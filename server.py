import os
from flask import Flask, request, jsonify, send_from_directory
import psycopg2

app = Flask(__name__)


def get_db():
    return psycopg2.connect(
        os.environ["DATABASE_URL"]
    )


def init_db():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id SERIAL PRIMARY KEY,
            type VARCHAR(20) NOT NULL,
            amount NUMERIC(15, 2) NOT NULL,
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    cur.close()
    conn.close()


@app.route("/")
def home():
    return send_from_directory(".", "index.html")


@app.route("/api/transactions", methods=["POST"])
def add_transaction():

    data = request.get_json() or {}

    transaction_type = data.get("type")
    amount = data.get("amount")
    description = data.get("description", "")

    if transaction_type not in ["income", "expense"]:
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
        (transaction_type, amount, description)
    )

    transaction_id = cur.fetchone()[0]

    conn.commit()
    cur.close()
    conn.close()

    return jsonify({
        "success": True,
        "id": transaction_id
    })


@app.route("/api/summary", methods=["GET"])
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
                ), 0
            ),
            COALESCE(
                SUM(
                    CASE
                        WHEN type = 'expense'
                        THEN amount
                        ELSE 0
                    END
                ), 0
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


@app.route("/api/health")
def health():
    return jsonify({
        "status": "ok",
        "service": "Real CEO"
    })


# PostgreSQL jadvalini server ishga tushganda yaratish
try:
    init_db()
    print("✅ PostgreSQL bazasi tayyor.")
except Exception as error:
    print("❌ PostgreSQL bazasini ishga tushirishda xatolik:")
    print(error)
    raise


if __name__ == "__main__":

    port = int(
        os.environ.get("PORT", 8080)
    )

    app.run(
        host="0.0.0.0",
        port=port
    )
