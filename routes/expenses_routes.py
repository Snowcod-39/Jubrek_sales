from flask import Blueprint, request, jsonify, session, render_template
from decimal import Decimal, InvalidOperation
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

    # Only ADMIN and EMPLOYEE can add expenses
    if session.get("role") not in ["ADMIN", "EMPLOYEE"]:
        return jsonify({"error": "Invalid user role."}), 403

    data = request.get_json()

    if not data:
        return jsonify({"error": "No data provided."}), 400

    description = data.get("description")
    amount = data.get("amount")
    expense_date = data.get("expense_date")

    # -----------------------------------------------------
    # Validation
    # -----------------------------------------------------

    if not description or not str(description).strip():
        return jsonify({"error": "Description is required."}), 400

    description = str(description).strip()

    if amount is None:
        return jsonify({"error": "Amount is required."}), 400

    if not expense_date:
        return jsonify({"error": "Expense date is required."}), 400

    try:
        amount = Decimal(str(amount))

    except (ValueError, TypeError, InvalidOperation):
        return jsonify({"error": "Invalid amount."}), 400

    if amount <= 0:
        return jsonify({
            "error": "Amount must be greater than zero."
        }), 400

    try:
        expense_date = date.fromisoformat(str(expense_date))

    except (ValueError, TypeError):
        return jsonify({
            "error": "Invalid expense date. Use YYYY-MM-DD."
        }), 400

    connection = None

    try:

        connection = get_db_connection()

        with connection.cursor() as cursor:

            # -------------------------------------------------
            # Determine who created the expense
            # -------------------------------------------------

            created_by_admin_id = None
            created_by_employee_id = None

            if session.get("role") == "ADMIN":

                created_by_admin_id = session["user_id"]

            elif session.get("role") == "EMPLOYEE":

                created_by_employee_id = session["user_id"]

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

    # User must be logged in
    if "user_id" not in session:
        return jsonify({"error": "Login required."}), 401

    role = session.get("role")

    if role not in ["ADMIN", "EMPLOYEE"]:
        return jsonify({"error": "Invalid user role."}), 403

    connection = None

    try:

        connection = get_db_connection()

        with connection.cursor() as cursor:

            # =================================================
            # EMPLOYEE
            # Only show expenses created by the logged-in
            # employee.
            # =================================================

            if role == "EMPLOYEE":

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

                    WHERE e.created_by_employee_id = %s

                    ORDER BY
                        e.expense_date DESC,
                        e.id DESC;
                """, (session["user_id"],))

            # =================================================
            # ADMIN
            # Admin can see ALL expenses.
            # =================================================

            else:

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

                    ORDER BY
                        e.expense_date DESC,
                        e.id DESC;
                """)

            rows = cursor.fetchall()

        # -----------------------------------------------------
        # Format response
        # -----------------------------------------------------

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


# =========================================================
# EXPENSE PAGE
# =========================================================

@expenses_routes.route("/expenses")
def expenses_page():

    if "user_id" not in session:
        return "Login required.", 401

    return render_template("expenses.html")