from flask import Flask, request, jsonify, send_file
import os
import psycopg2
from psycopg2.extras import RealDictCursor

app = Flask(__name__)


# =========================================================
# DATABASE
# =========================================================

def get_db():
    return psycopg2.connect(
        os.environ["DATABASE_URL"],
        cursor_factory=RealDictCursor
    )


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
            quantity NUMERIC(14,4) DEFAULT 0,
            min_quantity NUMERIC(14,4) DEFAULT 0,
            price NUMERIC(14,2) DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # =====================================================
    # EMPLOYEES
    # =====================================================
    cur.execute("""
        CREATE TABLE IF NOT EXISTS employees (
            id SERIAL PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            phone VARCHAR(100),
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
            quantity NUMERIC(14,4) NOT NULL,
            unit_price NUMERIC(14,2) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Old table migration
    cur.execute("""
        ALTER TABLE sales
        ADD COLUMN IF NOT EXISTS total NUMERIC(14,2)
    """)

    cur.execute("""
        UPDATE sales
        SET total = quantity * unit_price
        WHERE total IS NULL
    """)

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
            name VARCHAR(255) UNIQUE NOT NULL,
            sale_unit VARCHAR(100) DEFAULT 'dona',
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
                REFERENCES recipes(id)
                ON DELETE CASCADE,
            inventory_id INTEGER NOT NULL
                REFERENCES inventory(id),
            quantity NUMERIC(14,4) NOT NULL
        )
    """)

    # =====================================================
    # SALE INVENTORY USAGE
    # =====================================================
    cur.execute("""
        CREATE TABLE IF NOT EXISTS sale_inventory_usage (
            id SERIAL PRIMARY KEY,
            sale_id INTEGER NOT NULL
                REFERENCES sales(id)
                ON DELETE CASCADE,
            inventory_id INTEGER NOT NULL
                REFERENCES inventory(id),
            quantity NUMERIC(14,4) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    cur.close()
    conn.close()


# =========================================================
# START DATABASE
# =========================================================

try:
    init_db()
except Exception as e:
    print("DATABASE INIT ERROR:", e)


# =========================================================
# HOME
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
    return jsonify({
        "status": "ok",
        "message": "Real CEO API ishlayapti"
    })


# =========================================================
# DASHBOARD SUMMARY
# =========================================================

@app.get("/api/summary")
def summary():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            COALESCE(SUM(
                CASE
                    WHEN type = 'income'
                    THEN amount
                    ELSE 0
                END
            ), 0) AS income,

            COALESCE(SUM(
                CASE
                    WHEN type = 'expense'
                    THEN amount
                    ELSE 0
                END
            ), 0) AS expense
        FROM transactions
    """)

    finance = cur.fetchone()

    cur.execute("""
        SELECT
            COALESCE(SUM(quantity * price), 0) AS inventory_value,
            COUNT(*) FILTER (
                WHERE quantity <= min_quantity
            ) AS low_stock
        FROM inventory
    """)

    inventory_data = cur.fetchone()

    cur.execute("""
        SELECT
            COALESCE(SUM(quantity), 0) AS today_sales
        FROM sales
        WHERE created_at >= CURRENT_DATE
    """)

    sales_data = cur.fetchone()

    income = float(finance["income"] or 0)
    expense = float(finance["expense"] or 0)

    result = {
        "income": income,
        "expense": expense,
        "profit": income - expense,
        "inventory_value": float(
            inventory_data["inventory_value"] or 0
        ),
        "low_stock": int(
            inventory_data["low_stock"] or 0
        ),
        "today_sales": float(
            sales_data["today_sales"] or 0
        )
    }

    cur.close()
    conn.close()

    return jsonify(result)


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

    rows = cur.fetchall()

    cur.close()
    conn.close()

    return jsonify(rows)


@app.post("/api/transactions")
def add_transaction():
    data = request.get_json() or {}

    tx_type = data.get("type")
    amount = data.get("amount")
    description = data.get("description", "")

    if tx_type not in ["income", "expense"]:
        return jsonify({
            "error": "type noto‘g‘ri"
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
        VALUES (%s, %s, %s)
        RETURNING *
    """, (
        tx_type,
        amount,
        description
    ))

    row = cur.fetchone()

    conn.commit()
    cur.close()
    conn.close()

    return jsonify(row), 201


@app.delete("/api/transactions/<int:transaction_id>")
def delete_transaction(transaction_id):
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        DELETE FROM transactions
        WHERE id = %s
        RETURNING *
    """, (transaction_id,))

    row = cur.fetchone()

    if not row:
        conn.rollback()
        cur.close()
        conn.close()

        return jsonify({
            "error": "Tranzaksiya topilmadi"
        }), 404

    conn.commit()

    cur.close()
    conn.close()

    return jsonify({
        "message": "Tranzaksiya o‘chirildi"
    })


# =========================================================
# REPORT
# =========================================================

@app.get("/api/report")
def report():
    period = request.args.get("period", "today")

    conn = get_db()
    cur = conn.cursor()

    if period == "week":
        condition = "created_at >= CURRENT_DATE - INTERVAL '6 days'"
    elif period == "month":
        condition = "created_at >= DATE_TRUNC('month', CURRENT_DATE)"
    else:
        condition = "created_at >= CURRENT_DATE"

    cur.execute(f"""
        SELECT
            COALESCE(SUM(
                CASE
                    WHEN type = 'income'
                    THEN amount
                    ELSE 0
                END
            ), 0) AS income,

            COALESCE(SUM(
                CASE
                    WHEN type = 'expense'
                    THEN amount
                    ELSE 0
                END
            ), 0) AS expense
        FROM transactions
        WHERE {condition}
    """)

    row = cur.fetchone()

    income = float(row["income"] or 0)
    expense = float(row["expense"] or 0)

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
               quantity * price AS total_value,
               CASE
                   WHEN quantity <= min_quantity
                   THEN TRUE
                   ELSE FALSE
               END AS low_stock
        FROM inventory
        ORDER BY id DESC
    """)

    rows = cur.fetchall()

    cur.close()
    conn.close()

    return jsonify(rows)


@app.post("/api/inventory")
def add_inventory():
    data = request.get_json() or {}

    name = data.get("name")
    unit = data.get("unit")
    quantity = data.get("quantity", 0)
    min_quantity = data.get("min_quantity", 0)
    price = data.get("price", 0)

    if not name or not unit:
        return jsonify({
            "error": "name va unit kerak"
        }), 400

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO inventory
        (name, unit, quantity, min_quantity, price)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING *
    """, (
        name,
        unit,
        quantity,
        min_quantity,
        price
    ))

    row = cur.fetchone()

    conn.commit()

    cur.close()
    conn.close()

    return jsonify(row), 201


@app.put("/api/inventory/<int:item_id>")
def update_inventory(item_id):
    data = request.get_json() or {}

    name = data.get("name")
    unit = data.get("unit")
    min_quantity = data.get("min_quantity")
    price = data.get("price")

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        UPDATE inventory
        SET
            name = COALESCE(%s, name),
            unit = COALESCE(%s, unit),
            min_quantity = COALESCE(%s, min_quantity),
            price = COALESCE(%s, price)
        WHERE id = %s
        RETURNING *
    """, (
        name,
        unit,
        min_quantity,
        price,
        item_id
    ))

    row = cur.fetchone()

    if not row:
        conn.rollback()
        cur.close()
        conn.close()

        return jsonify({
            "error": "Mahsulot topilmadi"
        }), 404

    conn.commit()

    cur.close()
    conn.close()

    return jsonify(row)


@app.delete("/api/inventory/<int:item_id>")
def delete_inventory(item_id):
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT COUNT(*) AS count
        FROM recipe_items
        WHERE inventory_id = %s
    """, (item_id,))

    used = cur.fetchone()

    if int(used["count"]) > 0:
        cur.close()
        conn.close()

        return jsonify({
            "error": "Bu mahsulot retseptda ishlatilgan. Avval retseptdan olib tashlang."
        }), 400

    cur.execute("""
        DELETE FROM inventory
        WHERE id = %s
        RETURNING *
    """, (item_id,))

    row = cur.fetchone()

    if not row:
        conn.rollback()
        cur.close()
        conn.close()

        return jsonify({
            "error": "Mahsulot topilmadi"
        }), 404

    conn.commit()

    cur.close()
    conn.close()

    return jsonify({
        "message": "Mahsulot o‘chirildi"
    })


@app.post("/api/inventory/<int:item_id>/stock")
def inventory_stock(item_id):
    data = request.get_json() or {}

    action = data.get("action")
    amount = data.get("amount")

    if action not in ["in", "out"]:
        return jsonify({
            "error": "action in yoki out bo‘lishi kerak"
        }), 400

    if amount is None or float(amount) <= 0:
        return jsonify({
            "error": "amount noto‘g‘ri"
        }), 400

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT *
        FROM inventory
        WHERE id = %s
        FOR UPDATE
    """, (item_id,))

    item = cur.fetchone()

    if not item:
        conn.rollback()
        cur.close()
        conn.close()

        return jsonify({
            "error": "Mahsulot topilmadi"
        }), 404

    if action == "in":
        new_quantity = float(item["quantity"]) + float(amount)
    else:
        new_quantity = float(item["quantity"]) - float(amount)

        if new_quantity < 0:
            conn.rollback()
            cur.close()
            conn.close()

            return jsonify({
                "error": "Omborda yetarli mahsulot yo‘q"
            }), 400

    cur.execute("""
        UPDATE inventory
        SET quantity = %s
        WHERE id = %s
        RETURNING *
    """, (
        new_quantity,
        item_id
    ))

    row = cur.fetchone()

    conn.commit()

    cur.close()
    conn.close()

    return jsonify(row)


@app.put("/api/inventory/<int:item_id>/price")
def update_inventory_price(item_id):
    data = request.get_json() or {}

    price = data.get("price")

    if price is None:
        return jsonify({
            "error": "price kerak"
        }), 400

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        UPDATE inventory
        SET price = %s
        WHERE id = %s
        RETURNING *
    """, (
        price,
        item_id
    ))

    row = cur.fetchone()

    if not row:
        conn.rollback()
        cur.close()
        conn.close()

        return jsonify({
            "error": "Mahsulot topilmadi"
        }), 404

    conn.commit()

    cur.close()
    conn.close()

    return jsonify(row)


@app.get("/api/inventory/summary")
def inventory_summary():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            COALESCE(SUM(quantity * price), 0) AS total_value,
            COUNT(*) AS products,
            COUNT(*) FILTER (
                WHERE quantity <= min_quantity
            ) AS low_stock
        FROM inventory
    """)

    row = cur.fetchone()

    cur.close()
    conn.close()

    return jsonify(row)


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
        ORDER BY id DESC
    """)

    rows = cur.fetchall()

    cur.close()
    conn.close()

    return jsonify(rows)


@app.post("/api/employees")
def add_employee():
    data = request.get_json() or {}

    name = data.get("name")
    phone = data.get("phone", "")
    position = data.get("position", "")
    salary = data.get("salary", 0)

    if not name:
        return jsonify({
            "error": "name kerak"
        }), 400

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO employees
        (name, phone, position, salary)
        VALUES (%s, %s, %s, %s)
        RETURNING *
    """, (
        name,
        phone,
        position,
        salary
    ))

    row = cur.fetchone()

    conn.commit()

    cur.close()
    conn.close()

    return jsonify(row), 201


@app.put("/api/employees/<int:employee_id>")
def update_employee(employee_id):
    data = request.get_json() or {}

    name = data.get("name")
    phone = data.get("phone")
    position = data.get("position")
    salary = data.get("salary")

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        UPDATE employees
        SET
            name = COALESCE(%s, name),
            phone = COALESCE(%s, phone),
            position = COALESCE(%s, position),
            salary = COALESCE(%s, salary)
        WHERE id = %s
        RETURNING *
    """, (
        name,
        phone,
        position,
        salary,
        employee_id
    ))

    row = cur.fetchone()

    if not row:
        conn.rollback()
        cur.close()
        conn.close()

        return jsonify({
            "error": "Xodim topilmadi"
        }), 404

    conn.commit()

    cur.close()
    conn.close()

    return jsonify(row)


@app.delete("/api/employees/<int:employee_id>")
def delete_employee(employee_id):
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        DELETE FROM employees
        WHERE id = %s
        RETURNING *
    """, (employee_id,))

    row = cur.fetchone()

    if not row:
        conn.rollback()
        cur.close()
        conn.close()

        return jsonify({
            "error": "Xodim topilmadi"
        }), 404

    conn.commit()

    cur.close()
    conn.close()

    return jsonify({
        "message": "Xodim o‘chirildi"
    })


@app.get("/api/employees/summary")
def employee_summary():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            COUNT(*) AS employees,
            COALESCE(SUM(salary), 0) AS total_salary
        FROM employees
    """)

    row = cur.fetchone()

    cur.close()
    conn.close()

    return jsonify(row)


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

            COALESCE(
                SUM(ri.quantity * i.price),
                0
            ) AS cost

        FROM recipes r

        LEFT JOIN recipe_items ri
            ON ri.recipe_id = r.id

        LEFT JOIN inventory i
            ON i.id = ri.inventory_id

        GROUP BY
            r.id,
            r.name,
            r.sale_unit,
            r.created_at

        ORDER BY r.id DESC
    """)

    recipes = cur.fetchall()

    for recipe in recipes:
        cur.execute("""
            SELECT
                ri.id,
                ri.inventory_id,
                i.name,
                i.unit,
                ri.quantity,
                i.price,
                ri.quantity * i.price AS item_cost
            FROM recipe_items ri
            JOIN inventory i
                ON i.id = ri.inventory_id
            WHERE ri.recipe_id = %s
            ORDER BY ri.id
        """, (recipe["id"],))

        recipe["items"] = cur.fetchall()

    cur.close()
    conn.close()

    return jsonify(recipes)


@app.get("/api/recipes/<int:recipe_id>")
def get_recipe(recipe_id):
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT *
        FROM recipes
        WHERE id = %s
    """, (recipe_id,))

    recipe = cur.fetchone()

    if not recipe:
        cur.close()
        conn.close()

        return jsonify({
            "error": "Retsept topilmadi"
        }), 404

    cur.execute("""
        SELECT
            ri.id,
            ri.inventory_id,
            i.name,
            i.unit,
            ri.quantity,
            i.price,
            ri.quantity * i.price AS item_cost
        FROM recipe_items ri
        JOIN inventory i
            ON i.id = ri.inventory_id
        WHERE ri.recipe_id = %s
        ORDER BY ri.id
    """, (recipe_id,))

    recipe["items"] = cur.fetchall()

    total_cost = sum(
        float(item["item_cost"] or 0)
        for item in recipe["items"]
    )

    recipe["cost"] = total_cost

    cur.close()
    conn.close()

    return jsonify(recipe)


@app.post("/api/recipes")
def add_recipe():
    data = request.get_json() or {}

    name = data.get("name")
    sale_unit = data.get("sale_unit", "dona")
    items = data.get("items", [])

    if not name:
        return jsonify({
            "error": "Retsept nomi kerak"
        }), 400

    if not items:
        return jsonify({
            "error": "Retseptga kamida bitta mahsulot qo‘shing"
        }), 400

    conn = get_db()
    cur = conn.cursor()

    try:
        cur.execute("""
            INSERT INTO recipes
            (name, sale_unit)
            VALUES (%s, %s)
            RETURNING *
        """, (
            name,
            sale_unit
        ))

        recipe = cur.fetchone()

        for item in items:
            inventory_id = item.get("inventory_id")
            quantity = item.get("quantity")

            if not inventory_id or quantity is None:
                raise ValueError(
                    "Retsept tarkibidagi ma'lumot noto‘g‘ri"
                )

            cur.execute("""
                INSERT INTO recipe_items
                (recipe_id, inventory_id, quantity)
                VALUES (%s, %s, %s)
            """, (
                recipe["id"],
                inventory_id,
                quantity
            ))

        conn.commit()

        return jsonify(recipe), 201

    except Exception as e:
        conn.rollback()

        return jsonify({
            "error": str(e)
        }), 400

    finally:
        cur.close()
        conn.close()


@app.put("/api/recipes/<int:recipe_id>")
def update_recipe(recipe_id):
    data = request.get_json() or {}

    name = data.get("name")
    sale_unit = data.get("sale_unit")
    items = data.get("items")

    conn = get_db()
    cur = conn.cursor()

    try:
        cur.execute("""
            SELECT *
            FROM recipes
            WHERE id = %s
        """, (recipe_id,))

        recipe = cur.fetchone()

        if not recipe:
            raise ValueError("Retsept topilmadi")

        cur.execute("""
            SELECT COUNT(*) AS count
            FROM sales
            WHERE recipe_id = %s
        """, (recipe_id,))

        used = cur.fetchone()

        if int(used["count"]) > 0:
            return jsonify({
                "error": "Bu retsept sotuvlarda ishlatilgan. Uni o‘zgartirish xavfsiz emas."
            }), 400

        cur.execute("""
            UPDATE recipes
            SET
                name = COALESCE(%s, name),
                sale_unit = COALESCE(%s, sale_unit)
            WHERE id = %s
            RETURNING *
        """, (
            name,
            sale_unit,
            recipe_id
        ))

        recipe = cur.fetchone()

        if items is not None:
            cur.execute("""
                DELETE FROM recipe_items
                WHERE recipe_id = %s
            """, (recipe_id,))

            for item in items:
                inventory_id = item.get("inventory_id")
                quantity = item.get("quantity")

                if not inventory_id or quantity is None:
                    raise ValueError(
                        "Retsept tarkibidagi ma'lumot noto‘g‘ri"
                    )

                cur.execute("""
                    INSERT INTO recipe_items
                    (recipe_id, inventory_id, quantity)
                    VALUES (%s, %s, %s)
                """, (
                    recipe_id,
                    inventory_id,
                    quantity
                ))

        conn.commit()

        return jsonify(recipe)

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

    cur.execute("""
        SELECT COUNT(*) AS count
        FROM sales
        WHERE recipe_id = %s
    """, (recipe_id,))

    used = cur.fetchone()

    if int(used["count"]) > 0:
        cur.close()
        conn.close()

        return jsonify({
            "error": "Bu retsept sotuvlarda ishlatilgan. Uni o‘chirib bo‘lmaydi."
        }), 400

    cur.execute("""
        DELETE FROM recipes
        WHERE id = %s
        RETURNING *
    """, (recipe_id,))

    row = cur.fetchone()

    if not row:
        conn.rollback()
        cur.close()
        conn.close()

        return jsonify({
            "error": "Retsept topilmadi"
        }), 404

    conn.commit()

    cur.close()
    conn.close()

    return jsonify({
        "message": "Retsept o‘chirildi"
    })


# =========================================================
# SALES
# =========================================================

@app.get("/api/sales")
def get_sales():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            s.*,
            r.name AS recipe_name
        FROM sales s
        LEFT JOIN recipes r
            ON r.id = s.recipe_id
        ORDER BY s.created_at DESC
    """)

    rows = cur.fetchall()

    cur.close()
    conn.close()

    return jsonify(rows)


@app.get("/api/sales/summary")
def sales_summary():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            COALESCE(SUM(quantity), 0) AS total_quantity,
            COALESCE(SUM(total), 0) AS total_sales
        FROM sales
        WHERE created_at >= CURRENT_DATE
    """)

    row = cur.fetchone()

    cur.close()
    conn.close()

    return jsonify(row)


# =========================================================
# ADD SALE
# =========================================================

@app.post("/api/sales")
def add_sale():
    data = request.get_json() or {}

    product_name = data.get("product_name")
    quantity = data.get("quantity")
    unit_price = data.get("unit_price")
    recipe_id = data.get("recipe_id")

    if not product_name:
        return jsonify({
            "error": "Mahsulot nomi kerak"
        }), 400

    if quantity is None or float(quantity) <= 0:
        return jsonify({
            "error": "Sotuv miqdori noto‘g‘ri"
        }), 400

    if unit_price is None or float(unit_price) < 0:
        return jsonify({
            "error": "Narx noto‘g‘ri"
        }), 400

    conn = get_db()
    cur = conn.cursor()

    try:
        quantity = float(quantity)
        unit_price = float(unit_price)
        total = quantity * unit_price

        # ---------------------------------------------
        # RECIPE CHECK
        # ---------------------------------------------

        recipe_items = []

        if recipe_id:
            cur.execute("""
                SELECT *
                FROM recipes
                WHERE id = %s
            """, (recipe_id,))

            recipe = cur.fetchone()

            if not recipe:
                raise ValueError("Retsept topilmadi")

            cur.execute("""
                SELECT
                    ri.inventory_id,
                    ri.quantity,
                    i.name,
                    i.unit,
                    i.quantity AS stock
                FROM recipe_items ri
                JOIN inventory i
                    ON i.id = ri.inventory_id
                WHERE ri.recipe_id = %s
                FOR UPDATE OF i
            """, (recipe_id,))

            recipe_items = cur.fetchall()

            for item in recipe_items:
                needed = float(item["quantity"]) * quantity
                stock = float(item["stock"])

                if stock < needed:
                    raise ValueError(
                        f"{item['name']} yetarli emas. "
                        f"Kerak: {needed} {item['unit']}, "
                        f"omborda: {stock} {item['unit']}"
                    )

        # ---------------------------------------------
        # INSERT SALE
        # ---------------------------------------------

        cur.execute("""
            INSERT INTO sales
            (
                product_name,
                quantity,
                unit_price,
                total,
                recipe_id
            )
            VALUES (%s, %s, %s, %s, %s)
            RETURNING *
        """, (
            product_name,
            quantity,
            unit_price,
            total,
            recipe_id
        ))

        sale = cur.fetchone()

        # ---------------------------------------------
        # INCOME TRANSACTION
        # ---------------------------------------------

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

        # ---------------------------------------------
        # INVENTORY DECREASE
        # ---------------------------------------------

        for item in recipe_items:
            needed = float(item["quantity"]) * quantity

            cur.execute("""
                UPDATE inventory
                SET quantity = quantity - %s
                WHERE id = %s
            """, (
                needed,
                item["inventory_id"]
            ))

            # exact usage record
            cur.execute("""
                INSERT INTO sale_inventory_usage
                (
                    sale_id,
                    inventory_id,
                    quantity
                )
                VALUES (%s, %s, %s)
            """, (
                sale["id"],
                item["inventory_id"],
                needed
            ))

        conn.commit()

        return jsonify(sale), 201

    except Exception as e:
        conn.rollback()

        return jsonify({
            "error": str(e)
        }), 400

    finally:
        cur.close()
        conn.close()


# =========================================================
# DELETE SALE
# =========================================================

@app.delete("/api/sales/<int:sale_id>")
def delete_sale(sale_id):
    conn = get_db()
    cur = conn.cursor()

    try:
        # ---------------------------------------------
        # FIND SALE
        # ---------------------------------------------

        cur.execute("""
            SELECT *
            FROM sales
            WHERE id = %s
            FOR UPDATE
        """, (sale_id,))

        sale = cur.fetchone()

        if not sale:
            raise ValueError("Sotuv topilmadi")

        # ---------------------------------------------
        # GET INVENTORY USAGE
        # ---------------------------------------------

        cur.execute("""
            SELECT
                sui.inventory_id,
                sui.quantity,
                i.name
            FROM sale_inventory_usage sui
            JOIN inventory i
                ON i.id = sui.inventory_id
            WHERE sui.sale_id = %s
            FOR UPDATE OF i
        """, (sale_id,))

        usage_rows = cur.fetchall()

        restored = []

        # ---------------------------------------------
        # RESTORE INVENTORY
        # ---------------------------------------------

        for usage in usage_rows:
            cur.execute("""
                UPDATE inventory
                SET quantity = quantity + %s
                WHERE id = %s
                RETURNING *
            """, (
                usage["quantity"],
                usage["inventory_id"]
            ))

            item = cur.fetchone()

            restored.append({
                "name": usage["name"],
                "quantity": float(usage["quantity"])
            })

        # ---------------------------------------------
        # DELETE LINKED TRANSACTION
        # ---------------------------------------------

        cur.execute("""
            DELETE FROM transactions
            WHERE sale_id = %s
        """, (sale_id,))

        # ---------------------------------------------
        # DELETE USAGE
        # ---------------------------------------------

        cur.execute("""
            DELETE FROM sale_inventory_usage
            WHERE sale_id = %s
        """, (sale_id,))

        # ---------------------------------------------
        # DELETE SALE
        # ---------------------------------------------

        cur.execute("""
            DELETE FROM sales
            WHERE id = %s
        """, (sale_id,))

        conn.commit()

        return jsonify({
            "message": "Sotuv o‘chirildi va ombor tiklandi",
            "restored": restored
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
# COST / PROFIT
# =========================================================

@app.get("/api/profit-summary")
def profit_summary():
    """
    Sotuvlar bo‘yicha:
    - revenue = sotuvdan tushgan pul
    - cost = retseptdagi mahsulotlar tannarxi
    - profit = revenue - cost
    """

    conn = get_db()
    cur = conn.cursor()

    # -----------------------------------------------------
    # BUGUN
    # -----------------------------------------------------

    cur.execute("""
        SELECT
            COALESCE(SUM(s.total), 0) AS revenue,

            COALESCE(
                SUM(
                    s.quantity *
                    COALESCE(recipe_cost.cost, 0)
                ),
                0
            ) AS cost

        FROM sales s

        LEFT JOIN LATERAL (
            SELECT
                COALESCE(
                    SUM(
                        ri.quantity * i.price
                    ),
                    0
                ) AS cost

            FROM recipe_items ri

            JOIN inventory i
                ON i.id = ri.inventory_id

            WHERE ri.recipe_id = s.recipe_id
        ) recipe_cost
        ON TRUE

        WHERE s.created_at >= CURRENT_DATE
    """)

    today = cur.fetchone()

    # -----------------------------------------------------
    # HAFTA
    # -----------------------------------------------------

    cur.execute("""
        SELECT
            COALESCE(SUM(s.total), 0) AS revenue,

            COALESCE(
                SUM(
                    s.quantity *
                    COALESCE(recipe_cost.cost, 0)
                ),
                0
            ) AS cost

        FROM sales s

        LEFT JOIN LATERAL (
            SELECT
                COALESCE(
                    SUM(
                        ri.quantity * i.price
                    ),
                    0
                ) AS cost

            FROM recipe_items ri

            JOIN inventory i
                ON i.id = ri.inventory_id

            WHERE ri.recipe_id = s.recipe_id
        ) recipe_cost
        ON TRUE

        WHERE s.created_at >= CURRENT_DATE - INTERVAL '6 days'
    """)

    week = cur.fetchone()

    # -----------------------------------------------------
    # OY
    # -----------------------------------------------------

    cur.execute("""
        SELECT
            COALESCE(SUM(s.total), 0) AS revenue,

            COALESCE(
                SUM(
                    s.quantity *
                    COALESCE(recipe_cost.cost, 0)
                ),
                0
            ) AS cost

        FROM sales s

        LEFT JOIN LATERAL (
            SELECT
                COALESCE(
                    SUM(
                        ri.quantity * i.price
                    ),
                    0
                ) AS cost

            FROM recipe_items ri

            JOIN inventory i
                ON i.id = ri.inventory_id

            WHERE ri.recipe_id = s.recipe_id
        ) recipe_cost
        ON TRUE

        WHERE s.created_at >= DATE_TRUNC(
            'month',
            CURRENT_DATE
        )
    """)

    month = cur.fetchone()

    # -----------------------------------------------------
    # TOP PRODUCTS
    # -----------------------------------------------------

    cur.execute("""
        SELECT
            s.product_name,
            SUM(s.quantity) AS quantity,
            SUM(s.total) AS revenue,

            SUM(
                s.quantity *
                COALESCE(recipe_cost.cost, 0)
            ) AS cost

        FROM sales s

        LEFT JOIN LATERAL (
            SELECT
                COALESCE(
                    SUM(
                        ri.quantity * i.price
                    ),
                    0
                ) AS cost

            FROM recipe_items ri

            JOIN inventory i
                ON i.id = ri.inventory_id

            WHERE ri.recipe_id = s.recipe_id
        ) recipe_cost
        ON TRUE

        GROUP BY s.product_name

        ORDER BY quantity DESC

        LIMIT 10
    """)

    top_products = cur.fetchall()

    def make_period(row):
        revenue = float(row["revenue"] or 0)
        cost = float(row["cost"] or 0)

        return {
            "revenue": revenue,
            "cost": cost,
            "profit": revenue - cost
        }

    result = {
        "today": make_period(today),
        "week": make_period(week),
        "month": make_period(month),
        "top_products": []
    }

    for product in top_products:
        revenue = float(product["revenue"] or 0)
        cost = float(product["cost"] or 0)

        result["top_products"].append({
            "product_name": product["product_name"],
            "quantity": float(product["quantity"] or 0),
            "revenue": revenue,
            "cost": cost,
            "profit": revenue - cost
        })

    cur.close()
    conn.close()

    return jsonify(result)


# =========================================================
# RECIPE COST
# =========================================================

@app.get("/api/recipes/<int:recipe_id>/cost")
def recipe_cost(recipe_id):
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            r.id,
            r.name,
            r.sale_unit,

            COALESCE(
                SUM(
                    ri.quantity * i.price
                ),
                0
            ) AS cost

        FROM recipes r

        LEFT JOIN recipe_items ri
            ON ri.recipe_id = r.id

        LEFT JOIN inventory i
            ON i.id = ri.inventory_id

        WHERE r.id = %s

        GROUP BY
            r.id,
            r.name,
            r.sale_unit
    """, (recipe_id,))

    recipe = cur.fetchone()

    if not recipe:
        cur.close()
        conn.close()

        return jsonify({
            "error": "Retsept topilmadi"
        }), 404

    cur.execute("""
        SELECT
            i.name,
            i.unit,
            ri.quantity,
            i.price,
            ri.quantity * i.price AS cost
        FROM recipe_items ri

        JOIN inventory i
            ON i.id = ri.inventory_id

        WHERE ri.recipe_id = %s
    """, (recipe_id,))

    items = cur.fetchall()

    recipe["items"] = items

    recipe["cost"] = float(
        recipe["cost"] or 0
    )

    cur.close()
    conn.close()

    return jsonify(recipe)


# =========================================================
# TOP SELLING PRODUCTS
# =========================================================

@app.get("/api/top-products")
def top_products():
    period = request.args.get("period", "today")

    if period == "week":
        condition = """
            s.created_at >= CURRENT_DATE - INTERVAL '6 days'
        """
    elif period == "month":
        condition = """
            s.created_at >= DATE_TRUNC('month', CURRENT_DATE)
        """
    else:
        condition = """
            s.created_at >= CURRENT_DATE
        """

    conn = get_db()
    cur = conn.cursor()

    cur.execute(f"""
        SELECT
            s.product_name,
            SUM(s.quantity) AS quantity,
            SUM(s.total) AS revenue,

            SUM(
                s.quantity *
                COALESCE(recipe_cost.cost, 0)
            ) AS cost

        FROM sales s

        LEFT JOIN LATERAL (
            SELECT
                COALESCE(
                    SUM(
                        ri.quantity * i.price
                    ),
                    0
                ) AS cost

            FROM recipe_items ri

            JOIN inventory i
                ON i.id = ri.inventory_id

            WHERE ri.recipe_id = s.recipe_id
        ) recipe_cost
        ON TRUE

        WHERE {condition}

        GROUP BY s.product_name

        ORDER BY quantity DESC

        LIMIT 20
    """)

    rows = cur.fetchall()

    result = []

    for row in rows:
        revenue = float(row["revenue"] or 0)
        cost = float(row["cost"] or 0)

        result.append({
            "product_name": row["product_name"],
            "quantity": float(row["quantity"] or 0),
            "revenue": revenue,
            "cost": cost,
            "profit": revenue - cost
        })

    cur.close()
    conn.close()

    return jsonify(result)


# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))

    app.run(
        host="0.0.0.0",
        port=port
    )
