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
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
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

    # =====================================================
    # INVENTORY PRICE
    # =====================================================

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
# ADD TRANSACTION
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
# GET TRANSACTIONS
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
        LIMIT 50
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
# INVENTORY - ADD PRODUCT
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

    if quantity < 0:

        return jsonify({
            "success": False,
            "error": "Miqdor manfiy bo'lishi mumkin emas"
        }), 400

    if min_quantity < 0:

        return jsonify({
            "success": False,
            "error": "Minimal qoldiq manfiy bo'lishi mumkin emas"
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
# INVENTORY - GET PRODUCTS
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

    new_quantity = float(
        result[1]
    )

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

    new_quantity = float(
        result[1]
    )

    cur.close()
    conn.close()

    return jsonify({
        "success": True,
        "id": result[0],
        "quantity": new_quantity
    })


# =========================================================
# INVENTORY - DELETE PRODUCT
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
# HEALTH CHECK
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
