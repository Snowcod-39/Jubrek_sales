
from datetime import date, timedelta

from flask import Blueprint, jsonify, request, session

from db import get_db_connection


dashboard_routes = Blueprint("dashboard_routes", __name__)

BUSINESS_TIMEZONE = "Africa/Nairobi"


def admin_required():
    return (
        "user_id" in session
        and session.get("role") == "ADMIN"
    )


@dashboard_routes.route(
    "/api/admin/dashboard/data",
    methods=["GET"]
)
def admin_dashboard_data():

    if not admin_required():
        return jsonify({
            "error": "Admin access required."
        }), 403

    period = request.args.get("period", "today").lower()

    if period not in ["today", "week", "month", "year", "custom"]:
        return jsonify({
            "error": "Invalid dashboard period."
        }), 400

    today = date.today()

    if period == "custom":
        try:
            start_date = date.fromisoformat(
                request.args.get("from", "")
            )
            end_date = date.fromisoformat(
                request.args.get("to", "")
            )
        except (ValueError, TypeError):
            return jsonify({
                "error": "Provide valid from and to dates."
            }), 400

        if start_date > end_date:
            return jsonify({
                "error": "The start date cannot be after the end date."
            }), 400

        if (end_date - start_date).days > 365:
            return jsonify({
                "error": "Custom date range cannot exceed 366 days."
            }), 400

    elif period == "today":
        start_date = today
        end_date = today

    elif period == "week":
        start_date = today - timedelta(days=today.weekday())
        end_date = today

    elif period == "month":
        start_date = today.replace(day=1)
        end_date = today

    else:  # year
        start_date = today.replace(month=1, day=1)
        end_date = today

    connection = None

    try:
        connection = get_db_connection()

        with connection.cursor() as cursor:

            # =============================================
            # CURRENT INVENTORY SUMMARY
            # Independent of graph date selection
            # =============================================

            cursor.execute("""
                SELECT
                    COUNT(*) FILTER (
                        WHERE status = 'ACTIVE'
                    ),

                    COALESCE(
                        SUM(quantity) FILTER (
                            WHERE status = 'ACTIVE'
                        ),
                        0
                    ),

                    COUNT(*) FILTER (
                        WHERE status = 'ACTIVE'
                          AND quantity <= minimum_stock
                    )

                FROM products;
            """)

            inventory = cursor.fetchone()

            active_products = inventory[0] or 0
            total_stock = inventory[1] or 0
            low_stock_variants = inventory[2] or 0

            # =============================================
            # SALES TODAY
            # Released sales only
            # =============================================

            cursor.execute("""
                SELECT
                    COALESCE(SUM(si.subtotal), 0)

                FROM sales s

                JOIN sale_items si
                    ON si.sale_id = s.id

                WHERE s.delivery_status = 'RELEASED'

                  AND (
                      s.sale_date AT TIME ZONE %s
                  )::date = (
                      CURRENT_TIMESTAMP AT TIME ZONE %s
                  )::date;
            """, (
                BUSINESS_TIMEZONE,
                BUSINESS_TIMEZONE
            ))

            sales_today = cursor.fetchone()[0] or 0

            # =============================================
            # DAILY PROFIT AFTER EXPENSES
            # =============================================

            if period == "year":

                cursor.execute("""
                    WITH selected_dates AS (
                        SELECT generate_series(
                            DATE_TRUNC('month', %s::date),
                            DATE_TRUNC('month', %s::date),
                            INTERVAL '1 month'
                        )::date AS report_date
                    ),

                    monthly_sales AS (
                        SELECT
                            sales_data.report_date,
                            COALESCE(SUM(sales_data.revenue), 0) AS revenue,
                            COALESCE(SUM(sales_data.product_cost), 0) AS product_cost

                        FROM (
                            SELECT
                                DATE_TRUNC(
                                    'month',
                                    s.sale_date AT TIME ZONE %s
                                )::date AS report_date,

                                si.subtotal AS revenue,
                                si.quantity * si.buying_price AS product_cost

                            FROM sales s

                            JOIN sale_items si
                                ON si.sale_id = s.id

                            WHERE s.delivery_status = 'RELEASED'
                              AND (s.sale_date AT TIME ZONE %s)::date
                                  BETWEEN %s AND %s

                        ) AS sales_data

                        GROUP BY sales_data.report_date
                    ),

                    monthly_expenses AS (
                        SELECT
                            DATE_TRUNC('month', expense_date)::date AS report_date,
                            COALESCE(SUM(amount), 0) AS expenses

                        FROM expenses

                        WHERE expense_date BETWEEN %s AND %s

                        GROUP BY DATE_TRUNC('month', expense_date)::date
                    )

                    SELECT
                        d.report_date,
                        COALESCE(s.revenue, 0),
                        COALESCE(s.product_cost, 0),
                        COALESCE(e.expenses, 0),

                        COALESCE(s.revenue, 0)
                        - COALESCE(s.product_cost, 0)
                        - COALESCE(e.expenses, 0) AS net_profit

                    FROM selected_dates d

                    LEFT JOIN monthly_sales s
                        ON s.report_date = d.report_date

                    LEFT JOIN monthly_expenses e
                        ON e.report_date = d.report_date

                    ORDER BY d.report_date ASC;

                """, (
                    start_date,
                    end_date,
                    BUSINESS_TIMEZONE,
                    BUSINESS_TIMEZONE,
                    start_date,
                    end_date,
                    start_date,
                    end_date
                ))

            else:
                
                cursor.execute("""
                WITH selected_dates AS (
                    SELECT generate_series(
                        %s::date,
                        %s::date,
                        INTERVAL '1 day'
                    )::date AS report_date
                ),

                
daily_sales AS (
    SELECT
        sale_data.report_date,

        COALESCE(SUM(sale_data.revenue), 0)
            AS revenue,

        COALESCE(SUM(sale_data.product_cost), 0)
            AS product_cost

    FROM (
        SELECT
            (s.sale_date AT TIME ZONE %s)::date
                AS report_date,

            si.subtotal AS revenue,

            si.quantity * si.buying_price
                AS product_cost

        FROM sales s

        JOIN sale_items si
            ON si.sale_id = s.id

        WHERE s.delivery_status = 'RELEASED'

          AND (
              s.sale_date AT TIME ZONE %s
          )::date BETWEEN %s AND %s

    ) AS sale_data

    GROUP BY sale_data.report_date
),


                daily_expenses AS (
                    SELECT
                        expense_date AS report_date,
                        COALESCE(SUM(amount), 0) AS expenses

                    FROM expenses

                    WHERE expense_date BETWEEN %s AND %s

                    GROUP BY expense_date
                )

                SELECT
                    d.report_date,

                    COALESCE(s.revenue, 0),

                    COALESCE(s.product_cost, 0),

                    COALESCE(e.expenses, 0),

                    COALESCE(s.revenue, 0)
                    - COALESCE(s.product_cost, 0)
                    - COALESCE(e.expenses, 0)
                    AS net_profit

                FROM selected_dates d

                LEFT JOIN daily_sales s
                    ON s.report_date = d.report_date

                LEFT JOIN daily_expenses e
                    ON e.report_date = d.report_date

                ORDER BY d.report_date ASC;
            """, (
                start_date,
                end_date,
                BUSINESS_TIMEZONE,
                BUSINESS_TIMEZONE,
                start_date,
                end_date,                
                start_date,
                end_date
            ))

            profit_rows = cursor.fetchall()

            profit_data = []

            for row in profit_rows:
                profit_data.append({
                    "date": row[0].isoformat(),
                    "revenue": str(row[1]),
                    "product_cost": str(row[2]),
                    "expenses": str(row[3]),
                    "net_profit": str(row[4])
                })

            # =============================================
            # TOP FIVE BEST-SELLING PRODUCTS
            # Same date range as profit graph
            # =============================================

            cursor.execute("""
                SELECT
                    p.id,
                    p.product_name,
                    COALESCE(SUM(si.quantity), 0)
                        AS quantity_sold

                FROM sales s

                JOIN sale_items si
                    ON si.sale_id = s.id

                JOIN products p
                    ON p.id = si.product_id

                WHERE s.delivery_status = 'RELEASED'

                  AND (
                      s.sale_date AT TIME ZONE %s
                  )::date BETWEEN %s AND %s

                GROUP BY
                    p.id,
                    p.product_name

                ORDER BY
                    quantity_sold DESC,
                    p.product_name ASC

                LIMIT 5;
            """, (
                BUSINESS_TIMEZONE,
                start_date,
                end_date
            ))

            best_sellers = []

            for row in cursor.fetchall():
                best_sellers.append({
                    "product_id": row[0],
                    "product_name": row[1],
                    "quantity_sold": row[2]
                })

        return jsonify({
            "summary": {
                "active_products": active_products,
                "total_stock": total_stock,
                "sales_today": str(sales_today),
                "low_stock_variants": low_stock_variants
            },
            "period": period,
            "from": start_date.isoformat(),
            "to": end_date.isoformat(),
            "profit": profit_data,
            "best_sellers": best_sellers
        })

    except Exception as e:
        print(
            "ADMIN DASHBOARD DATA ERROR:",
            type(e).__name__,
            str(e)
        )

        return jsonify({
            "error": "Could not load dashboard data."
        }), 500

    finally:
        if connection:
            connection.close()
