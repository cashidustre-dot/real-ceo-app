import os

from flask import Flask, request, jsonify, send_from_directory
import psycopg2


app = Flask(__name__)


# =========================================================
# DATABASE
# =========================================================

def get_db():
    return psycopg2.connect(
        os.environ["DATABASE_URL"]
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
            amount NUMERIC(15, 2) NOT NULL,
            description TEXT,
            sale_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Eski bazada transactions allaqachon mavjud bo'lsa,
    # sale_id ustunini qo'shamiz.
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
            name VARCHAR(150) NOT NULL,
            unit VARCHAR(30) NOT NULL,
            quantity NUMERIC(15, 3) NOT NULL DEFAULT 0,
            min_quantity NUMERIC(15, 3) NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        ALTER TABLE inventory
        ADD COLUMN IF NOT EXISTS price NUMERIC(15, 2)
        NOT NULL DEFAULT 0
    """)

    # =====================================================
    # EMPLOYEES
    # =====================================================

    cur.execute("""
        CREATE TABLE IF NOT EXISTS employees (
            id SERIAL PRIMARY KEY,
            name VARCHAR(150) NOT NULL,
            position VARCHAR(100) NOT NULL,
            salary NUMERIC(15, 2) NOT NULL DEFAULT 0,
            hire_date DATE DEFAULT CURRENT_DATE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # =====================================================
    # SALES
    # =====================================================

    cur.execute("""
        CREATE TABLE IF NOT EXISTS sales (
            id SERIAL PRIMARY KEY,
            product_name VARCHAR(150) NOT NULL,
            quantity NUMERIC(15, 3) NOT NULL DEFAULT 1,
            unit_price NUMERIC(15, 2) NOT NULL DEFAULT 0,
            total_amount NUMERIC(15, 2) NOT NULL DEFAULT 0,
            payment_method VARCHAR(30) NOT NULL DEFAULT 'cash',
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()

    cur.close()
    conn.close()


# =========================================================
# HOME
# =========================================================

@app.route("/")
def home():

    return send_from_directory(
        ".",
        "index.html"
    )


# =========================================================
# TRANSACTIONS - ADD
# =========================================================

@app.route(
    "/api/transactions",
    methods=["POST"]
)
def add_transaction():

    data = request.get_json() or {}

    transaction_type = data.get("type")
    amount = data.get("amount")
    description = data.get(
        "description",
        ""
    )

    if transaction_type not in [
        "income",
        "expense"
    ]:

        return jsonify({
            "success": False,
            "error": "Noto'g'ri transaction turi"
        }), 400

    try:

        amount = float(amount)

    except (TypeError, ValueError):

        return jsonify({
            "success": False,
            "error": "Summa noto'g'ri"
        }), 400

    if amount <= 0:

        return jsonify({
            "success": False,
            "error": "Summa 0 dan katta bo'lishi kerak"
        }), 400

    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        """
        INSERT INTO transactions
        (type, amount, description)
        VALUES (%s, %s, %s)
        RETURNING id
        """,
        (
            transaction_type,
            amount,
            description
        )
    )

    transaction_id = cur.fetchone()[0]

    conn.commit()

    cur.close()
    conn.close()

    return jsonify({
        "success": True,
        "id": transaction_id
    })


# =========================================================
# TRANSACTIONS - GET
# =========================================================

@app.route(
    "/api/transactions",
    methods=["GET"]
)
def get_transactions():

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            id,
            type,
            amount,
            description,
            created_at
        FROM transactions
        ORDER BY created_at DESC
        LIMIT 100
    """)

    rows = cur.fetchall()

    cur.close()
    conn.close()

    transactions = []

    for row in rows:

        transactions.append({
            "id": row[0],
            "type": row[1],
            "amount": float(row[2]),
            "description": row[3] or "",
            "created_at": row[4].isoformat()
        })

    return jsonify({
        "success": True,
        "transactions": transactions
    })


# =========================================================
# TRANSACTIONS - DELETE
# =========================================================

@app.route(
    "/api/transactions/<int:transaction_id>",
    methods=["DELETE"]
)
def delete_transaction(transaction_id):

    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        """
        DELETE FROM transactions
        WHERE id = %s
        RETURNING id
        """,
        (transaction_id,)
    )

    result = cur.fetchone()

    if not result:

        conn.rollback()

        cur.close()
        conn.close()

        return jsonify({
            "success": False,
            "error": "Tranzaksiya topilmadi"
        }), 404

    conn.commit()

    cur.close()
    conn.close()

    return jsonify({
        "success": True
    })


# =========================================================
# SUMMARY
# =========================================================

@app.route(
    "/api/summary",
    methods=["GET"]
)
def summary():

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            COALESCE(
                SUM(
                    CASE
                        WHEN type = 'income'
                        THEN amount
                        ELSE 0
                    END
                ),
                0
            ),
            COALESCE(
                SUM(
                    CASE
                        WHEN type = 'expense'
                        THEN amount
                        ELSE 0
                    END
                ),
                0
            )
        FROM transactions
    """)

    income, expense = cur.fetchone()

    cur.close()
    conn.close()

    return jsonify({
        "income": float(income),
        "expense": float(expense),
        "profit": float(income - expense)
    })


# =========================================================
# REPORT
# =========================================================

@app.route(
    "/api/report",
    methods=["GET"]
)
def report():

    period = request.args.get(
        "period",
        "today"
    )

    conn = get_db()
    cur = conn.cursor()

    if period == "today":

        condition = """
            created_at >= CURRENT_DATE
        """

    elif period == "week":

        condition = """
            created_at >= CURRENT_DATE - INTERVAL '6 days'
        """

    elif period == "month":

        condition = """
            created_at >= DATE_TRUNC(
                'month',
                CURRENT_DATE
            )
        """

    else:

        cur.close()
        conn.close()

        return jsonify({
            "success": False,
            "error": "Noto'g'ri hisobot davri"
        }), 400

    query = f"""
        SELECT
            COALESCE(
                SUM(
                    CASE
                        WHEN type = 'income'
                        THEN amount
                        ELSE 0
                    END
                ),
                0
            ),
            COALESCE(
                SUM(
                    CASE
                        WHEN type = 'expense'
                        THEN amount
                        ELSE 0
                    END
                ),
                0
            ),
            COUNT(*)
        FROM transactions
        WHERE {condition}
    """

    cur.execute(query)

    income, expense, transaction_count = cur.fetchone()

    cur.close()
    conn.close()

    income = float(income)
    expense = float(expense)

    return jsonify({
        "success": True,
        "period": period,
        "income": income,
        "expense": expense,
        "profit": income - expense,
        "transaction_count": transaction_count
    })


# =========================================================
# INVENTORY - ADD
# =========================================================

@app.route(
    "/api/inventory",
    methods=["POST"]
)
def add_product():

    data = request.get_json() or {}

    name = str(
        data.get("name", "")
    ).strip()

    unit = str(
        data.get("unit", "")
    ).strip()

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

    if not name:

        return jsonify({
            "success": False,
            "error": "Mahsulot nomini kiriting"
        }), 400

    if not unit:

        return jsonify({
            "success": False,
            "error": "O'lchov birligini kiriting"
        }), 400

    try:

        quantity = float(quantity)
        min_quantity = float(min_quantity)
        price = float(price)

    except (TypeError, ValueError):

        return jsonify({
            "success": False,
            "error": "Miqdor yoki narx noto'g'ri"
        }), 400

    if quantity < 0 or min_quantity < 0 or price < 0:

        return jsonify({
            "success": False,
            "error": "Qiymatlar manfiy bo'lishi mumkin emas"
        }), 400

    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        """
        INSERT INTO inventory
        (name, unit, quantity, min_quantity, price)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING id
        """,
        (
            name,
            unit,
            quantity,
            min_quantity,
            price
        )
    )

    product_id = cur.fetchone()[0]

    conn.commit()

    cur.close()
    conn.close()

    return jsonify({
        "success": True,
        "id": product_id
    })


# =========================================================
# INVENTORY - GET
# =========================================================

@app.route(
    "/api/inventory",
    methods=["GET"]
)
def get_inventory():

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            id,
            name,
            unit,
            quantity,
            min_quantity,
            price,
            created_at
        FROM inventory
        ORDER BY name ASC
    """)

    rows = cur.fetchall()

    cur.close()
    conn.close()

    products = []

    for row in rows:

        quantity = float(row[3])
        price = float(row[5])

        products.append({
            "id": row[0],
            "name": row[1],
            "unit": row[2],
            "quantity": quantity,
            "min_quantity": float(row[4]),
            "price": price,
            "total_value": quantity * price,
            "created_at": row[6].isoformat()
        })

    return jsonify({
        "success": True,
        "products": products
    })


# =========================================================
# INVENTORY - SUMMARY
# =========================================================

@app.route(
    "/api/inventory/summary",
    methods=["GET"]
)
def inventory_summary():

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            COUNT(*),
            COALESCE(
                SUM(quantity * price),
                0
            )
        FROM inventory
    """)

    product_count, total_value = cur.fetchone()

    cur.execute("""
        SELECT
            COUNT(*)
        FROM inventory
        WHERE quantity <= min_quantity
    """)

    low_stock_count = cur.fetchone()[0]

    cur.close()
    conn.close()

    return jsonify({
        "success": True,
        "product_count": product_count,
        "total_value": float(total_value),
        "low_stock_count": low_stock_count
    })


# =========================================================
# INVENTORY - UPDATE PRICE
# =========================================================

@app.route(
    "/api/inventory/<int:product_id>/price",
    methods=["PUT"]
)
def update_price(product_id):

    data = request.get_json() or {}

    price = data.get("price")

    try:

        price = float(price)

    except (TypeError, ValueError):

        return jsonify({
            "success": False,
            "error": "Narx noto'g'ri"
        }), 400

    if price < 0:

        return jsonify({
            "success": False,
            "error": "Narx manfiy bo'lishi mumkin emas"
        }), 400

    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        """
        UPDATE inventory
        SET price = %s
        WHERE id = %s
        RETURNING id, price
        """,
        (
            price,
            product_id
        )
    )

    result = cur.fetchone()

    if not result:

        conn.rollback()
        cur.close()
        conn.close()

        return jsonify({
            "success": False,
            "error": "Mahsulot topilmadi"
        }), 404

    conn.commit()

    cur.close()
    conn.close()

    return jsonify({
        "success": True,
        "id": result[0],
        "price": float(result[1])
    })


# =========================================================
# INVENTORY - STOCK IN
# =========================================================

@app.route(
    "/api/inventory/<int:product_id>/in",
    methods=["POST"]
)
def stock_in(product_id):

    data = request.get_json() or {}

    amount = data.get("amount")

    try:

        amount = float(amount)

    except (TypeError, ValueError):

        return jsonify({
            "success": False,
            "error": "Kirim miqdori noto'g'ri"
        }), 400

    if amount <= 0:

        return jsonify({
            "success": False,
            "error": "Miqdor 0 dan katta bo'lishi kerak"
        }), 400

    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        """
        UPDATE inventory
        SET quantity = quantity + %s
        WHERE id = %s
        RETURNING id, quantity
        """,
        (
            amount,
            product_id
        )
    )

    result = cur.fetchone()

    if not result:

        conn.rollback()
        cur.close()
        conn.close()

        return jsonify({
            "success": False,
            "error": "Mahsulot topilmadi"
        }), 404

    conn.commit()

    new_quantity = float(result[1])

    cur.close()
    conn.close()

    return jsonify({
        "success": True,
        "id": result[0],
        "quantity": new_quantity
    })


# =========================================================
# INVENTORY - STOCK OUT
# =========================================================

@app.route(
    "/api/inventory/<int:product_id>/out",
    methods=["POST"]
)
def stock_out(product_id):

    data = request.get_json() or {}

    amount = data.get("amount")

    try:

        amount = float(amount)

    except (TypeError, ValueError):

        return jsonify({
            "success": False,
            "error": "Chiqim miqdori noto'g'ri"
        }), 400

    if amount <= 0:

        return jsonify({
            "success": False,
            "error": "Miqdor 0 dan katta bo'lishi kerak"
        }), 400

    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        """
        UPDATE inventory
        SET quantity = quantity - %s
        WHERE id = %s
        AND quantity >= %s
        RETURNING id, quantity
        """,
        (
            amount,
            product_id,
            amount
        )
    )

    result = cur.fetchone()

    if not result:

        conn.rollback()
        cur.close()
        conn.close()

        return jsonify({
            "success": False,
            "error": "Omborda yetarli mahsulot mavjud emas"
        }), 400

    conn.commit()

    new_quantity = float(result[1])

    cur.close()
    conn.close()

    return jsonify({
        "success": True,
        "id": result[0],
        "quantity": new_quantity
    })


# =========================================================
# INVENTORY - DELETE
# =========================================================

@app.route(
    "/api/inventory/<int:product_id>",
    methods=["DELETE"]
)
def delete_product(product_id):

    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        """
        DELETE FROM inventory
        WHERE id = %s
        RETURNING id
        """,
        (product_id,)
    )

    result = cur.fetchone()

    if not result:

        conn.rollback()
        cur.close()
        conn.close()

        return jsonify({
            "success": False,
            "error": "Mahsulot topilmadi"
        }), 404

    conn.commit()

    cur.close()
    conn.close()

    return jsonify({
        "success": True
    })


# =========================================================
# EMPLOYEES - ADD
# =========================================================

@app.route(
    "/api/employees",
    methods=["POST"]
)
def add_employee():

    data = request.get_json() or {}

    name = str(
        data.get("name", "")
    ).strip()

    position = str(
        data.get("position", "")
    ).strip()

    salary = data.get(
        "salary",
        0
    )

    hire_date = data.get(
        "hire_date"
    )

    if not name:

        return jsonify({
            "success": False,
            "error": "Xodim ismini kiriting"
        }), 400

    if not position:

        return jsonify({
            "success": False,
            "error": "Lavozimni kiriting"
        }), 400

    try:

        salary = float(salary)

    except (TypeError, ValueError):

        return jsonify({
            "success": False,
            "error": "Oylik maoshi noto'g'ri"
        }), 400

    if salary < 0:

        return jsonify({
            "success": False,
            "error": "Oylik maoshi manfiy bo'lishi mumkin emas"
        }), 400

    conn = get_db()
    cur = conn.cursor()

    if hire_date:

        cur.execute(
            """
            INSERT INTO employees
            (name, position, salary, hire_date)
            VALUES (%s, %s, %s, %s)
            RETURNING id
            """,
            (
                name,
                position,
                salary,
                hire_date
            )
        )

    else:

        cur.execute(
            """
            INSERT INTO employees
            (name, position, salary)
            VALUES (%s, %s, %s)
            RETURNING id
            """,
            (
                name,
                position,
                salary
            )
        )

    employee_id = cur.fetchone()[0]

    conn.commit()

    cur.close()
    conn.close()

    return jsonify({
        "success": True,
        "id": employee_id
    })


# =========================================================
# EMPLOYEES - GET
# =========================================================

@app.route(
    "/api/employees",
    methods=["GET"]
)
def get_employees():

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            id,
            name,
            position,
            salary,
            hire_date,
            created_at
        FROM employees
        ORDER BY name ASC
    """)

    rows = cur.fetchall()

    cur.close()
    conn.close()

    employees = []

    for row in rows:

        employees.append({
            "id": row[0],
            "name": row[1],
            "position": row[2],
            "salary": float(row[3]),
            "hire_date": (
                row[4].isoformat()
                if row[4]
                else None
            ),
            "created_at": row[5].isoformat()
        })

    return jsonify({
        "success": True,
        "employees": employees
    })


# =========================================================
# EMPLOYEES - SUMMARY
# =========================================================

@app.route(
    "/api/employees/summary",
    methods=["GET"]
)
def employees_summary():

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            COUNT(*),
            COALESCE(
                SUM(salary),
                0
            )
        FROM employees
    """)

    employee_count, total_salary = cur.fetchone()

    cur.close()
    conn.close()

    return jsonify({
        "success": True,
        "employee_count": employee_count,
        "total_salary": float(total_salary)
    })


# =========================================================
# EMPLOYEES - UPDATE
# =========================================================

@app.route(
    "/api/employees/<int:employee_id>",
    methods=["PUT"]
)
def update_employee(employee_id):

    data = request.get_json() or {}

    name = str(
        data.get("name", "")
    ).strip()

    position = str(
        data.get("position", "")
    ).strip()

    salary = data.get(
        "salary",
        0
    )

    hire_date = data.get(
        "hire_date"
    )

    if not name or not position:

        return jsonify({
            "success": False,
            "error": "Ism va lavozimni kiriting"
        }), 400

    try:

        salary = float(salary)

    except (TypeError, ValueError):

        return jsonify({
            "success": False,
            "error": "Oylik maoshi noto'g'ri"
        }), 400

    if salary < 0:

        return jsonify({
            "success": False,
            "error": "Oylik manfiy bo'lishi mumkin emas"
        }), 400

    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        """
        UPDATE employees
        SET
            name = %s,
            position = %s,
            salary = %s,
            hire_date = COALESCE(%s, hire_date)
        WHERE id = %s
        RETURNING id
        """,
        (
            name,
            position,
            salary,
            hire_date,
            employee_id
        )
    )

    result = cur.fetchone()

    if not result:

        conn.rollback()
        cur.close()
        conn.close()

        return jsonify({
            "success": False,
            "error": "Xodim topilmadi"
        }), 404

    conn.commit()

    cur.close()
    conn.close()

    return jsonify({
        "success": True,
        "id": result[0]
    })


# =========================================================
# EMPLOYEES - DELETE
# =========================================================

@app.route(
    "/api/employees/<int:employee_id>",
    methods=["DELETE"]
)
def delete_employee(employee_id):

    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        """
        DELETE FROM employees
        WHERE id = %s
        RETURNING id
        """,
        (employee_id,)
    )

    result = cur.fetchone()

    if not result:

        conn.rollback()
        cur.close()
        conn.close()

        return jsonify({
            "success": False,
            "error": "Xodim topilmadi"
        }), 404

    conn.commit()

    cur.close()
    conn.close()

    return jsonify({
        "success": True
    })


# =========================================================
# SALES - ADD
# =========================================================

@app.route(
    "/api/sales",
    methods=["POST"]
)
def add_sale():

    data = request.get_json() or {}

    product_name = str(
        data.get("product_name", "")
    ).strip()

    quantity = data.get(
        "quantity",
        1
    )

    unit_price = data.get(
        "unit_price",
        0
    )

    payment_method = str(
        data.get(
            "payment_method",
            "cash"
        )
    ).strip()

    description = str(
        data.get(
            "description",
            ""
        )
    ).strip()

    if not product_name:

        return jsonify({
            "success": False,
            "error": "Mahsulot yoki taom nomini kiriting"
        }), 400

    try:

        quantity = float(quantity)
        unit_price = float(unit_price)

    except (TypeError, ValueError):

        return jsonify({
            "success": False,
            "error": "Miqdor yoki narx noto'g'ri"
        }), 400

    if quantity <= 0:

        return jsonify({
            "success": False,
            "error": "Miqdor 0 dan katta bo'lishi kerak"
        }), 400

    if unit_price < 0:

        return jsonify({
            "success": False,
            "error": "Narx manfiy bo'lishi mumkin emas"
        }), 400

    allowed_payments = [
        "cash",
        "card",
        "other"
    ]

    if payment_method not in allowed_payments:

        return jsonify({
            "success": False,
            "error": "To'lov turi noto'g'ri"
        }), 400

    total_amount = quantity * unit_price

    conn = get_db()
    cur = conn.cursor()

    # Avval savdoni yaratamiz
    cur.execute(
        """
        INSERT INTO sales
        (
            product_name,
            quantity,
            unit_price,
            total_amount,
            payment_method,
            description
        )
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (
            product_name,
            quantity,
            unit_price,
            total_amount,
            payment_method,
            description
        )
    )

    sale_id = cur.fetchone()[0]

    # Savdo daromadini aynan shu sale_id bilan bog'laymiz
    cur.execute(
        """
        INSERT INTO transactions
        (
            type,
            amount,
            description,
            sale_id
        )
        VALUES (%s, %s, %s, %s)
        RETURNING id
        """,
        (
            "income",
            total_amount,
            f"Savdo: {product_name}",
            sale_id
        )
    )

    transaction_id = cur.fetchone()[0]

    conn.commit()

    cur.close()
    conn.close()

    return jsonify({
        "success": True,
        "id": sale_id,
        "transaction_id": transaction_id,
        "total_amount": total_amount
    })


# =========================================================
# SALES - GET
# =========================================================

@app.route(
    "/api/sales",
    methods=["GET"]
)
def get_sales():

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            id,
            product_name,
            quantity,
            unit_price,
            total_amount,
            payment_method,
            description,
            created_at
        FROM sales
        ORDER BY created_at DESC
        LIMIT 100
    """)

    rows = cur.fetchall()

    cur.close()
    conn.close()

    sales = []

    for row in rows:

        sales.append({
            "id": row[0],
            "product_name": row[1],
            "quantity": float(row[2]),
            "unit_price": float(row[3]),
            "total_amount": float(row[4]),
            "payment_method": row[5],
            "description": row[6] or "",
            "created_at": row[7].isoformat()
        })

    return jsonify({
        "success": True,
        "sales": sales
    })


# =========================================================
# SALES - SUMMARY
# =========================================================

@app.route(
    "/api/sales/summary",
    methods=["GET"]
)
def sales_summary():

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            COALESCE(
                SUM(total_amount),
                0
            ),
            COUNT(*)
        FROM sales
        WHERE created_at >= CURRENT_DATE
    """)

    today_total, today_count = cur.fetchone()

    cur.execute("""
        SELECT
            COALESCE(
                SUM(total_amount),
                0
            )
        FROM sales
        WHERE created_at >=
            CURRENT_DATE - INTERVAL '6 days'
    """)

    week_total = cur.fetchone()[0]

    cur.execute("""
        SELECT
            COALESCE(
                SUM(total_amount),
                0
            )
        FROM sales
        WHERE created_at >=
            DATE_TRUNC(
                'month',
                CURRENT_DATE
            )
    """)

    month_total = cur.fetchone()[0]

    cur.execute("""
        SELECT
            COALESCE(
                SUM(total_amount),
                0
            )
        FROM sales
        WHERE payment_method = 'cash'
    """)

    cash_total = cur.fetchone()[0]

    cur.execute("""
        SELECT
            COALESCE(
                SUM(total_amount),
                0
            )
        FROM sales
        WHERE payment_method = 'card'
    """)

    card_total = cur.fetchone()[0]

    cur.close()
    conn.close()

    return jsonify({
        "success": True,
        "today_total": float(today_total),
        "today_count": today_count,
        "week_total": float(week_total),
        "month_total": float(month_total),
        "cash_total": float(cash_total),
        "card_total": float(card_total)
    })


# =========================================================
# SALES - DELETE
# =========================================================

@app.route(
    "/api/sales/<int:sale_id>",
    methods=["DELETE"]
)
def delete_sale(sale_id):

    conn = get_db()
    cur = conn.cursor()

    # Savdoni topamiz
    cur.execute(
        """
        SELECT
            product_name,
            total_amount
        FROM sales
        WHERE id = %s
        """,
        (sale_id,)
    )

    sale = cur.fetchone()

    if not sale:

        cur.close()
        conn.close()

        return jsonify({
            "success": False,
            "error": "Savdo topilmadi"
        }), 404

    product_name = sale[0]
    total_amount = float(sale[1])

    # Eng avval aynan sale_id bilan bog'langan
    # transactionni o'chiramiz.
    cur.execute(
        """
        DELETE FROM transactions
        WHERE sale_id = %s
        """,
        (sale_id,)
    )

    # Eski versiyada yaratilgan savdolar uchun
    # sale_id bo'lmagan bo'lishi mumkin.
    # Ular uchun xavfsizroq fallback:
    # aynan summa + savdo nomi bo'yicha eng oxirgi
    # mos daromadni o'chiramiz.
    cur.execute(
        """
        DELETE FROM transactions
        WHERE id = (
            SELECT id
            FROM transactions
            WHERE sale_id IS NULL
              AND type = 'income'
              AND amount = %s
              AND description = %s
            ORDER BY created_at DESC
            LIMIT 1
        )
        """,
        (
            total_amount,
            f"Savdo: {product_name}"
        )
    )

    # Savdoni o'chiramiz
    cur.execute(
        """
        DELETE FROM sales
        WHERE id = %s
        RETURNING id
        """,
        (sale_id,)
    )

    conn.commit()

    cur.close()
    conn.close()

    return jsonify({
        "success": True
    })


# =========================================================
# HEALTH
# =========================================================

@app.route("/api/health")
def health():

    return jsonify({
        "status": "ok",
        "service": "Real CEO"
    })


# =========================================================
# DATABASE INITIALIZATION
# =========================================================

try:

    init_db()

    print(
        "PostgreSQL bazasi tayyor."
    )

except Exception as error:

    print(
        "PostgreSQL bazasini ishga tushirishda xatolik:"
    )

    print(error)

    raise


# =========================================================
# LOCAL START
# =========================================================

if __name__ == "__main__":

    port = int(
        os.environ.get(
            "PORT",
            8080
        )
    )

    app.run(
        host="0.0.0.0",
        port=port
    )
