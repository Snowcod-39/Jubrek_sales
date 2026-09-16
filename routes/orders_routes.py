from flask import Blueprint, request, jsonify, session, render_template
from decimal import Decimal
from db import get_db_connection


orders_routes = Blueprint(
    "orders_routes",
    __name__
)


# ============================================================
# EMPLOYEE ORDERS PAGE
# ============================================================

@orders_routes.route("/orders")
def orders_page():

    if "user_id" not in session:
        return jsonify({
            "error": "Login required."
        }), 401

    if session.get("role") != "EMPLOYEE":
        return jsonify({
            "error": "Employee access required."
        }), 403

    return render_template("employee_orders.html")


# ============================================================
# CREATE ORDER
# Customer can place an order
# ============================================================

@orders_routes.route(
    "/api/orders",
    methods=["POST"]
)
def create_order():

    data = request.get_json()

    if not data:
        return jsonify({
            "error": "Request data is required."
        }), 400

    customer_name = data.get("customer_name")
    customer_contact = data.get("customer_contact")
    items = data.get("items")

    if not customer_name:
        return jsonify({
            "error": "Customer name is required."
        }), 400

    if not items or not isinstance(items, list):
        return jsonify({
            "error": "Order must contain at least one product."
        }), 400

    connection = get_db_connection()

    try:

        with connection.cursor() as cursor:

            total_amount = Decimal("0.00")
            validated_items = []

            # ------------------------------------------------
            # Validate every product
            # ------------------------------------------------

            for item in items:

                product_id = item.get("product_id")
                quantity = item.get("quantity")

                if not product_id or quantity is None:
                    connection.rollback()
                    return jsonify({
                        "error":
                            "Each order item must have "
                            "product_id and quantity."
                    }), 400

                try:
                    quantity = Decimal(str(quantity))
                except Exception:
                    connection.rollback()
                    return jsonify({
                        "error": "Invalid product quantity."
                    }), 400

                if (
                    quantity <= 0
                    or quantity != quantity.to_integral_value()
                ):
                    connection.rollback()
                    return jsonify({
                        "error":
                            "Order quantity must be a whole "
                            "number greater than zero."
                    }), 400

                # Lock product while checking stock
                cursor.execute("""
                    SELECT
                        id,
                        product_name,
                        selling_price,
                        quantity,
                        status
                    FROM products
                    WHERE id = %s
                    FOR UPDATE;
                """, (product_id,))

                product = cursor.fetchone()

                if product is None:
                    connection.rollback()
                    return jsonify({
                        "error":
                            f"Product {product_id} not found."
                    }), 404

                (
                    product_id_db,
                    product_name,
                    selling_price,
                    available_quantity,
                    product_status
                ) = product

                if product_status != "ACTIVE":
                    connection.rollback()
                    return jsonify({
                        "error":
                            f"{product_name} is not available."
                    }), 400

                if quantity > available_quantity:
                    connection.rollback()
                    return jsonify({
                        "error":
                            f"Not enough stock for "
                            f"{product_name}. "
                            f"Available: {available_quantity}."
                    }), 400

                selling_price = Decimal(
                    str(selling_price)
                )

                subtotal = quantity * selling_price

                total_amount += subtotal

                validated_items.append({
                    "product_id": product_id_db,
                    "product_name": product_name,
                    "quantity": quantity,
                    "unit_price": selling_price,
                    "subtotal": subtotal
                })

            # ------------------------------------------------
            # Create order
            # ------------------------------------------------

            cursor.execute("""
                INSERT INTO orders
                (
                    customer_name,
                    customer_contact,
                    status,
                    total_amount,
                    processed_by,
                    created_at,
                    updated_at
                )
                VALUES
                (
                    %s,
                    %s,
                    'PENDING',
                    %s,
                    NULL,
                    CURRENT_TIMESTAMP,
                    CURRENT_TIMESTAMP
                )
                RETURNING id;
            """, (
                customer_name,
                customer_contact,
                total_amount
            ))

            order_id = cursor.fetchone()[0]

            # ------------------------------------------------
            # Create order items
            # ------------------------------------------------

            for item in validated_items:

                cursor.execute("""
                    INSERT INTO order_items
                    (
                        order_id,
                        product_id,
                        quantity,
                        unit_price,
                        subtotal,
                        created_at
                    )
                    VALUES
                    (
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        CURRENT_TIMESTAMP
                    );
                """, (
                    order_id,
                    item["product_id"],
                    item["quantity"],
                    item["unit_price"],
                    item["subtotal"]
                ))

        connection.commit()

        return jsonify({
            "message": "Order placed successfully.",
            "order_id": order_id,
            "status": "PENDING",
            "total_amount": str(total_amount)
        }), 201

    except Exception as e:

        connection.rollback()

        print(
            "CREATE ORDER ERROR:",
            type(e).__name__,
            str(e)
        )

        return jsonify({
            "error": "Could not create order."
        }), 500

    finally:
        connection.close()


# ============================================================
# GET ALL ORDERS
# Admin and employees
# ============================================================

@orders_routes.route(
    "/api/orders",
    methods=["GET"]
)
def get_orders():

    if "user_id" not in session:
        return jsonify({
            "error": "Login required."
        }), 401

    if session.get("role") not in [
        "ADMIN",
        "EMPLOYEE"
    ]:
        return jsonify({
            "error": "Access denied."
        }), 403

    connection = get_db_connection()

    try:

        with connection.cursor() as cursor:

            cursor.execute("""
                SELECT
                    o.id,
                    o.customer_name,
                    o.customer_contact,
                    o.status,
                    o.total_amount,
                    o.processed_by,
                    e.full_name,
                    o.created_at,
                    o.updated_at
                FROM orders o
                LEFT JOIN employees e
                    ON o.processed_by = e.id
                ORDER BY o.created_at DESC;
            """)

            orders = cursor.fetchall()

        return jsonify({
            "orders": [
                {
                    "id": order[0],
                    "customer_name": order[1],
                    "customer_contact": order[2],
                    "status": order[3],
                    "total_amount": str(order[4]),
                    "processed_by": order[5],
                    "processed_by_name": order[6],
                    "created_at": order[7].isoformat(),
                    "updated_at": order[8].isoformat()
                }
                for order in orders
            ]
        })

    finally:
        connection.close()


# ============================================================
# GET SINGLE ORDER
# Admin and employees
# ============================================================

@orders_routes.route(
    "/api/orders/<int:order_id>",
    methods=["GET"]
)
def get_order(order_id):

    if "user_id" not in session:
        return jsonify({
            "error": "Login required."
        }), 401

    if session.get("role") not in [
        "ADMIN",
        "EMPLOYEE"
    ]:
        return jsonify({
            "error": "Access denied."
        }), 403

    connection = get_db_connection()

    try:

        with connection.cursor() as cursor:

            cursor.execute("""
                SELECT
                    o.id,
                    o.customer_name,
                    o.customer_contact,
                    o.status,
                    o.total_amount,
                    o.processed_by,
                    e.full_name,
                    o.created_at,
                    o.updated_at
                FROM orders o
                LEFT JOIN employees e
                    ON o.processed_by = e.id
                WHERE o.id = %s;
            """, (order_id,))

            order = cursor.fetchone()

            if order is None:
                return jsonify({
                    "error": "Order not found."
                }), 404

            cursor.execute("""
                SELECT
                    oi.id,
                    oi.product_id,
                    p.product_name,
                    oi.quantity,
                    oi.unit_price,
                    oi.subtotal
                FROM order_items oi
                JOIN products p
                    ON oi.product_id = p.id
                WHERE oi.order_id = %s
                ORDER BY oi.id;
            """, (order_id,))

            items = cursor.fetchall()

            # ------------------------------------------------
            # Get sale/receipt information if payment exists
            # ------------------------------------------------

            cursor.execute("""
                SELECT
                    s.id,
                    s.receipt_book_id,
                    s.receipt_number,
                    s.payment_method,
                    s.payment_status,
                    s.delivery_status,
                    s.employee_id,
                    e.full_name,
                    s.released_by,
                    re.full_name,
                    s.released_at,
                    s.sale_date
                FROM sales s
                LEFT JOIN employees e
                    ON s.employee_id = e.id
                LEFT JOIN employees re
                    ON s.released_by = re.id
                WHERE s.order_id = %s
                ORDER BY s.id DESC
                LIMIT 1;
            """, (order_id,))

            sale = cursor.fetchone()

        response = {
            "id": order[0],
            "customer_name": order[1],
            "customer_contact": order[2],
            "status": order[3],
            "total_amount": str(order[4]),
            "processed_by": order[5],
            "processed_by_name": order[6],
            "created_at": order[7].isoformat(),
            "updated_at": order[8].isoformat(),

            "items": [
                {
                    "id": item[0],
                    "product_id": item[1],
                    "product_name": item[2],
                    "quantity": str(item[3]),
                    "unit_price": str(item[4]),
                    "subtotal": str(item[5])
                }
                for item in items
            ]
        }

        # ----------------------------------------------------
        # Add sale information if order has been paid
        # ----------------------------------------------------

        if sale:

            response["sale"] = {
                "sale_id": sale[0],
                "receipt_book_id": sale[1],
                "receipt_number": sale[2],
                "payment_method": sale[3],
                "payment_status": sale[4],
                "delivery_status": sale[5],
                "processed_by": sale[6],
                "processed_by_name": sale[7],
                "released_by": sale[8],
                "released_by_name": sale[9],
                "released_at": (
                    sale[10].isoformat()
                    if sale[10]
                    else None
                ),
                "sale_date": (
                    sale[11].isoformat()
                    if sale[11]
                    else None
                )
            }

        return jsonify({
            "order": response
        })

    finally:
        connection.close()


# ============================================================
# ACCEPT ORDER
#
# PENDING → PROCESSING
#
# This does NOT:
# - create a sale
# - generate a receipt
# - deduct stock
# - record payment
# ============================================================

@orders_routes.route(
    "/api/orders/<int:order_id>/process",
    methods=["POST"]
)
def process_order(order_id):

    if "user_id" not in session:
        return jsonify({
            "error": "Login required."
        }), 401

    if session.get("role") != "EMPLOYEE":
        return jsonify({
            "error": "Employee access required."
        }), 403

    connection = get_db_connection()

    try:

        with connection.cursor() as cursor:

            cursor.execute("""
                SELECT
                    id,
                    customer_name,
                    status,
                    processed_by
                FROM orders
                WHERE id = %s
                FOR UPDATE;
            """, (order_id,))

            order = cursor.fetchone()

            if order is None:
                connection.rollback()
                return jsonify({
                    "error": "Order not found."
                }), 404

            (
                order_id_db,
                customer_name,
                order_status,
                processed_by
            ) = order

            if order_status != "PENDING":
                connection.rollback()
                return jsonify({
                    "error":
                        f"Order is already {order_status}."
                }), 400

            # ------------------------------------------------
            # Assign order to current employee
            # ------------------------------------------------

            cursor.execute("""
                UPDATE orders
                SET
                    status = 'PROCESSING',
                    processed_by = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s;
            """, (
                session["user_id"],
                order_id
            ))

        connection.commit()

        return jsonify({
            "message": "Order accepted successfully.",
            "order_id": order_id_db,
            "status": "PROCESSING",
            "processed_by": session["user_id"]
        }), 200

    except Exception as e:

        connection.rollback()

        print(
            "ACCEPT ORDER ERROR:",
            type(e).__name__,
            str(e)
        )

        return jsonify({
            "error": "Could not accept order."
        }), 500

    finally:
        connection.close()


# ============================================================
# RECEIVE PAYMENT
#
# PROCESSING → PAID
#
# This:
# - creates the sale
# - creates sale items
# - assigns receipt number
# - records payment method
# - marks payment as PAID
#
# It does NOT deduct stock.
# ============================================================

@orders_routes.route(
    "/api/orders/<int:order_id>/pay",
    methods=["POST"]
)
def pay_order(order_id):

    if "user_id" not in session:
        return jsonify({
            "error": "Login required."
        }), 401

    if session.get("role") != "EMPLOYEE":
        return jsonify({
            "error": "Employee access required."
        }), 403

    data = request.get_json() or {}

    payment_method = data.get(
        "payment_method",
        "CASH"
    )

    if payment_method not in [
        "CASH",
        "MPESA"
    ]:
        return jsonify({
            "error":
                "Payment method must be CASH or MPESA."
        }), 400

    connection = get_db_connection()

    try:

        with connection.cursor() as cursor:

            # ------------------------------------------------
            # Lock order
            # ------------------------------------------------

            cursor.execute("""
                SELECT
                    id,
                    customer_name,
                    status,
                    total_amount,
                    processed_by
                FROM orders
                WHERE id = %s
                FOR UPDATE;
            """, (order_id,))

            order = cursor.fetchone()

            if order is None:
                connection.rollback()
                return jsonify({
                    "error": "Order not found."
                }), 404

            (
                order_id_db,
                customer_name,
                order_status,
                order_total,
                processed_by
            ) = order

            if order_status != "PROCESSING":
                connection.rollback()
                return jsonify({
                    "error":
                        f"Only PROCESSING orders can "
                        f"receive payment. "
                        f"Current status: {order_status}."
                }), 400

            # ------------------------------------------------
            # Employee ownership
            # ------------------------------------------------

            if processed_by != session["user_id"]:
                connection.rollback()
                return jsonify({
                    "error":
                        "You can only receive payment "
                        "for orders assigned to you."
                }), 403

            # ------------------------------------------------
            # Prevent duplicate sale
            # ------------------------------------------------

            cursor.execute("""
                SELECT
                    id,
                    receipt_number,
                    payment_status
                FROM sales
                WHERE order_id = %s
                FOR UPDATE;
            """, (order_id,))

            existing_sale = cursor.fetchone()

            if existing_sale is not None:
                connection.rollback()
                return jsonify({
                    "error":
                        "A sale has already been created "
                        "for this order.",
                    "sale_id": existing_sale[0],
                    "receipt_number": existing_sale[1],
                    "payment_status": existing_sale[2]
                }), 409

            # ------------------------------------------------
            # Get order items and lock products
            # ------------------------------------------------

            cursor.execute("""
                SELECT
                    oi.product_id,
                    oi.quantity,
                    p.product_name,
                    p.buying_price,
                    p.selling_price,
                    p.quantity,
                    p.status
                FROM order_items oi
                JOIN products p
                    ON oi.product_id = p.id
                WHERE oi.order_id = %s
                ORDER BY oi.id
                FOR UPDATE OF p;
            """, (order_id,))

            items = cursor.fetchall()

            if not items:
                connection.rollback()
                return jsonify({
                    "error": "This order has no products."
                }), 400

            total_amount = Decimal("0.00")
            sale_items = []

            # ------------------------------------------------
            # Validate products
            # ------------------------------------------------

            for item in items:

                (
                    product_id,
                    quantity,
                    product_name,
                    buying_price,
                    selling_price,
                    available_quantity,
                    product_status
                ) = item

                if product_status != "ACTIVE":
                    connection.rollback()
                    return jsonify({
                        "error":
                            f"{product_name} is no longer available."
                    }), 400

                # We still check stock before accepting payment.
                # Stock will only be deducted during RELEASE.

                if quantity > available_quantity:
                    connection.rollback()
                    return jsonify({
                        "error":
                            f"Not enough stock for "
                            f"{product_name}. "
                            f"Available: {available_quantity}, "
                            f"Required: {quantity}."
                    }), 400

                buying_price = Decimal(
                    str(buying_price)
                )

                selling_price = Decimal(
                    str(selling_price)
                )

                quantity = Decimal(
                    str(quantity)
                )

                subtotal = (
                    quantity * selling_price
                )

                total_amount += subtotal

                sale_items.append({
                    "product_id": product_id,
                    "quantity": quantity,
                    "buying_price": buying_price,
                    "selling_price": selling_price,
                    "subtotal": subtotal
                })

            # ------------------------------------------------
            # SYSTEM RECEIPT NUMBER
            #
            # SYSTEM receipts do NOT use receipt books.
            # Their numbers are generated independently and
            # remain globally unique.
            # ------------------------------------------------

            cursor.execute("""
                SELECT
                    COALESCE(MAX(receipt_number), 0) + 1
                FROM sales
                WHERE receipt_type = 'SYSTEM';
            """)

            next_receipt_number = cursor.fetchone()[0]

            # ------------------------------------------------
            # Create sale
            # ------------------------------------------------

            cursor.execute("""
                INSERT INTO sales
                (
                    employee_id,
                    receipt_book_id,
                    receipt_number,
                    order_id,
                    total_amount,
                    payment_method,
                    payment_status,
                    sale_date,
                    created_at,
                    delivery_status,
                    receipt_type,
                    released_by,
                    released_at
                )
                VALUES
                (
                    %s,
                    NULL,
                    %s,
                    %s,
                    %s,
                    %s,
                    'PAID',
                    CURRENT_TIMESTAMP,
                    CURRENT_TIMESTAMP,
                    'NOT RELEASED',
                    'SYSTEM',
                    NULL,
                    NULL
                )
                RETURNING id;
            """, (
                session["user_id"],
                next_receipt_number,
                order_id,
                total_amount,
                payment_method
            ))

            sale_id = cursor.fetchone()[0]

            # ------------------------------------------------
            # Create sale items
            # ------------------------------------------------

            for item in sale_items:

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
                    item["product_id"],
                    item["quantity"],
                    item["selling_price"],
                    item["buying_price"],
                    item["subtotal"]
                ))

            # ------------------------------------------------
            # Mark order as PAID
            # ------------------------------------------------

            cursor.execute("""
                UPDATE orders
                SET
                    status = 'PAID',
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s;
            """, (order_id,))

        connection.commit()

        return jsonify({
            "message":
                "Payment received and receipt generated.",
            "order_id": order_id_db,
            "sale_id": sale_id,
            "receipt_book_id": None,
            "receipt_number": next_receipt_number,
            "payment_method": payment_method,
            "payment_status": "PAID",
            "status": "PAID",
            "delivery_status": "NOT RELEASED"
        }), 201

    except Exception as e:

        connection.rollback()

        print(
            "PAY ORDER ERROR:",
            type(e).__name__,
            str(e)
        )

        return jsonify({
            "error":
                "Could not receive payment."
        }), 500

    finally:
        connection.close()


# ============================================================
# RELEASE SALE
#
# PAID → RELEASED
#
# This:
# - verifies the sale is paid
# - locks the products
# - checks stock
# - deducts stock
# - records stock transaction
# - records releasing employee
# - records release time
# ============================================================

@orders_routes.route(
    "/api/orders/<int:order_id>/release",
    methods=["POST"]
)
def release_order(order_id):

    if "user_id" not in session:
        return jsonify({
            "error": "Login required."
        }), 401

    if session.get("role") != "EMPLOYEE":
        return jsonify({
            "error": "Employee access required."
        }), 403

    connection = get_db_connection()

    try:

        with connection.cursor() as cursor:

            # ------------------------------------------------
            # Lock order
            # ------------------------------------------------

            cursor.execute("""
                SELECT
                    id,
                    customer_name,
                    status,
                    total_amount
                FROM orders
                WHERE id = %s
                FOR UPDATE;
            """, (order_id,))

            order = cursor.fetchone()

            if order is None:
                connection.rollback()
                return jsonify({
                    "error": "Order not found."
                }), 404

            (
                order_id_db,
                customer_name,
                order_status,
                order_total
            ) = order

            if order_status != "PAID":
                connection.rollback()
                return jsonify({
                    "error":
                        f"Only PAID orders can be released. "
                        f"Current status: {order_status}."
                }), 400

            # ------------------------------------------------
            # Find and lock sale
            # ------------------------------------------------

            cursor.execute("""
                SELECT
                    id,
                    employee_id,
                    receipt_book_id,
                    receipt_number,
                    payment_status,
                    delivery_status
                FROM sales
                WHERE order_id = %s
                FOR UPDATE;
            """, (order_id,))

            sale = cursor.fetchone()

            if sale is None:
                connection.rollback()
                return jsonify({
                    "error":
                        "No sale exists for this order."
                }), 400

            (
                sale_id,
                sale_employee_id,
                receipt_book_id,
                receipt_number,
                payment_status,
                delivery_status
            ) = sale

            if payment_status != "PAID":
                connection.rollback()
                return jsonify({
                    "error":
                        "This sale has not been paid."
                }), 400

            if delivery_status == "RELEASED":
                connection.rollback()
                return jsonify({
                    "error":
                        "This sale has already been released."
                }), 400

            # ------------------------------------------------
            # Get sale items and lock products
            # ------------------------------------------------

            cursor.execute("""
                SELECT
                    si.product_id,
                    si.quantity,
                    p.product_name,
                    p.quantity,
                    p.status
                FROM sale_items si
                JOIN products p
                    ON si.product_id = p.id
                WHERE si.sale_id = %s
                ORDER BY si.id
                FOR UPDATE OF p;
            """, (sale_id,))

            items = cursor.fetchall()

            if not items:
                connection.rollback()
                return jsonify({
                    "error":
                        "This sale has no products."
                }), 400

            # ------------------------------------------------
            # Validate all stock BEFORE changing anything
            # ------------------------------------------------

            release_items = []

            for item in items:

                (
                    product_id,
                    quantity,
                    product_name,
                    current_quantity,
                    product_status
                ) = item

                if product_status != "ACTIVE":
                    connection.rollback()
                    return jsonify({
                        "error":
                            f"{product_name} is no longer active."
                    }), 400

                quantity = Decimal(str(quantity))
                current_quantity = Decimal(
                    str(current_quantity)
                )

                if quantity > current_quantity:
                    connection.rollback()
                    return jsonify({
                        "error":
                            f"Not enough stock to release "
                            f"{product_name}. "
                            f"Available: {current_quantity}, "
                            f"Required: {quantity}."
                    }), 400

                new_quantity = (
                    current_quantity - quantity
                )

                release_items.append({
                    "product_id": product_id,
                    "product_name": product_name,
                    "quantity": quantity,
                    "previous_quantity": current_quantity,
                    "new_quantity": new_quantity
                })

            # ------------------------------------------------
            # Deduct stock and create stock transactions
            # ------------------------------------------------

            for item in release_items:

                cursor.execute("""
                    UPDATE products
                    SET
                        quantity = %s,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s;
                """, (
                    item["new_quantity"],
                    item["product_id"]
                ))

                cursor.execute("""
                    INSERT INTO stock_transactions
                    (
                        product_id,
                        employee_id,
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
                        'SALE_OUT',
                        %s,
                        %s,
                        %s,
                        %s,
                        CURRENT_TIMESTAMP,
                        CURRENT_TIMESTAMP
                    );
                """, (
                    item["product_id"],
                    session["user_id"],
                    item["quantity"],
                    item["previous_quantity"],
                    item["new_quantity"],
                    f"Released Sale #{receipt_number}"
                ))

            # ------------------------------------------------
            # Mark sale as released
            # ------------------------------------------------

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

            # ------------------------------------------------
            # Mark order as RELEASED
            # ------------------------------------------------

            cursor.execute("""
                UPDATE orders
                SET
                    status = 'RELEASED',
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s;
            """, (order_id,))

        connection.commit()

        return jsonify({
            "message":
                "Sale released successfully. Stock updated.",
            "order_id": order_id_db,
            "sale_id": sale_id,
            "receipt_number": receipt_number,
            "status": "RELEASED",
            "delivery_status": "RELEASED",
            "released_by": session["user_id"]
        }), 200

    except Exception as e:

        connection.rollback()

        print(
            "RELEASE ORDER ERROR:",
            type(e).__name__,
            str(e)
        )

        return jsonify({
            "error":
                "Could not release sale."
        }), 500

    finally:
        connection.close()


# ============================================================
# UPDATE ORDER STATUS
#
# Used only for CANCELLED / REJECTED.
#
# PAID and RELEASED are deliberately NOT allowed here.
# They must go through the proper payment/release endpoints.
# ============================================================

@orders_routes.route(
    "/api/orders/<int:order_id>/status",
    methods=["PATCH"]
)
def update_order_status(order_id):

    if "user_id" not in session:
        return jsonify({
            "error": "Login required."
        }), 401

    if session.get("role") not in [
        "ADMIN",
        "EMPLOYEE"
    ]:
        return jsonify({
            "error": "Access denied."
        }), 403

    data = request.get_json() or {}

    new_status = data.get("status")

    allowed_statuses = [
        "CANCELLED",
        "REJECTED"
    ]

    if new_status not in allowed_statuses:
        return jsonify({
            "error":
                "This endpoint can only be used for "
                "CANCELLED or REJECTED orders."
        }), 400

    connection = get_db_connection()

    try:

        with connection.cursor() as cursor:

            cursor.execute("""
                SELECT
                    id,
                    status,
                    processed_by
                FROM orders
                WHERE id = %s
                FOR UPDATE;
            """, (order_id,))

            order = cursor.fetchone()

            if order is None:
                connection.rollback()
                return jsonify({
                    "error": "Order not found."
                }), 404

            (
                order_id_db,
                current_status,
                processed_by
            ) = order

            # ------------------------------------------------
            # Cannot cancel/reject paid or released orders
            # ------------------------------------------------

            if current_status in [
                "PAID",
                "RELEASED",
                "CANCELLED",
                "REJECTED"
            ]:
                connection.rollback()
                return jsonify({
                    "error":
                        f"Order is already {current_status} "
                        "and cannot be changed."
                }), 400

            # ------------------------------------------------
            # Employee ownership for PROCESSING orders
            # ------------------------------------------------

            if current_status == "PROCESSING":

                if (
                    session.get("role") == "EMPLOYEE"
                    and processed_by != session["user_id"]
                ):
                    connection.rollback()
                    return jsonify({
                        "error":
                            "You can only manage orders "
                            "assigned to you."
                    }), 403

            # ------------------------------------------------
            # Update order
            # ------------------------------------------------

            cursor.execute("""
                UPDATE orders
                SET
                    status = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s;
            """, (
                new_status,
                order_id
            ))

        connection.commit()

        return jsonify({
            "message":
                f"Order {new_status.lower()} successfully.",
            "order_id": order_id_db,
            "status": new_status
        }), 200

    except Exception as e:

        connection.rollback()

        print(
            "UPDATE ORDER STATUS ERROR:",
            type(e).__name__,
            str(e)
        )

        return jsonify({
            "error":
                "Could not update order status."
        }), 500

    finally:
        connection.close()


# ============================================================
# EMPLOYEE: GET PENDING ORDERS
# ============================================================

@orders_routes.route(
    "/api/orders/pending",
    methods=["GET"]
)
def get_pending_orders():

    if "user_id" not in session:
        return jsonify({
            "error": "Login required."
        }), 401

    if session.get("role") != "EMPLOYEE":
        return jsonify({
            "error": "Employee access required."
        }), 403

    connection = get_db_connection()

    try:

        with connection.cursor() as cursor:

            cursor.execute("""
                SELECT
                    o.id,
                    o.customer_name,
                    o.customer_contact,
                    o.total_amount,
                    o.created_at
                FROM orders o
                WHERE o.status = 'PENDING'
                ORDER BY o.created_at ASC;
            """)

            orders = cursor.fetchall()

        return jsonify({
            "orders": [
                {
                    "id": order[0],
                    "customer_name": order[1],
                    "customer_contact": order[2],
                    "total_amount": str(order[3]),
                    "created_at": order[4].isoformat()
                }
                for order in orders
            ]
        })

    finally:
        connection.close()


# ============================================================
# EMPLOYEE: GET MY ORDERS
# ============================================================

@orders_routes.route(
    "/api/orders/my-orders",
    methods=["GET"]
)
def get_my_orders():

    if "user_id" not in session:
        return jsonify({
            "error": "Login required."
        }), 401

    if session.get("role") != "EMPLOYEE":
        return jsonify({
            "error": "Employee access required."
        }), 403

    connection = get_db_connection()

    try:

        with connection.cursor() as cursor:

            cursor.execute("""
                SELECT
                    o.id,
                    o.customer_name,
                    o.customer_contact,
                    o.status,
                    o.total_amount,
                    o.created_at,
                    o.updated_at
                FROM orders o
                WHERE o.processed_by = %s
                ORDER BY o.updated_at DESC;
            """, (session["user_id"],))

            orders = cursor.fetchall()

        return jsonify({
            "orders": [
                {
                    "id": order[0],
                    "customer_name": order[1],
                    "customer_contact": order[2],
                    "status": order[3],
                    "total_amount": str(order[4]),
                    "created_at": order[5].isoformat(),
                    "updated_at": order[6].isoformat()
                }
                for order in orders
            ]
        })

    finally:
        connection.close()


# ============================================================
# CUSTOMER: CUSTOMER PAGE
# ============================================================

@orders_routes.route("/customer")
def customer_page():

    return render_template("customer_orders.html")


# ============================================================
# CUSTOMER: VIEW PRODUCTS AND AVAILABILITY
# Customer sees availability only, NOT stock quantity
# ============================================================

@orders_routes.route(
    "/api/customer/products",
    methods=["GET"]
)
def get_customer_products():

    connection = get_db_connection()

    try:

        with connection.cursor() as cursor:

            cursor.execute("""
                SELECT
                    p.id,
                    p.product_name,
                    c.category_name,
                    p.selling_price,
                    p.quantity
                FROM products p
                LEFT JOIN categories c
                    ON p.category_id = c.id
                WHERE p.status = 'ACTIVE'
                ORDER BY p.product_name;
            """)

            products = cursor.fetchall()

        return jsonify({
            "products": [
                {
                    "id": product[0],
                    "product_name": product[1],
                    "category_name": product[2],
                    "selling_price": str(product[3]),
                    "available": product[4] > 0
                }
                for product in products
            ]
        })

    except Exception as e:

        print(
            "CUSTOMER PRODUCTS ERROR:",
            type(e).__name__,
            str(e)
        )

        return jsonify({
            "error": "Could not load products."
        }), 500

    finally:
        connection.close()


# ============================================================
# CUSTOMER: CHECK ORDER
# Customer uses order ID + contact
# ============================================================

@orders_routes.route(
    "/api/customer/orders/<int:order_id>",
    methods=["POST"]
)
def customer_check_order(order_id):

    data = request.get_json() or {}

    customer_contact = data.get(
        "customer_contact",
        ""
    ).strip()

    if not customer_contact:
        return jsonify({
            "error": "Customer contact is required."
        }), 400

    connection = get_db_connection()

    try:

        with connection.cursor() as cursor:

            cursor.execute("""
                SELECT
                    id,
                    customer_name,
                    customer_contact,
                    status,
                    total_amount,
                    created_at,
                    updated_at
                FROM orders
                WHERE id = %s
                  AND customer_contact = %s;
            """, (
                order_id,
                customer_contact
            ))

            order = cursor.fetchone()

            if order is None:
                return jsonify({
                    "error": "Order not found."
                }), 404

            cursor.execute("""
                SELECT
                    p.product_name,
                    oi.quantity,
                    oi.unit_price,
                    oi.subtotal
                FROM order_items oi
                JOIN products p
                    ON oi.product_id = p.id
                WHERE oi.order_id = %s
                ORDER BY oi.id;
            """, (order_id,))

            items = cursor.fetchall()

        return jsonify({

            "order": {

                "id": order[0],

                "customer_name": order[1],

                "status": order[3],

                "total_amount": str(
                    order[4]
                ),

                "created_at":
                    order[5].isoformat(),

                "updated_at":
                    order[6].isoformat(),

                "items": [

                    {
                        "product_name": item[0],

                        "quantity": str(
                            item[1]
                        ),

                        "unit_price": str(
                            item[2]
                        ),

                        "subtotal": str(
                            item[3]
                        )
                    }

                    for item in items
                ]
            }
        })

    except Exception as e:

        print(
            "CUSTOMER ORDER CHECK ERROR:",
            type(e).__name__,
            str(e)
        )

        return jsonify({
            "error": "Could not check order."
        }), 500

    finally:

        connection.close()
