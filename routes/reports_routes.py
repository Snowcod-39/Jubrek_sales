from flask import Blueprint, jsonify, session, render_template, request
from db import get_db_connection


reports_routes = Blueprint("reports_routes", __name__)


# =========================================================
# REPORT SUMMARY
# =========================================================

@reports_routes.route("/api/reports/summary", methods=["GET"])
def report_summary():

    if "user_id" not in session:
        return jsonify({"error": "Login required."}), 401


    # -----------------------------------------------------
    # Get requested report period
    # -----------------------------------------------------

    period = request.args.get("period", "daily").lower()


    allowed_periods = [
        "daily",
        "weekly",
        "monthly",
        "annually"
    ]


    if period not in allowed_periods:

        return jsonify({
            "error": "Invalid report period."
        }), 400


    connection = None


    try:

        connection = get_db_connection()
        cursor = connection.cursor()


        # -------------------------------------------------
        # Determine date filter
        # -------------------------------------------------

        if period == "daily":

            date_condition = """
                DATE(s.sale_date) = CURRENT_DATE
            """

            expense_date_condition = """
                e.expense_date = CURRENT_DATE
            """


        elif period == "weekly":

            date_condition = """
                s.sale_date >= DATE_TRUNC('week', CURRENT_DATE)
                AND s.sale_date < DATE_TRUNC('week', CURRENT_DATE)
                    + INTERVAL '1 week'
            """

            expense_date_condition = """
                e.expense_date >= DATE_TRUNC('week', CURRENT_DATE)
                AND e.expense_date < DATE_TRUNC('week', CURRENT_DATE)
                    + INTERVAL '1 week'
            """


        elif period == "monthly":

            date_condition = """
                s.sale_date >= DATE_TRUNC('month', CURRENT_DATE)
                AND s.sale_date < DATE_TRUNC('month', CURRENT_DATE)
                    + INTERVAL '1 month'
            """

            expense_date_condition = """
                e.expense_date >= DATE_TRUNC('month', CURRENT_DATE)
                AND e.expense_date < DATE_TRUNC('month', CURRENT_DATE)
                    + INTERVAL '1 month'
            """


        else:

            date_condition = """
                s.sale_date >= DATE_TRUNC('year', CURRENT_DATE)
                AND s.sale_date < DATE_TRUNC('year', CURRENT_DATE)
                    + INTERVAL '1 year'
            """

            expense_date_condition = """
                e.expense_date >= DATE_TRUNC('year', CURRENT_DATE)
                AND e.expense_date < DATE_TRUNC('year', CURRENT_DATE)
                    + INTERVAL '1 year'
            """


        # =================================================
        # SALES + PROFIT SUMMARY
        # =================================================

        cursor.execute(f"""
            SELECT
                COUNT(DISTINCT s.id) AS total_sales,

                COALESCE(
                    SUM(si.subtotal),
                    0
                ) AS sales_revenue,

                COALESCE(
                    SUM(
                        si.quantity * si.buying_price
                    ),
                    0
                ) AS cost_of_goods_sold

            FROM sales s

            LEFT JOIN sale_items si
                ON s.id = si.sale_id

            WHERE {date_condition};
        """)


        sales_data = cursor.fetchone()


        total_sales = sales_data[0]
        sales_revenue = sales_data[1]
        cost_of_goods_sold = sales_data[2]


        # =================================================
        # EXPENSE SUMMARY
        # =================================================

        cursor.execute(f"""
            SELECT
                COUNT(*) AS total_expenses,

                COALESCE(
                    SUM(e.amount),
                    0
                ) AS total_expenses_amount

            FROM expenses e

            WHERE {expense_date_condition};
        """)


        expense_data = cursor.fetchone()


        total_expenses = expense_data[0]
        total_expenses_amount = expense_data[1]


        # =================================================
        # PROFIT CALCULATIONS
        # =================================================

        gross_profit = (
            sales_revenue
            - cost_of_goods_sold
        )


        net_profit = (
            gross_profit
            - total_expenses_amount
        )


        # =================================================
        # SALES BY EMPLOYEE
        # =================================================

        cursor.execute(f"""
            SELECT
                emp.id,
                emp.full_name,

                COUNT(DISTINCT s.id)
                    AS number_of_sales,

                COALESCE(
                    SUM(si.subtotal),
                    0
                ) AS total_sales_amount

            FROM employees emp

            LEFT JOIN sales s
                ON emp.id = s.employee_id
                AND {date_condition}

            LEFT JOIN sale_items si
                ON s.id = si.sale_id

            GROUP BY
                emp.id,
                emp.full_name

            ORDER BY
                total_sales_amount DESC;
        """)


        employee_rows = cursor.fetchall()


        sales_by_employee = []


        for row in employee_rows:

            sales_by_employee.append({

                "employee_id": row[0],

                "employee_name": row[1],

                "number_of_sales": row[2],

                "total_sales_amount":
                    str(row[3])
            })


        # =================================================
        # EXPENSES BY EMPLOYEE
        # =================================================

        cursor.execute(f"""
            SELECT
                emp.id,
                emp.full_name,

                COUNT(e.id)
                    AS number_of_expenses,

                COALESCE(
                    SUM(e.amount),
                    0
                ) AS total_expense_amount

            FROM employees emp

            LEFT JOIN expenses e
                ON emp.id = e.created_by_employee_id
                AND {expense_date_condition}

            GROUP BY
                emp.id,
                emp.full_name

            ORDER BY
                total_expense_amount DESC;
        """)


        expense_employee_rows = cursor.fetchall()


        expenses_by_employee = []


        for row in expense_employee_rows:

            expenses_by_employee.append({

                "employee_id": row[0],

                "employee_name": row[1],

                "number_of_expenses": row[2],

                "total_expense_amount":
                    str(row[3])
            })


        # =================================================
        # RESPONSE
        # =================================================

        return jsonify({

            "period": period,

            "summary": {

                "total_sales":
                    total_sales,

                "sales_revenue":
                    str(sales_revenue),

                "cost_of_goods_sold":
                    str(cost_of_goods_sold),

                "gross_profit":
                    str(gross_profit),

                "total_expenses":
                    total_expenses,

                "total_expense_amount":
                    str(total_expenses_amount),

                "net_profit":
                    str(net_profit)
            },

            "sales_by_employee":
                sales_by_employee,

            "expenses_by_employee":
                expenses_by_employee

        })


    except Exception as e:

        print(
            "REPORT ERROR:",
            type(e).__name__,
            str(e)
        )

        return jsonify({
            "error": "Could not generate report."
        }), 500


    finally:

        if connection:
            connection.close()


# =========================================================
# REPORT PAGE
# =========================================================

@reports_routes.route("/reports")
def reports_page():

    if "user_id" not in session:
        return "Login required.", 401

    return render_template("reports.html")
