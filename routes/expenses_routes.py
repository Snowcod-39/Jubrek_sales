from flask import Blueprint, request, jsonify, session, render_template, redirect, url_for
from decimal import Decimal
from datetime import date


from db import get_db_connection


expenses_routes = Blueprint("expenses_routes", __name__)


# =========================================================
# ADD EXPENSE
# =========================================================

@expenses_routes.route("/api/expenses", methods=["POST"])
def add_expense():

    # User must be logged in
    if "user_id" not in session:
        return jsonify({"error": "Login required."}), 401

    data = request.get_json()

    if not data:
        return jsonify({"error": "No data provided."}), 400


    description = data.get("description")
    amount = data.get("amount")
    expense_date = data.get("expense_date")


    # -----------------------------------------------------
    # Validation
    # -----------------------------------------------------

    if not description:
        return jsonify({"error": "Description is required."}), 400

    if amount is None:
        return jsonify({"error": "Amount is required."}), 400

    if not expense_date:
        return jsonify({"error": "Expense date is required."}), 400


    try:
        amount = Decimal(str(amount))

    except Exception:
        return jsonify({"error": "Invalid amount."}), 400


    if amount <= 0:
        return jsonify({"error": "Amount must be greater than zero."}), 400


    try:
        expense_date = date.fromisoformat(expense_date)

    except ValueError:
        return jsonify({
            "error": "Invalid expense date. Use YYYY-MM-DD."
        }), 400


    connection = None

    try:

        connection = get_db_connection()
        cursor = connection.cursor()


        # -------------------------------------------------
        # Determine who created the expense
        # -------------------------------------------------

        created_by_admin_id = None
        created_by_employee_id = None


        if session.get("role") == "ADMIN":

            created_by_admin_id = session["user_id"]


        elif session.get("role") == "EMPLOYEE":

            created_by_employee_id = session["user_id"]


        else:

            return jsonify({
                "error": "Invalid user role."
            }), 403


        # -------------------------------------------------
        # Insert expense
        # -------------------------------------------------

        cursor.execute("""
            INSERT INTO expenses
            (
                description,
                amount,
                expense_date,
                created_by_admin_id,
                created_by_employee_id
            )
            VALUES
            (
                %s,
                %s,
                %s,
                %s,
                %s
            )
            RETURNING id;
        """, (
            description,
            amount,
            expense_date,
            created_by_admin_id,
            created_by_employee_id
        ))


        expense_id = cursor.fetchone()[0]


        connection.commit()


        return jsonify({
            "message": "Expense added successfully.",
            "expense_id": expense_id,
            "description": description,
            "amount": str(amount),
            "expense_date": expense_date.isoformat()
        }), 201


    except Exception as e:

        if connection:
            connection.rollback()

        print(
            "EXPENSE ADD ERROR:",
            type(e).__name__,
            str(e)
        )

        return jsonify({
            "error": "Could not add expense."
        }), 500


    finally:

        if connection:
            connection.close()



# =========================================================
# GET EXPENSES
# =========================================================

@expenses_routes.route("/api/expenses", methods=["GET"])
def get_expenses():

    if "user_id" not in session:
        return jsonify({"error": "Login required."}), 401


    connection = None

    try:

        connection = get_db_connection()
        cursor = connection.cursor()


        cursor.execute("""
            SELECT
                e.id,
                e.description,
                e.amount,
                e.expense_date,
                e.created_at,

                CASE
                    WHEN e.created_by_employee_id IS NOT NULL
                    THEN emp.full_name

                    WHEN e.created_by_admin_id IS NOT NULL
                    THEN adm.full_name

                    ELSE 'Unknown'
                END AS created_by,

                CASE
                    WHEN e.created_by_employee_id IS NOT NULL
                    THEN 'EMPLOYEE'

                    WHEN e.created_by_admin_id IS NOT NULL
                    THEN 'ADMIN'

                    ELSE 'UNKNOWN'
                END AS created_by_role

            FROM expenses e

            LEFT JOIN employees emp
                ON e.created_by_employee_id = emp.id

            LEFT JOIN admins adm
                ON e.created_by_admin_id = adm.id

            ORDER BY e.expense_date DESC, e.id DESC;
        """)


        rows = cursor.fetchall()


        expenses = []


        for row in rows:

            expenses.append({
                "id": row[0],
                "description": row[1],
                "amount": str(row[2]),
                "expense_date": row[3].isoformat(),
                "created_at": row[4].isoformat(),
                "created_by": row[5],
                "created_by_role": row[6]
            })


        return jsonify({
            "expenses": expenses
        })


    except Exception as e:

        print(
            "EXPENSE GET ERROR:",
            type(e).__name__,
            str(e)
        )

        return jsonify({
            "error": "Could not load expenses."
        }), 500


    finally:

        if connection:
            connection.close()

@expenses_routes.route("/expenses")
def expenses_page():

    if "user_id" not in session:
        return "Login required.", 401

    return render_template("expenses.html")