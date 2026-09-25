from flask import Blueprint, request, jsonify, session, render_template
from decimal import Decimal, InvalidOperation
from db import get_db_connection


sales_routes = Blueprint("sales_routes", __name__)


# =========================================================
# AUTHORIZATION
# =========================================================

def employee_required():
    return (
        "user_id" in session
        and session.get("role") == "EMPLOYEE"
    )


def admin_required():
    return (
        "user_id" in session
        and session.get("role") == "ADMIN"
    )


def admin_or_employee_required():
    return (
        "user_id" in session
        and session.get("role") in ["ADMIN", "EMPLOYEE"]
    )


# =========================================================
# EMPLOYEE SALES PAGE
# =========================================================

@sales_routes.route("/employee/sales")
def employee_sales_page():

    if "user_id" not in session:
        return "Login required.", 401

    if session.get("role") != "EMPLOYEE":
        return "Employee access required.", 403

    return render_template("employee_sales.html")


# =========================================================
# GET NEXT SYSTEM RECEIPT NUMBER
# =========================================================

@sales_routes.route(
    "/api/sales/next-receipt",
    methods=["GET"]
)
def get_next_receipt():

    if not employee_required():
        return jsonify({
            "error": "Employee access required."
        }), 403

    connection = get_db_connection()

    try:

        with connection.cursor() as cursor:

            cursor.execute("""
                SELECT pg_advisory_xact_lock(700001);
            """)

            cursor.execute("""
                SELECT COALESCE(
                    MAX(receipt_number),
                    0
                ) + 1
                FROM sales
                WHERE receipt_type = 'SYSTEM'
                  AND receipt_book_id IS NULL;
            """)

            next_receipt = cursor.fetchone()[0]

        return jsonify({
            "receipt_number": next_receipt,
            "formatted_receipt_number": str(next_receipt)
        }), 200

    except Exception as e:

        print(
            "NEXT SYSTEM RECEIPT ERROR:",
            type(e).__name__,
            str(e)
        )

        return jsonify({
            "error":
                "Could not determine the next system receipt number."
        }), 500

    finally:
        connection.close()


# =========================================================
# RECORD SALE
# =========================================================

@sales_routes.route(
    "/api/sales",
    methods=["POST"]
)
def record_sale():

    if not employee_required():
        return jsonify({
            "error": "Employee access required."
        }), 403

    data = request.get_json(silent=True)

    if not data:
        return jsonify({
            "error": "Request data is required."
        }), 400

    items = data.get("items")

    payment_method = str(
        data.get(
            "payment_method",
            "CASH"
        )
    ).upper().strip()

    receipt_type = str(
        data.get(
            "receipt_type",
            "SYSTEM"
        )
    ).upper().strip()

    receipt_number = data.get("receipt_number")


    # =========================================================
    # CUSTOMER NAME
    # =========================================================

    customer_name = data.get("customer_name")

    if customer_name is not None:

        customer_name = str(
            customer_name
        ).strip()

        if customer_name == "":
            customer_name = None


    # =========================================================
    # NOTES
    # =========================================================

    notes = data.get("notes")

    if notes is not None:

        notes = str(
            notes
        ).strip()

        if notes == "":
            notes = None


    # =========================================================
    # PAYMENT METHOD
    # =========================================================

    if payment_method not in (
        "CASH",
        "MPESA"
    ):

        return jsonify({
            "error":
                "Invalid payment method. Use CASH or MPESA."
        }), 400


    # =========================================================
    # AMOUNT RECEIVED
    # =========================================================

    amount_received = None

    if payment_method == "CASH":

        raw_amount_received = data.get(
            "amount_received"
        )

        if (
            raw_amount_received is None
            or
            str(raw_amount_received).strip() == ""
        ):

            return jsonify({
                "error":
                    "Amount received is required for cash payments."
            }), 400

        try:

            amount_received = Decimal(
                str(raw_amount_received)
            )

        except (
            ValueError,
            TypeError,
            InvalidOperation
        ):

            return jsonify({
                "error":
                    "Invalid amount received."
            }), 400

        if amount_received < 0:

            return jsonify({
                "error":
                    "Amount received cannot be negative."
            }), 400


    # =========================================================
    # RECEIPT TYPE
    # =========================================================

    if receipt_type not in (
        "SYSTEM",
        "MANUAL"
    ):

        return jsonify({
            "error":
                "Invalid receipt type. Use SYSTEM or MANUAL."
        }), 400


    # =========================================================
    # PRODUCTS
    # =========================================================

    if (
        not items
        or
        not isinstance(items, list)
    ):

        return jsonify({
            "error":
                "At least one product is required."
        }), 400


    # =========================================================
    # MANUAL RECEIPT NUMBER
    # =========================================================

    if receipt_type == "MANUAL":

        if receipt_number is None:

            return jsonify({
                "error":
                    "Manual receipt number is required."
            }), 400

        try:

            receipt_number = int(
                receipt_number
            )

        except (
            ValueError,
            TypeError
        ):

            return jsonify({
                "error":
                    "Invalid manual receipt number."
            }), 400

    else:

        receipt_number = None


    connection = get_db_connection()

    try:

        with connection.cursor() as cursor:

            receipt_book_id = None
            receipt_alert = None
            expected_receipt = None


            # =================================================
            # SYSTEM RECEIPT
            # =================================================

            if receipt_type == "SYSTEM":

                cursor.execute("""
                    SELECT pg_advisory_xact_lock(700001);
                """)

                cursor.execute("""
                    SELECT COALESCE(
                        MAX(receipt_number),
                        0
                    ) + 1
                    FROM sales
                    WHERE receipt_type = 'SYSTEM'
                      AND receipt_book_id IS NULL;
                """)

                receipt_number = cursor.fetchone()[0]


            # =================================================
            # MANUAL RECEIPT
            # =================================================

            else:

                cursor.execute("""
                    SELECT
                        id,
                        start_number,
                        end_number,
                        number_width,
                        status
                    FROM receipt_books
                    WHERE status = 'ACTIVE'
                    ORDER BY
                        book_year DESC,
                        book_number DESC
                    LIMIT 1
                    FOR UPDATE;
                """)

                receipt_book = cursor.fetchone()

                if receipt_book is None:

                    connection.rollback()

                    return jsonify({
                        "error":
                            "There is no active manual receipt book."
                    }), 400


                (
                    receipt_book_id,
                    start_number,
                    end_number,
                    number_width,
                    book_status
                ) = receipt_book


                if book_status != "ACTIVE":

                    connection.rollback()

                    return jsonify({
                        "error":
                            "The current manual receipt book is not active."
                    }), 400


                if (
                    receipt_number < start_number
                    or
                    receipt_number > end_number
                ):

                    connection.rollback()

                    return jsonify({
                        "error":
                            f"Manual receipt number must be "
                            f"between {start_number} "
                            f"and {end_number}."
                    }), 400


                # =================================================
                # DUPLICATE MANUAL RECEIPT
                # =================================================

                cursor.execute("""
                    SELECT id
                    FROM sales
                    WHERE receipt_book_id = %s
                      AND receipt_number = %s
                    LIMIT 1;
                """, (
                    receipt_book_id,
                    receipt_number
                ))

                existing_sale = cursor.fetchone()

                if existing_sale:

                    connection.rollback()

                    return jsonify({
                        "error":
                            "This manual receipt number "
                            "has already been used."
                    }), 400


                # =================================================
                # PREVIOUS RECEIPT
                # =================================================

                cursor.execute("""
                    SELECT receipt_number
                    FROM sales
                    WHERE receipt_book_id = %s
                    ORDER BY receipt_number DESC
                    LIMIT 1;
                """, (
                    receipt_book_id,
                ))

                previous_receipt = cursor.fetchone()

                expected_receipt = start_number

                if previous_receipt:

                    expected_receipt = (
                        previous_receipt[0] + 1
                    )


                # =================================================
                # MISSING RECEIPT ALERT
                # =================================================

                if receipt_number > expected_receipt:

                    missing_from = expected_receipt
                    missing_to = receipt_number - 1

                    if missing_from == missing_to:

                        receipt_alert = (
                            f"Receipt number "
                            f"{missing_from} appears "
                            f"to be missing before "
                            f"receipt {receipt_number}."
                        )

                    else:

                        receipt_alert = (
                            f"Receipts "
                            f"{missing_from} to "
                            f"{missing_to} appear "
                            f"to be missing before "
                            f"receipt {receipt_number}."
                        )


            # =================================================
            # CREATE SALE
            # =================================================

            cursor.execute("""
                INSERT INTO sales
                (
                    employee_id,
                    receipt_book_id,
                    receipt_number,
                    total_amount,
                    payment_method,
                    payment_status,
                    receipt_type,
                    delivery_status,
                    customer_name,
                    notes,
                    amount_received,
                    change_amount
                )
                VALUES
                (
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    'PAID',
                    %s,
                    'NOT RELEASED',
                    %s,
                    %s,
                    %s,
                    %s
                )
                RETURNING id;
            """, (
                session["user_id"],
                receipt_book_id,
                receipt_number,
                Decimal("0.00"),
                payment_method,
                receipt_type,
                customer_name,
                notes,
                amount_received,
                None
            ))

            sale_id = cursor.fetchone()[0]


            # =================================================
            # SAVE RECEIPT ALERT
            # =================================================

            if receipt_alert:

                cursor.execute("""
                    INSERT INTO receipt_alerts
                    (
                        receipt_book_id,
                        sale_id,
                        expected_receipt_number,
                        entered_receipt_number,
                        message
                    )
                    VALUES
                    (
                        %s,
                        %s,
                        %s,
                        %s,
                        %s
                    );
                """, (
                    receipt_book_id,
                    sale_id,
                    expected_receipt,
                    receipt_number,
                    receipt_alert
                ))


            # =================================================
            # PROCESS PRODUCTS
            # =================================================

            total_amount = Decimal("0.00")


            for item in items:

                if not isinstance(item, dict):

                    connection.rollback()

                    return jsonify({
                        "error":
                            "Invalid sale item."
                    }), 400


                product_id = item.get(
                    "product_id"
                )

                quantity = item.get(
                    "quantity"
                )


                if (
                    product_id is None
                    or
                    quantity is None
                ):

                    connection.rollback()

                    return jsonify({
                        "error":
                            "Each sale item needs "
                            "a product and quantity."
                    }), 400


                try:

                    product_id = int(
                        product_id
                    )

                    quantity = Decimal(
                        str(quantity)
                    )

                except (
                    ValueError,
                    TypeError,
                    InvalidOperation
                ):

                    connection.rollback()

                    return jsonify({
                        "error":
                            "Invalid product ID or quantity."
                    }), 400


                # =================================================
                # WHOLE NUMBER QUANTITY
                # =================================================

                if (
                    quantity <= 0
                    or
                    quantity !=
                    quantity.to_integral_value()
                ):

                    connection.rollback()

                    return jsonify({
                        "error":
                            "Sale quantity must be "
                            "a whole number greater "
                            "than zero."
                    }), 400


                # =================================================
                # GET PRODUCT
                # =================================================

                cursor.execute("""
                    SELECT
                        id,
                        product_name,
                        buying_price,
                        selling_price,
                        quantity
                    FROM products
                    WHERE id = %s
                      AND status = 'ACTIVE'
                    FOR UPDATE;
                """, (
                    product_id,
                ))

                product = cursor.fetchone()


                if product is None:

                    connection.rollback()

                    return jsonify({
                        "error":
                            f"Product {product_id} "
                            f"not found or inactive."
                    }), 404


                (
                    product_id_db,
                    product_name,
                    buying_price,
                    selling_price,
                    available_quantity
                ) = product


                # =================================================
                # STOCK CHECK
                # =================================================

                if quantity > available_quantity:

                    connection.rollback()

                    return jsonify({
                        "error":
                            f"Not enough stock for "
                            f"{product_name}. "
                            f"Available: "
                            f"{available_quantity}"
                    }), 400


                # =================================================
                # SUBTOTAL
                # =================================================

                subtotal = (
                    selling_price *
                    quantity
                )

                total_amount += subtotal


                # =================================================
                # STOCK IS NOT DEDUCTED HERE
                # =================================================

                cursor.execute("""
                    INSERT INTO sale_items
                    (
                        sale_id,
                        product_id,
                        quantity,
                        selling_price,
                        buying_price,
                        subtotal
                    )
                    VALUES
                    (
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s
                    );
                """, (
                    sale_id,
                    product_id_db,
                    quantity,
                    selling_price,
                    buying_price,
                    subtotal
                ))


            # =================================================
            # CASH CHANGE
            # =================================================

            change_amount = None


            if payment_method == "CASH":

                if amount_received < total_amount:

                    connection.rollback()

                    return jsonify({
                        "error":
                            f"Amount received "
                            f"({amount_received}) "
                            f"is less than the sale total "
                            f"({total_amount})."
                    }), 400


                change_amount = (
                    amount_received -
                    total_amount
                )


            # =================================================
            # UPDATE SALE
            # =================================================

            cursor.execute("""
                UPDATE sales
                SET
                    total_amount = %s,
                    amount_received = %s,
                    change_amount = %s
                WHERE id = %s;
            """, (
                total_amount,
                amount_received,
                change_amount,
                sale_id
            ))


        connection.commit()


        response = {

            "message":
                "Sale recorded successfully.",

            "sale_id":
                sale_id,

            "receipt_book_id":
                receipt_book_id,

            "receipt_number":
                receipt_number,

            "receipt_type":
                receipt_type,

            "total_amount":
                str(total_amount),

            "payment_method":
                payment_method,

            "customer_name":
                customer_name,

            "notes":
                notes,

            "amount_received":
                (
                    str(amount_received)
                    if amount_received is not None
                    else None
                ),

            "change_amount":
                (
                    str(change_amount)
                    if change_amount is not None
                    else None
                ),

            "delivery_status":
                "NOT RELEASED"
        }


        if receipt_alert:
            response["receipt_alert"] = receipt_alert


        return jsonify(response), 201


    except Exception as e:

        connection.rollback()

        print(
            "SALE ERROR:",
            type(e).__name__,
            str(e)
        )

        return jsonify({
            "error":
                "Could not record sale."
        }), 500


    finally:

        connection.close()


# =========================================================
# RELEASE SALE
# =========================================================

@sales_routes.route(
    "/api/sales/<int:sale_id>/release",
    methods=["POST"]
)
def release_sale(sale_id):

    if not admin_or_employee_required():

        return jsonify({
            "error":
                "Admin or employee access required."
        }), 403

    connection = get_db_connection()

    try:

        with connection.cursor() as cursor:

            cursor.execute("""
                SELECT
                    id,
                    employee_id,
                    payment_status,
                    delivery_status,
                    receipt_number,
                    receipt_book_id
                FROM sales
                WHERE id = %s
                FOR UPDATE;
            """, (
                sale_id,
            ))

            sale = cursor.fetchone()


            if sale is None:

                connection.rollback()

                return jsonify({
                    "error":
                        "Sale not found."
                }), 404


            (
                sale_id_db,
                employee_id,
                payment_status,
                delivery_status,
                receipt_number,
                receipt_book_id
            ) = sale


            if payment_status != "PAID":

                connection.rollback()

                return jsonify({
                    "error":
                        "Only paid sales can be released."
                }), 400


            if delivery_status == "RELEASED":

                connection.rollback()

                return jsonify({
                    "error":
                        "This sale has already been released."
                }), 400


            cursor.execute("""
                SELECT
                    si.product_id,
                    si.quantity,
                    p.product_name,
                    p.quantity
                FROM sale_items si
                JOIN products p
                    ON si.product_id = p.id
                WHERE si.sale_id = %s
                FOR UPDATE;
            """, (
                sale_id,
            ))

            items = cursor.fetchall()


            if not items:

                connection.rollback()

                return jsonify({
                    "error":
                        "This sale has no products."
                }), 400


            # =================================================
            # CHECK STOCK FIRST
            # =================================================

            for item in items:

                (
                    product_id,
                    quantity,
                    product_name,
                    current_quantity
                ) = item


                if quantity > current_quantity:

                    connection.rollback()

                    return jsonify({
                        "error":
                            f"Not enough stock to release "
                            f"{product_name}. "
                            f"Available: "
                            f"{current_quantity}, "
                            f"Required: "
                            f"{quantity}."
                    }), 400


            # =================================================
            # DEDUCT STOCK
            # =================================================

            for item in items:

                (
                    product_id,
                    quantity,
                    product_name,
                    current_quantity
                ) = item


                new_quantity = (
                    current_quantity -
                    quantity
                )


                cursor.execute("""
                    UPDATE products
                    SET
                        quantity = %s,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s;
                """, (
                    new_quantity,
                    product_id
                ))


                release_reason = (
                    f"Released Sale - "
                    f"Receipt {receipt_number}"
                )


                if session.get("role") == "EMPLOYEE":

                    cursor.execute("""
                        INSERT INTO stock_transactions
                        (
                            product_id,
                            employee_id,
                            admin_id,
                            transaction_type,
                            quantity,
                            previous_quantity,
                            new_quantity,
                            reason,
                            transaction_date,
                            created_at
                        )
                        VALUES
                        (
                            %s,
                            %s,
                            NULL,
                            'SALE_OUT',
                            %s,
                            %s,
                            %s,
                            %s,
                            CURRENT_TIMESTAMP,
                            CURRENT_TIMESTAMP
                        );
                    """, (
                        product_id,
                        session["user_id"],
                        quantity,
                        current_quantity,
                        new_quantity,
                        release_reason
                    ))

                else:

                    cursor.execute("""
                        INSERT INTO stock_transactions
                        (
                            product_id,
                            employee_id,
                            admin_id,
                            transaction_type,
                            quantity,
                            previous_quantity,
                            new_quantity,
                            reason,
                            transaction_date,
                            created_at
                        )
                        VALUES
                        (
                            %s,
                            NULL,
                            %s,
                            'SALE_OUT',
                            %s,
                            %s,
                            %s,
                            %s,
                            CURRENT_TIMESTAMP,
                            CURRENT_TIMESTAMP
                        );
                    """, (
                        product_id,
                        session["user_id"],
                        quantity,
                        current_quantity,
                        new_quantity,
                        release_reason
                    ))


            # =================================================
            # MARK RELEASED
            # =================================================

            cursor.execute("""
                UPDATE sales
                SET
                    delivery_status = 'RELEASED',
                    released_by = %s,
                    released_at = CURRENT_TIMESTAMP
                WHERE id = %s;
            """, (
                session["user_id"],
                sale_id
            ))


        connection.commit()


        return jsonify({

            "message":
                "Sale released successfully.",

            "sale_id":
                sale_id_db,

            "receipt_book_id":
                receipt_book_id,

            "receipt_number":
                receipt_number,

            "delivery_status":
                "RELEASED"

        }), 200


    except Exception as e:

        connection.rollback()

        print(
            "RELEASE SALE ERROR:",
            type(e).__name__,
            str(e)
        )

        return jsonify({
            "error":
                "Could not release sale."
        }), 500


    finally:

        connection.close()


# =========================================================
# GET SALES
# =========================================================

@sales_routes.route(
    "/api/sales",
    methods=["GET"]
)
def get_sales():

    if "user_id" not in session:

        return jsonify({
            "error":
                "Login required."
        }), 401


    role = session.get("role")


    if role not in [
        "EMPLOYEE",
        "ADMIN"
    ]:

        return jsonify({
            "error":
                "Unauthorized access."
        }), 403


    connection = get_db_connection()


    try:

        with connection.cursor() as cursor:

            if role == "EMPLOYEE":

                cursor.execute("""
                    SELECT
                        s.id,
                        s.receipt_book_id,
                        s.receipt_number,
                        s.total_amount,
                        s.payment_method,
                        s.payment_status,
                        s.sale_date,
                        s.delivery_status,
                        s.receipt_type,
                        s.customer_name,
                        s.notes,
                        s.amount_received,
                        s.change_amount,
                        e.full_name AS employee_name
                    FROM sales s
                    JOIN employees e
                        ON s.employee_id = e.id
                    WHERE s.employee_id = %s
                    ORDER BY
                        s.sale_date DESC,
                        s.id DESC;
                """, (
                    session["user_id"],
                ))

            else:

                cursor.execute("""
                    SELECT
                        s.id,
                        s.receipt_book_id,
                        s.receipt_number,
                        s.total_amount,
                        s.payment_method,
                        s.payment_status,
                        s.sale_date,
                        s.delivery_status,
                        s.receipt_type,
                        s.customer_name,
                        s.notes,
                        s.amount_received,
                        s.change_amount,
                        e.full_name AS employee_name
                    FROM sales s
                    JOIN employees e
                        ON s.employee_id = e.id
                    ORDER BY
                        s.sale_date DESC,
                        s.id DESC;
                """)


            rows = cursor.fetchall()


            sales = []


            for row in rows:

                sales.append({

                    "id":
                        row[0],

                    "receipt_book_id":
                        row[1],

                    "receipt_number":
                        row[2],

                    "total_amount":
                        str(row[3]),

                    "payment_method":
                        row[4],

                    "payment_status":
                        row[5],

                    "sale_date":
                        row[6].isoformat(),

                    "delivery_status":
                        row[7],

                    "receipt_type":
                        row[8],

                    "customer_name":
                        row[9],

                    "notes":
                        row[10],

                    "amount_received":
                        (
                            str(row[11])
                            if row[11] is not None
                            else None
                        ),

                    "change_amount":
                        (
                            str(row[12])
                            if row[12] is not None
                            else None
                        ),

                    "employee_name":
                        row[13]

                })


            # =================================================
            # TODAY'S TOTAL FOR EMPLOYEE
            # =================================================

            today_total = None


            if role == "EMPLOYEE":

                cursor.execute("""
                    SELECT
                        COALESCE(
                            SUM(total_amount),
                            0
                        )
                    FROM sales
                    WHERE employee_id = %s
                      AND sale_date::date = CURRENT_DATE;
                """, (
                    session["user_id"],
                ))

                today_total =cursor.fetchone()[0]


        response = {
            "sales": sales
        }


        if role == "EMPLOYEE":

            response["today_total"] = str(
                today_total
            )


        return jsonify(response), 200


    except Exception as e:

        print(
            "GET SALES ERROR:",
            type(e).__name__,
            str(e)
        )

        return jsonify({
            "error":
                "Could not retrieve sales."
        }), 500


    finally:

        connection.close()


# =========================================================
# GET TODAY'S TOTAL SALES
# =========================================================

@sales_routes.route(
    "/api/sales/today-total",
    methods=["GET"]
)
def get_today_total_sales():

    if "user_id" not in session:

        return jsonify({
            "error":
                "Login required."
        }), 401


    role = session.get("role")


    if role not in [
        "EMPLOYEE",
        "ADMIN"
    ]:

        return jsonify({
            "error":
                "Unauthorized access."
        }), 403


    connection = get_db_connection()


    try:

        with connection.cursor() as cursor:

            if role == "EMPLOYEE":

                cursor.execute("""
                    SELECT
                        COALESCE(
                            SUM(total_amount),
                            0
                        )
                    FROM sales
                    WHERE employee_id = %s
                      AND sale_date::date =
                          CURRENT_DATE;
                """, (
                    session["user_id"],
                ))

            else:

                cursor.execute("""
                    SELECT
                        COALESCE(
                            SUM(total_amount),
                            0
                        )
                    FROM sales
                    WHERE sale_date::date =
                          CURRENT_DATE;
                """)


            total = cursor.fetchone()[0]


        return jsonify({
            "total_sales":
                str(total)
        }), 200


    except Exception as e:

        print(
            "TODAY TOTAL SALES ERROR:",
            type(e).__name__,
            str(e)
        )

        return jsonify({
            "error":
                "Could not retrieve today's sales total."
        }), 500


    finally:

        connection.close()


# =========================================================
# GET RECEIPT
# =========================================================

@sales_routes.route(
    "/api/sales/<int:sale_id>/receipt",
    methods=["GET"]
)
def get_receipt(sale_id):

    if "user_id" not in session:

        return jsonify({
            "error":
                "Login required."
        }), 401


    role = session.get("role")


    if role not in [
        "EMPLOYEE",
        "ADMIN"
    ]:

        return jsonify({
            "error":
                "Unauthorized access."
        }), 403


    connection = get_db_connection()


    try:

        with connection.cursor() as cursor:

            cursor.execute("""
                SELECT
                    s.id,
                    s.employee_id,
                    s.receipt_book_id,
                    s.receipt_number,
                    s.total_amount,
                    s.payment_method,
                    s.payment_status,
                    s.sale_date,
                    s.delivery_status,
                    s.receipt_type,
                    s.customer_name,
                    s.notes,
                    s.amount_received,
                    s.change_amount,
                    e.full_name AS employee_name
                FROM sales s
                JOIN employees e
                    ON s.employee_id = e.id
                WHERE s.id = %s;
            """, (
                sale_id,
            ))


            sale = cursor.fetchone()


            if sale is None:

                return jsonify({
                    "error":
                        "Sale not found."
                }), 404


            (
                sale_id_db,
                sale_employee_id,
                receipt_book_id,
                receipt_number,
                total_amount,
                payment_method,
                payment_status,
                sale_date,
                delivery_status,
                receipt_type,
                customer_name,
                notes,
                amount_received,
                change_amount,
                employee_name
            ) = sale


            if (
                role == "EMPLOYEE"
                and
                sale_employee_id !=
                session["user_id"]
            ):

                return jsonify({
                    "error":
                        "Access denied."
                }), 403


            cursor.execute("""
                SELECT
                    p.product_name,
                    si.quantity,
                    si.selling_price,
                    si.subtotal
                FROM sale_items si
                JOIN products p
                    ON si.product_id = p.id
                WHERE si.sale_id = %s
                ORDER BY
                    si.id;
            """, (
                sale_id,
            ))


            item_rows = cursor.fetchall()


            items = []


            for row in item_rows:

                items.append({

                    "product_name":
                        row[0],

                    "quantity":
                        str(row[1]),

                    "selling_price":
                        str(row[2]),

                    "subtotal":
                        str(row[3])

                })


        receipt = {

            "sale_id":
                sale_id_db,

            "receipt_book_id":
                receipt_book_id,

            "receipt_number":
                receipt_number,

            "total_amount":
                str(total_amount),

            "payment_method":
                payment_method,

            "payment_status":
                payment_status,

            "sale_date":
                sale_date.isoformat(),

            "delivery_status":
                delivery_status,

            "receipt_type":
                receipt_type,

            "customer_name":
                customer_name,

            "notes":
                notes,

            "amount_received":
                (
                    str(amount_received)
                    if amount_received is not None
                    else None
                ),

            "change_amount":
                (
                    str(change_amount)
                    if change_amount is not None
                    else None
                ),

            "employee_name":
                employee_name,

            "items":
                items

        }


        return jsonify(receipt), 200


    except Exception as e:

        print(
            "RECEIPT ERROR:",
            type(e).__name__,
            str(e)
        )

        return jsonify({
            "error":
                "Could not generate receipt."
        }), 500


    finally:

        connection.close()


# =========================================================
# GET RECEIPT ALERTS
# =========================================================

@sales_routes.route(
    "/api/receipt-alerts",
    methods=["GET"]
)
def get_receipt_alerts():

    if "user_id" not in session:

        return jsonify({
            "error":
                "Login required."
        }), 401


    if session.get("role") != "ADMIN":

        return jsonify({
            "error":
                "Admin access required."
        }), 403


    connection = get_db_connection()


    try:

        with connection.cursor() as cursor:

            cursor.execute("""
                SELECT
                    ra.id,
                    ra.receipt_book_id,
                    rb.book_number,
                    rb.book_year,
                    ra.sale_id,
                    ra.expected_receipt_number,
                    ra.entered_receipt_number,
                    ra.message,
                    ra.status,
                    ra.created_at,
                    ra.resolved_at,
                    e.full_name AS employee_name
                FROM receipt_alerts ra
                JOIN receipt_books rb
                    ON ra.receipt_book_id = rb.id
                JOIN sales s
                    ON ra.sale_id = s.id
                JOIN employees e
                    ON s.employee_id = e.id
                WHERE ra.status = 'UNRESOLVED'
                ORDER BY
                    ra.created_at DESC;
            """)


            rows = cursor.fetchall()


            alerts = []


            for row in rows:

                alerts.append({

                    "id":
                        row[0],

                    "receipt_book_id":
                        row[1],

                    "book_number":
                        row[2],

                    "book_year":
                        row[3],

                    "sale_id":
                        row[4],

                    "expected_receipt_number":
                        row[5],

                    "entered_receipt_number":
                        row[6],

                    "message":
                        row[7],

                    "status":
                        row[8],

                    "created_at":
                        row[9].isoformat(),

                    "resolved_at":
                        (
                            row[10].isoformat()
                            if row[10]
                            else None
                        ),

                    "employee_name":
                        row[11]

                })


        return jsonify({
            "alerts": alerts
        }), 200


    except Exception as e:

        print(
            "GET RECEIPT ALERTS ERROR:",
            type(e).__name__,
            str(e)
        )

        return jsonify({
            "error":
                "Could not retrieve receipt alerts."
        }), 500


    finally:

        connection.close()


# =========================================================
# RESOLVE RECEIPT ALERT
# =========================================================

@sales_routes.route(
    "/api/receipt-alerts/<int:alert_id>/resolve",
    methods=["POST"]
)
def resolve_receipt_alert(alert_id):

    if "user_id" not in session:

        return jsonify({
            "error":
                "Login required."
        }), 401


    if session.get("role") != "ADMIN":

        return jsonify({
            "error":
                "Admin access required."
        }), 403


    connection = get_db_connection()


    try:

        with connection.cursor() as cursor:

            cursor.execute("""
                SELECT
                    id,
                    status
                FROM receipt_alerts
                WHERE id = %s;
            """, (
                alert_id,
            ))


            alert = cursor.fetchone()


            if alert is None:

                return jsonify({
                    "error":
                        "Receipt alert not found."
                }), 404


            if alert[1] == "RESOLVED":

                return jsonify({
                    "message":
                        "Receipt alert is already resolved."
                }), 200


            cursor.execute("""
                UPDATE receipt_alerts
                SET
                    status = 'RESOLVED',
                    resolved_at = CURRENT_TIMESTAMP
                WHERE id = %s;
            """, (
                alert_id,
            ))


        connection.commit()


        return jsonify({
            "message":
                "Receipt alert resolved successfully."
        }), 200


    except Exception as e:

        connection.rollback()

        print(
            "RESOLVE RECEIPT ALERT ERROR:",
            type(e).__name__,
            str(e)
        )

        return jsonify({
            "error":
                "Could not resolve receipt alert."
        }), 500


    finally:

        connection.close()


# =========================================================
# RECEIPT PAGE
# =========================================================

@sales_routes.route(
    "/sales/receipt"
)
def receipt_page():

    if "user_id" not in session:

        return "Login required.", 401

    return render_template(
        "receipt.html"
    )


# =========================================================
# SALES PAGE
# =========================================================

@sales_routes.route(
    "/sales"
)
def sales_page():

    if "user_id" not in session:

        return "Login required.", 401

    return render_template(
        "sales.html"
    )