from flask import Blueprint, jsonify, session, render_template, request
from db import get_db_connection
from datetime import datetime


reports_routes = Blueprint("reports_routes", __name__)


# =========================================================
# BUSINESS TIMEZONE
# =========================================================

BUSINESS_TIMEZONE = "Africa/Nairobi"


# =========================================================
# ADMIN CHECK
# =========================================================

def admin_required():
    return (
        "user_id" in session
        and session.get("role") == "ADMIN"
    )


# =========================================================
# REPORT SUMMARY
# =========================================================

@reports_routes.route("/api/reports/summary", methods=["GET"])
def report_summary():

    if not admin_required():
        return jsonify({
            "error": "Admin access required."
        }), 403

    # -----------------------------------------------------
    # Get requested report period
    # -----------------------------------------------------

    period = request.args.get(
        "period",
        "daily"
    ).lower()

    allowed_periods = [
        "daily",
        "weekly",
        "monthly",
        "annually",
        "all"
    ]

    if period not in allowed_periods:
        return jsonify({
            "error": "Invalid report period."
        }), 400

    # -----------------------------------------------------
    # Optional calendar date
    # -----------------------------------------------------

    selected_date = request.args.get("date")

    if selected_date:
        try:
            selected_date = datetime.strptime(
                selected_date,
                "%Y-%m-%d"
            ).date()

        except ValueError:
            return jsonify({
                "error": "Invalid date. Use YYYY-MM-DD."
            }), 400

    connection = None

    try:

        connection = get_db_connection()
        cursor = connection.cursor()

        # =================================================
        # IMPORTANT:
        # All "today" calculations use AFRICA/NAIROBI.
        #
        # This prevents Railway/PostgreSQL's server timezone
        # from changing which business day a transaction
        # belongs to.
        # =================================================

        nairobi_today_sql = """
            (CURRENT_TIMESTAMP AT TIME ZONE 'Africa/Nairobi')::date
        """

        # =================================================
        # DETERMINE DATE FILTER
        # =================================================

        if selected_date:

            # -------------------------------------------------
            # Specific date selected from calendar
            # -------------------------------------------------

            date_condition = """
                (s.sale_date AT TIME ZONE 'Africa/Nairobi')::date = %s
            """

            expense_date_condition = """
                e.expense_date = %s
            """

            date_params = [selected_date]
            expense_date_params = [selected_date]

            response_period = "selected_date"

        elif period == "daily":

            # -------------------------------------------------
            # Today in Kenya
            # -------------------------------------------------

            date_condition = f"""
                (s.sale_date AT TIME ZONE 'Africa/Nairobi')::date =
                {nairobi_today_sql}
            """

            expense_date_condition = f"""
                e.expense_date =
                {nairobi_today_sql}
            """

            date_params = []
            expense_date_params = []

            response_period = "daily"

        elif period == "weekly":

            # -------------------------------------------------
            # Current week in Kenya
            #
            # DATE_TRUNC is applied to the Nairobi local date,
            # not the Railway/PostgreSQL server date.
            # -------------------------------------------------

            date_condition = f"""
                (s.sale_date AT TIME ZONE 'Africa/Nairobi')::date >=
                DATE_TRUNC(
                    'week',
                    {nairobi_today_sql}
                )::date

                AND

                (s.sale_date AT TIME ZONE 'Africa/Nairobi')::date <
                (
                    DATE_TRUNC(
                        'week',
                        {nairobi_today_sql}
                    ) + INTERVAL '1 week'
                )::date
            """

            expense_date_condition = f"""
                e.expense_date >=
                DATE_TRUNC(
                    'week',
                    {nairobi_today_sql}
                )::date

                AND

                e.expense_date <
                (
                    DATE_TRUNC(
                        'week',
                        {nairobi_today_sql}
                    ) + INTERVAL '1 week'
                )::date
            """

            date_params = []
            expense_date_params = []

            response_period = "weekly"

        elif period == "monthly":

            # -------------------------------------------------
            # Current month in Kenya
            # -------------------------------------------------

            date_condition = f"""
                (s.sale_date AT TIME ZONE 'Africa/Nairobi')::date >=
                DATE_TRUNC(
                    'month',
                    {nairobi_today_sql}
                )::date

                AND

                (s.sale_date AT TIME ZONE 'Africa/Nairobi')::date <
                (
                    DATE_TRUNC(
                        'month',
                        {nairobi_today_sql}
                    ) + INTERVAL '1 month'
                )::date
            """

            expense_date_condition = f"""
                e.expense_date >=
                DATE_TRUNC(
                    'month',
                    {nairobi_today_sql}
                )::date

                AND

                e.expense_date <
                (
                    DATE_TRUNC(
                        'month',
                        {nairobi_today_sql}
                    ) + INTERVAL '1 month'
                )::date
            """

            date_params = []
            expense_date_params = []

            response_period = "monthly"

        elif period == "annually":

            # -------------------------------------------------
            # Current year in Kenya
            # -------------------------------------------------

            date_condition = f"""
                (s.sale_date AT TIME ZONE 'Africa/Nairobi')::date >=
                DATE_TRUNC(
                    'year',
                    {nairobi_today_sql}
                )::date

                AND

                (s.sale_date AT TIME ZONE 'Africa/Nairobi')::date <
                (
                    DATE_TRUNC(
                        'year',
                        {nairobi_today_sql}
                    ) + INTERVAL '1 year'
                )::date
            """

            expense_date_condition = f"""
                e.expense_date >=
                DATE_TRUNC(
                    'year',
                    {nairobi_today_sql}
                )::date

                AND

                e.expense_date <
                (
                    DATE_TRUNC(
                        'year',
                        {nairobi_today_sql}
                    ) + INTERVAL '1 year'
                )::date
            """

            date_params = []
            expense_date_params = []

            response_period = "annually"

        else:

            # -------------------------------------------------
            # ALL RECORDS
            # -------------------------------------------------

            date_condition = """
                TRUE
            """

            expense_date_condition = """
                TRUE
            """

            date_params = []
            expense_date_params = []

            response_period = "all"

        # =================================================
        # SALES + PROFIT SUMMARY
        # =================================================

        sales_query = f"""
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

            WHERE
                {date_condition}

                AND s.delivery_status = 'RELEASED';
        """

        cursor.execute(
            sales_query,
            date_params
        )

        sales_data = cursor.fetchone()

        total_sales = sales_data[0]
        sales_revenue = sales_data[1]
        cost_of_goods_sold = sales_data[2]

        # =================================================
        # EXPENSE SUMMARY
        # =================================================

        expense_query = f"""
            SELECT
                COUNT(*) AS total_expenses,

                COALESCE(
                    SUM(e.amount),
                    0
                ) AS total_expenses_amount

            FROM expenses e

            WHERE
                {expense_date_condition};
        """

        cursor.execute(
            expense_query,
            expense_date_params
        )

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

        sales_employee_query = f"""
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

                AND s.delivery_status = 'RELEASED'

            LEFT JOIN sale_items si
                ON s.id = si.sale_id

            GROUP BY
                emp.id,
                emp.full_name

            ORDER BY
                total_sales_amount DESC;
        """

        cursor.execute(
            sales_employee_query,
            date_params
        )

        employee_rows = cursor.fetchall()

        sales_by_employee = []

        for row in employee_rows:

            sales_by_employee.append({
                "employee_id": row[0],
                "employee_name": row[1],
                "number_of_sales": row[2],
                "total_sales_amount": str(row[3])
            })

        # =================================================
        # EXPENSES BY EMPLOYEE
        # =================================================

        expense_employee_query = f"""
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
        """

        cursor.execute(
            expense_employee_query,
            expense_date_params
        )

        expense_employee_rows = cursor.fetchall()

        expenses_by_employee = []

        for row in expense_employee_rows:

            expenses_by_employee.append({
                "employee_id": row[0],
                "employee_name": row[1],
                "number_of_expenses": row[2],
                "total_expense_amount": str(row[3])
            })

        # =================================================
        # RESPONSE
        # =================================================

        return jsonify({

            "period": response_period,

            "selected_date":
                selected_date.isoformat()
                if selected_date
                else None,

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

    if not admin_required():
        return "Admin access required.", 403

    return render_template("reports.html")
