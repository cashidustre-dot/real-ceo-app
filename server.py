from flask import Flask, request, jsonify, send_file
import os
import psycopg2
from psycopg2.extras import RealDictCursor

app = Flask(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL")


# =========================================================
# DATABASE
# =========================================================

def get_db():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL topilmadi!")

    return psycopg2.connect(
        DATABASE_URL,
        cursor_factory=RealDictCursor
    )


# =========================================================
# DATABASE INIT / MIGRATION
# =========================================================

def init_db():

    conn = get_db()
    cur = conn.cursor()

    # =====================================================
    # TRANSACTIONS
    # =====================================================

    cur.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id SERIAL PRIMARY KEY,
            type VARCHAR(20) NOT NULL,
            amount NUMERIC(14,2) NOT NULL,
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        ALTER TABLE transactions
        ADD COLUMN IF NOT EXISTS sale_id INTEGER
    """)

    # =====================================================
    # INVENTORY
    # =====================================================

    cur.execute("""
        CREATE TABLE IF NOT EXISTS inventory (
            id SERIAL PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            unit VARCHAR(50) NOT NULL,
            quantity NUMERIC(14,3) DEFAULT 0,
            min_quantity NUMERIC(14,3) DEFAULT 0,
            price NUMERIC(14,2) DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        ALTER TABLE inventory
        ADD COLUMN IF NOT EXISTS price NUMERIC(14,2) DEFAULT 0
    """)

    # =====================================================
    # EMPLOYEES
    # =====================================================

    cur.execute("""
        CREATE TABLE IF NOT EXISTS employees (
            id SERIAL PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            phone VARCHAR(50),
            position VARCHAR(255),
            salary NUMERIC(14,2) DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # =====================================================
    # SALES
    # =====================================================

    cur.execute("""
        CREATE TABLE IF NOT EXISTS sales (
            id SERIAL PRIMARY KEY,
            product_name VARCHAR(255) NOT NULL,
            quantity NUMERIC(14,3) NOT NULL,
            unit_price NUMERIC(14,2) NOT NULL,
            total NUMERIC(14,2),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Eski sales jadvaliga total qo'shish
    cur.execute("""
        ALTER TABLE sales
        ADD COLUMN IF NOT EXISTS total NUMERIC(14,2)
    """)

    # Eski sales uchun totalni hisoblash
    cur.execute("""
        UPDATE sales
        SET total = quantity * unit_price
        WHERE total IS NULL
    """)

    # Juda muhim:
    # Sotuv qaysi retseptdan yaratilganini saqlaymiz
    cur.execute("""
        ALTER TABLE sales
        ADD COLUMN IF NOT EXISTS recipe_id INTEGER
    """)

    # =====================================================
    # RECIPES
    # =====================================================

    cur.execute("""
        CREATE TABLE IF NOT EXISTS recipes (
            id SERIAL PRIMARY KEY,
            name VARCHAR(255) NOT NULL UNIQUE,
            sale_unit VARCHAR(50) DEFAULT 'dona',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # =====================================================
    # RECIPE ITEMS
    # =====================================================

    cur.execute("""
        CREATE TABLE IF NOT EXISTS recipe_items (
            id SERIAL PRIMARY KEY,
            recipe_id INTEGER NOT NULL
                REFERENCES recipes(id) ON DELETE CASCADE,
            inventory_id INTEGER NOT NULL
                REFERENCES inventory(id) ON DELETE CASCADE,
            quantity NUMERIC(14,4) NOT NULL
        )
    """)

    # =====================================================
    # SALE INVENTORY USAGE
    #
    # Har bir sotuvda ombordan aynan qancha mahsulot
    # ketganini saqlaydi.
    # =====================================================

    cur.execute("""
        CREATE TABLE IF NOT EXISTS sale_inventory_usage (
            id SERIAL PRIMARY KEY,

            sale_id INTEGER NOT NULL
                REFERENCES sales(id) ON DELETE CASCADE,

            inventory_id INTEGER NOT NULL
                REFERENCES inventory(id),

            quantity NUMERIC(14,4) NOT NULL,

            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()

    cur.close()
    conn.close()

    print("DATABASE INIT / MIGRATION OK")


try:
    init_db()
except Exception as e:
    print("DATABASE INIT ERROR:", e)


# =========================================================
# MAIN PAGE
# =========================================================

@app.get("/")
def home():

    index_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "index.html"
    )

    return send_file(index_path)


# =========================================================
# HEALTH
# =========================================================

@app.get("/api/health")
def health():

    try:

        conn = get_db()
        conn.close()

        return jsonify({
            "status": "ok",
            "database": "connected"
        })

    except Exception as e:

        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


# =========================================================
# DASHBOARD SUMMARY
# =========================================================

@app.get("/api/summary")
def summary():

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT COALESCE(SUM(amount),0) AS total
        FROM transactions
        WHERE type='income'
    """)

    income = float(cur.fetchone()["total"])

    cur.execute("""
        SELECT COALESCE(SUM(amount),0) AS total
        FROM transactions
        WHERE type='expense'
    """)

    expense = float(cur.fetchone()["total"])

    cur.execute("""
        SELECT COALESCE(SUM(quantity * price),0) AS total
        FROM inventory
    """)

    inventory_value = float(cur.fetchone()["total"])

    cur.execute("""
        SELECT COUNT(*) AS count
        FROM inventory
        WHERE quantity <= min_quantity
    """)

    low_stock = int(cur.fetchone()["count"])

    cur.close()
    conn.close()

    return jsonify({
        "income": income,
        "expense": expense,
        "profit": income - expense,
        "inventory": inventory_value,
        "low_stock": low_stock
    })


# =========================================================
# TRANSACTIONS
# =========================================================

@app.get("/api/transactions")
def get_transactions():

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT *
        FROM transactions
        ORDER BY created_at DESC
    """)

    data = cur.fetchall()

    cur.close()
    conn.close()

    return jsonify(data)


@app.post("/api/transactions")
def add_transaction():

    data = request.json or {}

    transaction_type = data.get("type")
    amount = data.get("amount")
    description = data.get("description", "")

    if transaction_type not in ["income", "expense"]:

        return jsonify({
            "error": "type income yoki expense bo'lishi kerak"
        }), 400

    if amount is None:

        return jsonify({
            "error": "amount kerak"
        }), 400

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO transactions
        (type, amount, description)

        VALUES (%s,%s,%s)

        RETURNING *
    """, (
        transaction_type,
        amount,
        description
    ))

    result = cur.fetchone()

    conn.commit()

    cur.close()
    conn.close()

    return jsonify(result), 201


@app.delete("/api/transactions/<int:transaction_id>")
def delete_transaction(transaction_id):

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        DELETE FROM transactions
        WHERE id=%s
        RETURNING *
    """, (
        transaction_id,
    ))

    result = cur.fetchone()

    if not result:

        conn.rollback()

        cur.close()
        conn.close()

        return jsonify({
            "error": "transaction topilmadi"
        }), 404

    conn.commit()

    cur.close()
    conn.close()

    return jsonify({
        "success": True,
        "deleted": result
    })


# =========================================================
# REPORT
# =========================================================

@app.get("/api/report")
def report():

    period = request.args.get(
        "period",
        "today"
    )

    if period == "today":

        condition = """
            created_at >= CURRENT_DATE
        """

    elif period == "week":

        condition = """
            created_at >= CURRENT_DATE
            - INTERVAL '7 days'
        """

    elif period == "month":

        condition = """
            created_at >= CURRENT_DATE
            - INTERVAL '30 days'
        """

    else:

        return jsonify({
            "error":
                "period today, week yoki month bo'lishi kerak"
        }), 400

    conn = get_db()
    cur = conn.cursor()

    cur.execute(f"""
        SELECT

            COALESCE(SUM(
                CASE
                    WHEN type='income'
                    THEN amount
                    ELSE 0
                END
            ),0) AS income,

            COALESCE(SUM(
                CASE
                    WHEN type='expense'
                    THEN amount
                    ELSE 0
                END
            ),0) AS expense

        FROM transactions

        WHERE {condition}
    """)

    result = cur.fetchone()

    income = float(
        result["income"]
    )

    expense = float(
        result["expense"]
    )

    cur.close()
    conn.close()

    return jsonify({
        "period": period,
        "income": income,
        "expense": expense,
        "profit": income - expense
    })


# =========================================================
# INVENTORY
# =========================================================

@app.get("/api/inventory")
def get_inventory():

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT *,

            CASE
                WHEN quantity <= min_quantity
                THEN TRUE
                ELSE FALSE
            END AS low_stock

        FROM inventory

        ORDER BY name
    """)

    data = cur.fetchall()

    cur.close()
    conn.close()

    return jsonify(data)


@app.post("/api/inventory")
def add_inventory():

    data = request.json or {}

    name = data.get("name")
    unit = data.get("unit")
    quantity = data.get(
        "quantity",
        0
    )
    min_quantity = data.get(
        "min_quantity",
        0
    )
    price = data.get(
        "price",
        0
    )

    if not name or not unit:

        return jsonify({
            "error": "name va unit kerak"
        }), 400

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO inventory
        (
            name,
            unit,
            quantity,
            min_quantity,
            price
        )

        VALUES (%s,%s,%s,%s,%s)

        RETURNING *
    """, (
        name,
        unit,
        quantity,
        min_quantity,
        price
    ))

    result = cur.fetchone()

    conn.commit()

    cur.close()
    conn.close()

    return jsonify(result), 201


@app.put("/api/inventory/<int:item_id>")
def update_inventory(item_id):

    data = request.json or {}

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        UPDATE inventory

        SET

            name=COALESCE(%s,name),

            unit=COALESCE(%s,unit),

            quantity=COALESCE(
                %s,
                quantity
            ),

            min_quantity=COALESCE(
                %s,
                min_quantity
            ),

            price=COALESCE(
                %s,
                price
            )

        WHERE id=%s

        RETURNING *
    """, (
        data.get("name"),
        data.get("unit"),
        data.get("quantity"),
        data.get("min_quantity"),
        data.get("price"),
        item_id
    ))

    result = cur.fetchone()

    if not result:

        conn.rollback()

        cur.close()
        conn.close()

        return jsonify({
            "error":
                "mahsulot topilmadi"
        }), 404

    conn.commit()

    cur.close()
    conn.close()

    return jsonify(result)


@app.delete("/api/inventory/<int:item_id>")
def delete_inventory(item_id):

    conn = get_db()
    cur = conn.cursor()

    try:

        cur.execute("""
            SELECT id
            FROM recipe_items
            WHERE inventory_id=%s
            LIMIT 1
        """, (
            item_id,
        ))

        used = cur.fetchone()

        if used:

            return jsonify({
                "error":
                    "Bu mahsulot retseptda ishlatilmoqda. "
                    "Avval retseptdan olib tashlang."
            }), 400

        cur.execute("""
            DELETE FROM inventory
            WHERE id=%s
            RETURNING *
        """, (
            item_id,
        ))

        result = cur.fetchone()

        if not result:

            conn.rollback()

            return jsonify({
                "error":
                    "mahsulot topilmadi"
            }), 404

        conn.commit()

        return jsonify({
            "success": True,
            "deleted": result
        })

    except Exception as e:

        conn.rollback()

        return jsonify({
            "error": str(e)
        }), 400

    finally:

        cur.close()
        conn.close()


# =========================================================
# STOCK IN
# =========================================================

@app.post("/api/inventory/<int:item_id>/in")
def inventory_in(item_id):

    data = request.json or {}

    amount = data.get(
        "quantity"
    )

    if (
        amount is None
        or float(amount) <= 0
    ):

        return jsonify({
            "error":
                "quantity noto'g'ri"
        }), 400

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        UPDATE inventory

        SET quantity =
            quantity + %s

        WHERE id=%s

        RETURNING *
    """, (
        amount,
        item_id
    ))

    result = cur.fetchone()

    if not result:

        conn.rollback()

        cur.close()
        conn.close()

        return jsonify({
            "error":
                "mahsulot topilmadi"
        }), 404

    conn.commit()

    cur.close()
    conn.close()

    return jsonify(result)


# =========================================================
# STOCK OUT
# =========================================================

@app.post("/api/inventory/<int:item_id>/out")
def inventory_out(item_id):

    data = request.json or {}

    amount = data.get(
        "quantity"
    )

    if (
        amount is None
        or float(amount) <= 0
    ):

        return jsonify({
            "error":
                "quantity noto'g'ri"
        }), 400

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT *
        FROM inventory

        WHERE id=%s

        FOR UPDATE
    """, (
        item_id,
    ))

    item = cur.fetchone()

    if not item:

        conn.rollback()

        cur.close()
        conn.close()

        return jsonify({
            "error":
                "mahsulot topilmadi"
        }), 404

    if float(
        item["quantity"]
    ) < float(amount):

        conn.rollback()

        cur.close()
        conn.close()

        return jsonify({
            "error":
                "omborda yetarli mahsulot yo'q"
        }), 400

    cur.execute("""
        UPDATE inventory

        SET quantity =
            quantity - %s

        WHERE id=%s

        RETURNING *
    """, (
        amount,
        item_id
    ))

    result = cur.fetchone()

    conn.commit()

    cur.close()
    conn.close()

    return jsonify(result)


# =========================================================
# PRICE
# =========================================================

@app.put("/api/inventory/<int:item_id>/price")
def update_inventory_price(item_id):

    data = request.json or {}

    price = data.get(
        "price"
    )

    if price is None:

        return jsonify({
            "error":
                "price kerak"
        }), 400

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        UPDATE inventory

        SET price=%s

        WHERE id=%s

        RETURNING *
    """, (
        price,
        item_id
    ))

    result = cur.fetchone()

    if not result:

        conn.rollback()

        cur.close()
        conn.close()

        return jsonify({
            "error":
                "mahsulot topilmadi"
        }), 404

    conn.commit()

    cur.close()
    conn.close()

    return jsonify(result)


@app.get("/api/inventory/summary")
def inventory_summary():

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT

            COALESCE(
                SUM(quantity * price),
                0
            ) AS total_value,

            COUNT(*) AS products,

            COUNT(*) FILTER (
                WHERE quantity <= min_quantity
            ) AS low_stock

        FROM inventory
    """)

    result = cur.fetchone()

    cur.close()
    conn.close()

    return jsonify({

        "total_value":
            float(result["total_value"]),

        "products":
            int(result["products"]),

        "low_stock":
            int(result["low_stock"])
    })


# =========================================================
# EMPLOYEES
# =========================================================

@app.get("/api/employees")
def get_employees():

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT *
        FROM employees
        ORDER BY name
    """)

    data = cur.fetchall()

    cur.close()
    conn.close()

    return jsonify(data)


@app.post("/api/employees")
def add_employee():

    data = request.json or {}

    name = data.get("name")
    phone = data.get(
        "phone",
        ""
    )
    position = data.get(
        "position",
        ""
    )
    salary = data.get(
        "salary",
        0
    )

    if not name:

        return jsonify({
            "error":
                "name kerak"
        }), 400

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO employees
        (
            name,
            phone,
            position,
            salary
        )

        VALUES (%s,%s,%s,%s)

        RETURNING *
    """, (
        name,
        phone,
        position,
        salary
    ))

    result = cur.fetchone()

    conn.commit()

    cur.close()
    conn.close()

    return jsonify(result), 201


@app.put("/api/employees/<int:employee_id>")
def update_employee(employee_id):

    data = request.json or {}

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        UPDATE employees

        SET

            name=COALESCE(
                %s,
                name
            ),

            phone=COALESCE(
                %s,
                phone
            ),

            position=COALESCE(
                %s,
                position
            ),

            salary=COALESCE(
                %s,
                salary
            )

        WHERE id=%s

        RETURNING *
    """, (
        data.get("name"),
        data.get("phone"),
        data.get("position"),
        data.get("salary"),
        employee_id
    ))

    result = cur.fetchone()

    if not result:

        conn.rollback()

        cur.close()
        conn.close()

        return jsonify({
            "error":
                "xodim topilmadi"
        }), 404

    conn.commit()

    cur.close()
    conn.close()

    return jsonify(result)


@app.delete("/api/employees/<int:employee_id>")
def delete_employee(employee_id):

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        DELETE FROM employees

        WHERE id=%s

        RETURNING *
    """, (
        employee_id,
    ))

    result = cur.fetchone()

    if not result:

        conn.rollback()

        cur.close()
        conn.close()

        return jsonify({
            "error":
                "xodim topilmadi"
        }), 404

    conn.commit()

    cur.close()
    conn.close()

    return jsonify({
        "success": True,
        "deleted": result
    })


@app.get("/api/employees/summary")
def employees_summary():

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT

            COUNT(*) AS count,

            COALESCE(
                SUM(salary),
                0
            ) AS salaries

        FROM employees
    """)

    result = cur.fetchone()

    cur.close()
    conn.close()

    return jsonify({

        "count":
            int(result["count"]),

        "salaries":
            float(result["salaries"])
    })


# =========================================================
# RECIPES
# =========================================================

@app.get("/api/recipes")
def get_recipes():

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT

            r.id,
            r.name,
            r.sale_unit,
            r.created_at,

            COUNT(ri.id)
                AS ingredient_count

        FROM recipes r

        LEFT JOIN recipe_items ri
            ON ri.recipe_id = r.id

        GROUP BY r.id

        ORDER BY r.name
    """)

    data = cur.fetchall()

    cur.close()
    conn.close()

    return jsonify(data)


@app.post("/api/recipes")
def create_recipe():

    data = request.json or {}

    name = str(
        data.get(
            "name",
            ""
        )
    ).strip()

    sale_unit = data.get(
        "sale_unit",
        "dona"
    )

    ingredients = data.get(
        "ingredients",
        []
    )

    if not name:

        return jsonify({
            "error":
                "Taom nomini kiriting"
        }), 400

    if not ingredients:

        return jsonify({
            "error":
                "Kamida bitta mahsulot qo'shing"
        }), 400

    conn = get_db()
    cur = conn.cursor()

    try:

        cur.execute("""
            INSERT INTO recipes
            (
                name,
                sale_unit
            )

            VALUES (%s,%s)

            RETURNING *
        """, (
            name,
            sale_unit
        ))

        recipe = cur.fetchone()

        for item in ingredients:

            inventory_id = item.get(
                "inventory_id"
            )

            quantity = item.get(
                "quantity"
            )

            if not inventory_id:
                continue

            if quantity is None:
                continue

            if float(quantity) <= 0:
                continue

            cur.execute("""
                SELECT id
                FROM inventory

                WHERE id=%s
            """, (
                inventory_id,
            ))

            inventory_item = cur.fetchone()

            if not inventory_item:

                raise Exception(
                    "Tanlangan mahsulot "
                    "omborda topilmadi"
                )

            cur.execute("""
                INSERT INTO recipe_items
                (
                    recipe_id,
                    inventory_id,
                    quantity
                )

                VALUES (%s,%s,%s)
            """, (
                recipe["id"],
                inventory_id,
                quantity
            ))

        conn.commit()

        return jsonify({
            "success": True,
            "recipe": recipe
        }), 201

    except Exception as e:

        conn.rollback()

        return jsonify({
            "error": str(e)
        }), 400

    finally:

        cur.close()
        conn.close()


@app.get("/api/recipes/<int:recipe_id>")
def get_recipe(recipe_id):

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT *
        FROM recipes

        WHERE id=%s
    """, (
        recipe_id,
    ))

    recipe = cur.fetchone()

    if not recipe:

        cur.close()
        conn.close()

        return jsonify({
            "error":
                "retsept topilmadi"
        }), 404

    cur.execute("""
        SELECT

            ri.id,
            ri.inventory_id,
            i.name AS inventory_name,
            i.unit,
            ri.quantity

        FROM recipe_items ri

        JOIN inventory i
            ON i.id = ri.inventory_id

        WHERE ri.recipe_id=%s

        ORDER BY i.name
    """, (
        recipe_id,
    ))

    ingredients = cur.fetchall()

    cur.close()
    conn.close()

    recipe["ingredients"] = ingredients

    return jsonify(recipe)


@app.put("/api/recipes/<int:recipe_id>")
def update_recipe(recipe_id):

    data = request.json or {}

    name = data.get(
        "name"
    )

    sale_unit = data.get(
        "sale_unit"
    )

    conn = get_db()
    cur = conn.cursor()

    try:

        cur.execute("""
            UPDATE recipes

            SET

                name=COALESCE(
                    %s,
                    name
                ),

                sale_unit=COALESCE(
                    %s,
                    sale_unit
                )

            WHERE id=%s

            RETURNING *
        """, (
            name,
            sale_unit,
            recipe_id
        ))

        recipe = cur.fetchone()

        if not recipe:

            conn.rollback()

            return jsonify({
                "error":
                    "retsept topilmadi"
            }), 404

        if "ingredients" in data:

            cur.execute("""
                DELETE FROM recipe_items

                WHERE recipe_id=%s
            """, (
                recipe_id,
            ))

            for item in data[
                "ingredients"
            ]:

                inventory_id = item.get(
                    "inventory_id"
                )

                quantity = item.get(
                    "quantity"
                )

                if not inventory_id:
                    continue

                if quantity is None:
                    continue

                if float(quantity) <= 0:
                    continue

                cur.execute("""
                    INSERT INTO recipe_items
                    (
                        recipe_id,
                        inventory_id,
                        quantity
                    )

                    VALUES (%s,%s,%s)
                """, (
                    recipe_id,
                    inventory_id,
                    quantity
                ))

        conn.commit()

        return jsonify({
            "success": True,
            "recipe": recipe
        })

    except Exception as e:

        conn.rollback()

        return jsonify({
            "error": str(e)
        }), 400

    finally:

        cur.close()
        conn.close()


@app.delete("/api/recipes/<int:recipe_id>")
def delete_recipe(recipe_id):

    conn = get_db()
    cur = conn.cursor()

    try:

        # Agar eski sotuvlar shu retseptga bog'langan
        # bo'lsa, retseptni o'chirishga ruxsat bermaymiz.
        cur.execute("""
            SELECT COUNT(*) AS count

            FROM sales

            WHERE recipe_id=%s
        """, (
            recipe_id,
        ))

        used_count = int(
            cur.fetchone()["count"]
        )

        if used_count > 0:

            return jsonify({
                "error":
                    "Bu retsept sotuvlarda ishlatilgan. "
                    "Uni o'chirish o'rniga tahrirlang."
            }), 400

        cur.execute("""
            DELETE FROM recipes

            WHERE id=%s

            RETURNING *
        """, (
            recipe_id,
        ))

        result = cur.fetchone()

        if not result:

            conn.rollback()

            return jsonify({
                "error":
                    "retsept topilmadi"
            }), 404

        conn.commit()

        return jsonify({
            "success": True,
            "deleted": result
        })

    except Exception as e:

        conn.rollback()

        return jsonify({
            "error": str(e)
        }), 400

    finally:

        cur.close()
        conn.close()


# =========================================================
# SALES
# =========================================================

@app.get("/api/sales")
def get_sales():

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT *

        FROM sales

        ORDER BY created_at DESC
    """)

    data = cur.fetchall()

    cur.close()
    conn.close()

    return jsonify(data)


# =========================================================
# CREATE SALE
# =========================================================

@app.post("/api/sales")
def add_sale():

    data = request.json or {}

    product_name = data.get(
        "product_name"
    )

    quantity = data.get(
        "quantity"
    )

    unit_price = data.get(
        "unit_price"
    )

    recipe_id = data.get(
        "recipe_id"
    )

    if not product_name:

        return jsonify({
            "error":
                "product_name kerak"
        }), 400

    if quantity is None:

        return jsonify({
            "error":
                "quantity kerak"
        }), 400

    if float(quantity) <= 0:

        return jsonify({
            "error":
                "quantity noto'g'ri"
        }), 400

    if unit_price is None:

        return jsonify({
            "error":
                "unit_price kerak"
        }), 400

    if float(unit_price) < 0:

        return jsonify({
            "error":
                "unit_price noto'g'ri"
        }), 400

    quantity = float(
        quantity
    )

    unit_price = float(
        unit_price
    )

    total = (
        quantity
        * unit_price
    )

    conn = get_db()
    cur = conn.cursor()

    try:

        recipe_items = []

        # =================================================
        # RETSEPTNI TEKSHIRISH
        # =================================================

        if recipe_id:

            cur.execute("""
                SELECT
                    ri.inventory_id,
                    ri.quantity,
                    i.name,
                    i.unit,
                    i.quantity AS stock

                FROM recipe_items ri

                JOIN inventory i
                    ON i.id =
                       ri.inventory_id

                WHERE ri.recipe_id=%s

                FOR UPDATE
            """, (
                recipe_id,
            ))

            recipe_items = cur.fetchall()

            if not recipe_items:

                raise Exception(
                    "Bu retseptda mahsulotlar "
                    "mavjud emas"
                )

            # Omborda yetarliligini tekshirish
            for item in recipe_items:

                needed = (
                    float(
                        item["quantity"]
                    )
                    * quantity
                )

                stock = float(
                    item["stock"]
                )

                if stock < needed:

                    raise Exception(
                        f"{item['name']} "
                        f"yetarli emas. "
                        f"Kerak: {needed} "
                        f"{item['unit']}, "
                        f"omborda: {stock} "
                        f"{item['unit']}"
                    )

        # =================================================
        # SOTUVNI SAQLASH
        # =================================================

        cur.execute("""
            INSERT INTO sales
            (
                product_name,
                quantity,
                unit_price,
                total,
                recipe_id
            )

            VALUES (
                %s,
                %s,
                %s,
                %s,
                %s
            )

            RETURNING *
        """, (
            product_name,
            quantity,
            unit_price,
            total,
            recipe_id
        ))

        sale = cur.fetchone()

        # =================================================
        # DAROMADNI SAQLASH
        # =================================================

        cur.execute("""
            INSERT INTO transactions
            (
                type,
                amount,
                description,
                sale_id
            )

            VALUES (
                'income',
                %s,
                %s,
                %s
            )

            RETURNING id
        """, (
            total,
            f"Sotuv: {product_name}",
            sale["id"]
        ))

        transaction = cur.fetchone()

        # =================================================
        # OMBORDAN YECHISH
        # =================================================

        used_inventory = []

        for item in recipe_items:

            needed = (
                float(
                    item["quantity"]
                )
                * quantity
            )

            # Ombordan yechish
            cur.execute("""
                UPDATE inventory

                SET quantity =
                    quantity - %s

                WHERE id=%s

                RETURNING *
            """, (
                needed,
                item["inventory_id"]
            ))

            updated = cur.fetchone()

            # =================================================
            # SOTUVDA QANCHA ISHLATILGANINI SAQLASH
            # =================================================

            cur.execute("""
                INSERT INTO sale_inventory_usage
                (
                    sale_id,
                    inventory_id,
                    quantity
                )

                VALUES (%s,%s,%s)
            """, (
                sale["id"],
                item["inventory_id"],
                needed
            ))

            used_inventory.append({

                "inventory_id":
                    item["inventory_id"],

                "name":
                    item["name"],

                "used":
                    needed,

                "remaining":
                    float(
                        updated["quantity"]
                    )
            })

        conn.commit()

        return jsonify({

            "success": True,

            "sale":
                sale,

            "transaction_id":
                transaction["id"],

            "inventory_used":
                used_inventory

        }), 201

    except Exception as e:

        conn.rollback()

        return jsonify({
            "error":
                str(e)
        }), 400

    finally:

        cur.close()
        conn.close()


# =========================================================
# SALES SUMMARY
# =========================================================

@app.get("/api/sales/summary")
def sales_summary():

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT

            COALESCE(
                SUM(total),
                0
            ) AS total_sales,

            COUNT(*) AS sales_count

        FROM sales

        WHERE created_at >= CURRENT_DATE
    """)

    result = cur.fetchone()

    cur.close()
    conn.close()

    return jsonify({

        "total_sales":
            float(
                result["total_sales"]
            ),

        "sales_count":
            int(
                result["sales_count"]
            )
    })


# =========================================================
# DELETE SALE
#
# ENG MUHIM QISM:
# Sotuv o'chirilganda ombor qaytariladi.
# =========================================================

@app.delete("/api/sales/<int:sale_id>")
def delete_sale(sale_id):

    conn = get_db()
    cur = conn.cursor()

    try:

        # =================================================
        # SOTUVNI TOPISH
        # =================================================

        cur.execute("""
            SELECT *

            FROM sales

            WHERE id=%s

            FOR UPDATE
        """, (
            sale_id,
        ))

        sale = cur.fetchone()

        if not sale:

            conn.rollback()

            return jsonify({
                "error":
                    "sotuv topilmadi"
            }), 404

        # =================================================
        # OMBORGA QAYTARILADIGAN MAHSULOTLAR
        # =================================================

        cur.execute("""
            SELECT
                sui.inventory_id,
                sui.quantity,
                i.name,
                i.unit

            FROM sale_inventory_usage sui

            JOIN inventory i
                ON i.id =
                   sui.inventory_id

            WHERE sui.sale_id=%s

            FOR UPDATE
        """, (
            sale_id,
        ))

        usage_items = cur.fetchall()

        restored_inventory = []

        # =================================================
        # OMBORGA QAYTARISH
        # =================================================

        for item in usage_items:

            cur.execute("""
                UPDATE inventory

                SET quantity =
                    quantity + %s

                WHERE id=%s

                RETURNING *
            """, (
                item["quantity"],
                item["inventory_id"]
            ))

            updated = cur.fetchone()

            if updated:

                restored_inventory.append({

                    "inventory_id":
                        item["inventory_id"],

                    "name":
                        item["name"],

                    "restored":
                        float(
                            item["quantity"]
                        ),

                    "remaining":
                        float(
                            updated["quantity"]
                        )
                })

        # =================================================
        # DAROMADNI O'CHIRISH
        # =================================================

        cur.execute("""
            DELETE FROM transactions

            WHERE sale_id=%s
        """, (
            sale_id,
        ))

        # =================================================
        # SALE INVENTORY USAGE O'CHIRISH
        # =================================================

        cur.execute("""
            DELETE FROM sale_inventory_usage

            WHERE sale_id=%s
        """, (
            sale_id,
        ))

        # =================================================
        # SOTUVNI O'CHIRISH
        # =================================================

        cur.execute("""
            DELETE FROM sales

            WHERE id=%s
        """, (
            sale_id,
        ))

        conn.commit()

        return jsonify({

            "success": True,

            "deleted":
                sale,

            "inventory_restored":
                restored_inventory

        })

    except Exception as e:

        conn.rollback()

        return jsonify({
            "error":
                str(e)
        }), 400

    finally:

        cur.close()
        conn.close()


# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":

    port = int(
        os.environ.get(
            "PORT",
            5000
        )
    )

    app.run(
        host="0.0.0.0",
        port=port
    )
