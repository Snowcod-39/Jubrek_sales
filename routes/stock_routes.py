from flask import Blueprint, request, jsonify, session, render_template
from decimal import Decimal, InvalidOperation
from db import get_db_connection

stock_routes = Blueprint("stock_routes", __name__)


# =========================================================
# ACCESS CHECKS
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


def stock_access_required():
    return (
        "user_id" in session
        and session.get("role") in ["ADMIN", "EMPLOYEE"]
    )


# =========================================================
# EMPLOYEE STOCK PAGE
# =========================================================

@stock_routes.route("/stock")
def stock_page():

    if not employee_required():
        return jsonify({
            "error": "Employee access required."
        }), 403

    return render_template("employee_stock.html")


# =========================================================
# EMPLOYEE LOW STOCK PAGE
# =========================================================

@stock_routes.route("/stock/low-stock")
def low_stock_page():

    if not employee_required():
        return jsonify({
            "error": "Employee access required."
        }), 403

    return render_template("employee_low_stock.html")


# =========================================================
# LOW STOCK ALERTS
# ADMIN + EMPLOYEE
# =========================================================

@stock_routes.route("/api/stock/alerts", methods=["GET"])
def get_stock_alerts():

    if not stock_access_required():
        return jsonify({
            "error": "Login required."
        }), 401

    connection = get_db_connection()

    try:

        with connection.cursor() as cursor:

            cursor.execute("""
                SELECT
                    p.id,
                    p.product_name,
                    p.quantity,
                    p.minimum_stock,
                    c.category_name
                FROM products p

                LEFT JOIN categories c
                    ON p.category_id = c.id

                WHERE p.status = 'ACTIVE'
                AND p.quantity <= p.minimum_stock

                ORDER BY
                    p.quantity ASC,
                    p.product_name ASC;
            """)

            alerts = cursor.fetchall()

        return jsonify({
            "alerts": [
                {
                    "product_id": alert[0],
                    "product_name": alert[1],
                    "quantity": str(alert[2]),
                    "minimum_stock": str(alert[3]),
                    "category_name": alert[4]
                }
                for alert in alerts
            ]
        })

    except Exception as e:

        print(
            "LOW STOCK ALERT ERROR:",
            type(e).__name__,
            str(e)
        )

        return jsonify({
            "error": "Could not load stock alerts."
        }), 500

    finally:
        connection.close()


# =========================================================
# ADD STOCK
#
# ADMIN:
#     admin_id is recorded
#
# EMPLOYEE:
#     employee_id is recorded
#
# BOTH CAN ADD STOCK
# =========================================================

@stock_routes.route("/api/stock/in", methods=["POST"])
def add_stock():

    if not stock_access_required():
        return jsonify({
            "error": "Login required."
        }), 401

    data = request.get_json()

    if not data:
        return jsonify({
            "error": "Request data is required."
        }), 400

    product_id = data.get("product_id")
    quantity = data.get("quantity")
    reason = data.get("reason", "")

    if reason is None:
        reason = ""

    reason = str(reason).strip()

    if product_id is None or quantity is None:
        return jsonify({
            "error": "Product and quantity are required."
        }), 400

    try:

        product_id = int(product_id)
        quantity = Decimal(str(quantity))

    except (
        ValueError,
        TypeError,
        InvalidOperation
    ):

        return jsonify({
            "error": "Invalid product ID or quantity."
        }), 400

    if quantity <= 0:
        return jsonify({
            "error": "Quantity must be greater than zero."
        }), 400

    connection = get_db_connection()

    try:

        with connection.cursor() as cursor:

            # -------------------------------------------------
            # GET PRODUCT
            # -------------------------------------------------

            cursor.execute("""
                SELECT
                    id,
                    product_name,
                    quantity,
                    minimum_stock
                FROM products
                WHERE id = %s
                AND status = 'ACTIVE'
                FOR UPDATE;
            """, (product_id,))

            product = cursor.fetchone()

            if product is None:

                connection.rollback()

                return jsonify({
                    "error": "Product not found or inactive."
                }), 404

            (
                product_id_db,
                product_name,
                previous_quantity,
                minimum_stock
            ) = product

            new_quantity = (
                previous_quantity + quantity
            )

            # -------------------------------------------------
            # UPDATE PRODUCT STOCK
            # -------------------------------------------------

            cursor.execute("""
                UPDATE products
                SET
                    quantity = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s;
            """, (
                new_quantity,
                product_id_db
            ))

            # -------------------------------------------------
            # RECORD ACTOR
            # -------------------------------------------------

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
                        'STOCK_IN',
                        %s,
                        %s,
                        %s,
                        %s,
                        CURRENT_TIMESTAMP,
                        CURRENT_TIMESTAMP
                    );
                """, (
                    product_id_db,
                    session["user_id"],
                    quantity,
                    previous_quantity,
                    new_quantity,
                    reason if reason else None
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
                        'STOCK_IN',
                        %s,
                        %s,
                        %s,
                        %s,
                        CURRENT_TIMESTAMP,
                        CURRENT_TIMESTAMP
                    );
                """, (
                    product_id_db,
                    session["user_id"],
                    quantity,
                    previous_quantity,
                    new_quantity,
                    reason if reason else None
                ))

        connection.commit()

        low_stock = (
            new_quantity <= minimum_stock
        )

        return jsonify({
            "message": "Stock added successfully.",
            "product": product_name,
            "previous_quantity": str(
                previous_quantity
            ),
            "quantity_added": str(
                quantity
            ),
            "new_quantity": str(
                new_quantity
            ),
            "minimum_stock": str(
                minimum_stock
            ),
            "low_stock": low_stock
        }), 201

    except Exception as e:

        connection.rollback()

        print(
            "STOCK IN ERROR:",
            type(e).__name__,
            str(e)
        )

        return jsonify({
            "error": "Could not add stock."
        }), 500

    finally:
        connection.close()


# =========================================================
# REMOVE STOCK
#
# ADMIN ONLY
#
# Employees cannot remove stock.
# =========================================================

@stock_routes.route("/api/stock/removal", methods=["POST"])
def remove_stock():

    if not admin_required():
        return jsonify({
            "error": "Admin access required."
        }), 403

    data = request.get_json()

    if not data:
        return jsonify({
            "error": "Request data is required."
        }), 400

    product_id = data.get("product_id")
    quantity = data.get("quantity")
    reason = data.get("reason", "")

    if reason is None:
        reason = ""

    reason = str(reason).strip()

    if product_id is None or quantity is None:
        return jsonify({
            "error": "Product and quantity are required."
        }), 400

    if not reason:
        return jsonify({
            "error":
                "A reason is required when removing stock."
        }), 400

    try:

        product_id = int(product_id)
        quantity = Decimal(str(quantity))

    except (
        ValueError,
        TypeError,
        InvalidOperation
    ):

        return jsonify({
            "error": "Invalid product ID or quantity."
        }), 400

    if quantity <= 0:
        return jsonify({
            "error": "Quantity must be greater than zero."
        }), 400

    connection = get_db_connection()

    try:

        with connection.cursor() as cursor:

            cursor.execute("""
                SELECT
                    id,
                    product_name,
                    quantity,
                    minimum_stock
                FROM products
                WHERE id = %s
                AND status = 'ACTIVE'
                FOR UPDATE;
            """, (product_id,))

            product = cursor.fetchone()

            if product is None:

                connection.rollback()

                return jsonify({
                    "error":
                        "Product not found or inactive."
                }), 404

            (
                product_id_db,
                product_name,
                previous_quantity,
                minimum_stock
            ) = product

            if quantity > previous_quantity:

                connection.rollback()

                return jsonify({
                    "error":
                        "Cannot remove more stock than "
                        "currently available."
                }), 400

            new_quantity = (
                previous_quantity - quantity
            )

            cursor.execute("""
                UPDATE products
                SET
                    quantity = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s;
            """, (
                new_quantity,
                product_id_db
            ))

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
                    'STOCK_REMOVAL',
                    %s,
                    %s,
                    %s,
                    %s,
                    CURRENT_TIMESTAMP,
                    CURRENT_TIMESTAMP
                );
            """, (
                product_id_db,
                session["user_id"],
                quantity,
                previous_quantity,
                new_quantity,
                reason
            ))

        connection.commit()

        low_stock = (
            new_quantity <= minimum_stock
        )

        return jsonify({
            "message": "Stock removed successfully.",
            "product": product_name,
            "previous_quantity": str(
                previous_quantity
            ),
            "quantity_removed": str(
                quantity
            ),
            "new_quantity": str(
                new_quantity
            ),
            "minimum_stock": str(
                minimum_stock
            ),
            "low_stock": low_stock
        }), 201

    except Exception as e:

        connection.rollback()

        print(
            "STOCK REMOVAL ERROR:",
            type(e).__name__,
            str(e)
        )

        return jsonify({
            "error": "Could not remove stock."
        }), 500

    finally:
        connection.close()


# =========================================================
# STOCK ADJUSTMENT
#
# ADMIN ONLY
#
# Employees cannot adjust stock.
# =========================================================

@stock_routes.route("/api/stock/adjustment", methods=["POST"])
def adjust_stock():

    if not admin_required():
        return jsonify({
            "error": "Admin access required."
        }), 403

    data = request.get_json()

    if not data:
        return jsonify({
            "error": "Request data is required."
        }), 400

    product_id = data.get("product_id")
    new_quantity = data.get("new_quantity")
    reason = data.get("reason", "")

    if reason is None:
        reason = ""

    reason = str(reason).strip()

    if product_id is None or new_quantity is None:
        return jsonify({
            "error":
                "Product and new quantity are required."
        }), 400

    if not reason:
        return jsonify({
            "error":
                "A reason is required for stock adjustment."
        }), 400

    try:

        product_id = int(product_id)
        new_quantity = Decimal(
            str(new_quantity)
        )

    except (
        ValueError,
        TypeError,
        InvalidOperation
    ):

        return jsonify({
            "error": "Invalid product ID or quantity."
        }), 400

    if new_quantity < 0:
        return jsonify({
            "error":
                "Stock quantity cannot be negative."
        }), 400

    connection = get_db_connection()

    try:

        with connection.cursor() as cursor:

            cursor.execute("""
                SELECT
                    id,
                    product_name,
                    quantity,
                    minimum_stock
                FROM products
                WHERE id = %s
                AND status = 'ACTIVE'
                FOR UPDATE;
            """, (product_id,))

            product = cursor.fetchone()

            if product is None:

                connection.rollback()

                return jsonify({
                    "error":
                        "Product not found or inactive."
                }), 404

            (
                product_id_db,
                product_name,
                previous_quantity,
                minimum_stock
            ) = product

            if new_quantity == previous_quantity:

                connection.rollback()

                return jsonify({
                    "error":
                        "New quantity is the same as current stock."
                }), 400

            difference = abs(
                new_quantity -
                previous_quantity
            )

            cursor.execute("""
                UPDATE products
                SET
                    quantity = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s;
            """, (
                new_quantity,
                product_id_db
            ))

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
                    'STOCK_ADJUSTMENT',
                    %s,
                    %s,
                    %s,
                    %s,
                    CURRENT_TIMESTAMP,
                    CURRENT_TIMESTAMP
                );
            """, (
                product_id_db,
                session["user_id"],
                difference,
                previous_quantity,
                new_quantity,
                reason
            ))

        connection.commit()

        low_stock = (
            new_quantity <= minimum_stock
        )

        return jsonify({
            "message": "Stock adjusted successfully.",
            "product": product_name,
            "previous_quantity": str(
                previous_quantity
            ),
            "new_quantity": str(
                new_quantity
            ),
            "difference": str(
                difference
            ),
            "minimum_stock": str(
                minimum_stock
            ),
            "low_stock": low_stock
        }), 201

    except Exception as e:

        connection.rollback()

        print(
            "STOCK ADJUSTMENT ERROR:",
            type(e).__name__,
            str(e)
        )

        return jsonify({
            "error": "Could not adjust stock."
        }), 500

    finally:
        connection.close()


# =========================================================
# STOCK HISTORY
#
# EMPLOYEE:
#     Own stock transactions only
#
# ADMIN:
#     All stock transactions
# =========================================================

@stock_routes.route("/api/stock", methods=["GET"])
def get_stock_transactions():

    if not stock_access_required():
        return jsonify({
            "error": "Login required."
        }), 401

    # Optional date filter.
    # Example:
    # /api/stock?date=2026-10-07
    selected_date = request.args.get("date")

    connection = get_db_connection()

    try:

        with connection.cursor() as cursor:

            if session.get("role") == "EMPLOYEE":

                if selected_date:

                    cursor.execute("""
                        SELECT
                            st.id,
                            st.product_id,
                            p.product_name,
                            st.employee_id,
                            e.full_name,
                            st.admin_id,
                            a.full_name,
                            st.transaction_type,
                            st.quantity,
                            st.previous_quantity,
                            st.new_quantity,
                            st.reason,
                            st.transaction_date

                        FROM stock_transactions st

                        JOIN products p
                            ON st.product_id = p.id

                        LEFT JOIN employees e
                            ON st.employee_id = e.id

                        LEFT JOIN admins a
                            ON st.admin_id = a.id

                        WHERE st.employee_id = %s
                        AND DATE(st.transaction_date) = %s

                        ORDER BY
                            st.transaction_date DESC,
                            st.id DESC;
                    """, (
                        session["user_id"],
                        selected_date
                    ))

                else:

                    cursor.execute("""
                        SELECT
                            st.id,
                            st.product_id,
                            p.product_name,
                            st.employee_id,
                            e.full_name,
                            st.admin_id,
                            a.full_name,
                            st.transaction_type,
                            st.quantity,
                            st.previous_quantity,
                            st.new_quantity,
                            st.reason,
                            st.transaction_date

                        FROM stock_transactions st

                        JOIN products p
                            ON st.product_id = p.id

                        LEFT JOIN employees e
                            ON st.employee_id = e.id

                        LEFT JOIN admins a
                            ON st.admin_id = a.id

                        WHERE st.employee_id = %s

                        ORDER BY
                            st.transaction_date DESC,
                            st.id DESC;
                    """, (
                        session["user_id"],
                    ))

            else:

                # Admin still sees all transactions.
                # If a date is supplied, filter all transactions
                # to that date.

                if selected_date:

                    cursor.execute("""
                        SELECT
                            st.id,
                            st.product_id,
                            p.product_name,
                            st.employee_id,
                            e.full_name,
                            st.admin_id,
                            a.full_name,
                            st.transaction_type,
                            st.quantity,
                            st.previous_quantity,
                            st.new_quantity,
                            st.reason,
                            st.transaction_date

                        FROM stock_transactions st

                        JOIN products p
                            ON st.product_id = p.id

                        LEFT JOIN employees e
                            ON st.employee_id = e.id

                        LEFT JOIN admins a
                            ON st.admin_id = a.id

                        WHERE DATE(st.transaction_date) = %s

                        ORDER BY
                            st.transaction_date DESC,
                            st.id DESC;
                    """, (
                        selected_date,
                    ))

                else:

                    cursor.execute("""
                        SELECT
                            st.id,
                            st.product_id,
                            p.product_name,
                            st.employee_id,
                            e.full_name,
                            st.admin_id,
                            a.full_name,
                            st.transaction_type,
                            st.quantity,
                            st.previous_quantity,
                            st.new_quantity,
                            st.reason,
                            st.transaction_date

                        FROM stock_transactions st

                        JOIN products p
                            ON st.product_id = p.id

                        LEFT JOIN employees e
                            ON st.employee_id = e.id

                        LEFT JOIN admins a
                            ON st.admin_id = a.id

                        ORDER BY
                            st.transaction_date DESC,
                            st.id DESC;
                    """)

            transactions = cursor.fetchall()

        return jsonify({
            "transactions": [

                {
                    "id": transaction[0],

                    "product_id":
                        transaction[1],

                    "product_name":
                        transaction[2],

                    "employee_id":
                        transaction[3],

                    "employee_name":
                        transaction[4],

                    "admin_id":
                        transaction[5],

                    "admin_name":
                        transaction[6],

                    "transaction_type":
                        transaction[7],

                    "quantity":
                        str(transaction[8]),

                    "previous_quantity":
                        str(transaction[9]),

                    "new_quantity":
                        str(transaction[10]),

                    "reason":
                        transaction[11],

                    "transaction_date":
                        transaction[12].isoformat()
                }

                for transaction in transactions
            ]
        })

    except Exception as e:

        print(
            "STOCK HISTORY ERROR:",
            type(e).__name__,
            str(e)
        )

        return jsonify({
            "error": "Could not load stock history."
        }), 500

    finally:
        connection.close()