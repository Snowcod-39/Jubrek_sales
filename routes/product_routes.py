from flask import Blueprint, request, jsonify, session, render_template, redirect, url_for
from db import get_db_connection


product_routes = Blueprint("product_routes", __name__)


# =========================================================
# ADMIN CHECK
# =========================================================

def admin_required():
    return "user_id" in session and session.get("role") == "ADMIN"


# =========================================================
# PRODUCT MANAGEMENT PAGE
# =========================================================

@product_routes.route("/admin/products")
def product_management():

    if not admin_required():
        return redirect(url_for("login"))

    return render_template("product_management.html")


# =========================================================
# CREATE PRODUCT
# =========================================================

@product_routes.route("/api/products", methods=["POST"])
def create_product():

    if not admin_required():
        return jsonify({
            "error": "Admin access required."
        }), 403

    data = request.get_json()

    if not data:
        return jsonify({
            "error": "Request data is required."
        }), 400

    product_name = data.get("product_name", "").strip()
    category_id = data.get("category_id")
    buying_price = data.get("buying_price")
    selling_price = data.get("selling_price")
    quantity = data.get("quantity")
    minimum_stock = data.get("minimum_stock")

    # -----------------------------------------------------
    # Validation
    # -----------------------------------------------------

    if not product_name:
        return jsonify({
            "error": "Product name is required."
        }), 400

    if category_id is None or category_id == "":
        return jsonify({
            "error": "Category is required."
        }), 400

    if buying_price is None:
        return jsonify({
            "error": "Buying price is required."
        }), 400

    if selling_price is None:
        return jsonify({
            "error": "Selling price is required."
        }), 400

    if quantity is None:
        return jsonify({
            "error": "Quantity is required."
        }), 400

    if minimum_stock is None:
        return jsonify({
            "error": "Minimum stock is required."
        }), 400

    try:

        category_id = int(category_id)
        buying_price = float(buying_price)
        selling_price = float(selling_price)
        quantity = float(quantity)
        minimum_stock = float(minimum_stock)

    except (ValueError, TypeError):

        return jsonify({
            "error": "Invalid product values."
        }), 400

    if buying_price < 0:
        return jsonify({
            "error": "Buying price cannot be negative."
        }), 400

    if selling_price < 0:
        return jsonify({
            "error": "Selling price cannot be negative."
        }), 400

    if quantity < 0:
        return jsonify({
            "error": "Quantity cannot be negative."
        }), 400

    if minimum_stock < 0:
        return jsonify({
            "error": "Minimum stock cannot be negative."
        }), 400

    connection = get_db_connection()

    try:

        with connection.cursor() as cursor:

            # -------------------------------------------------
            # Check category
            # -------------------------------------------------

            cursor.execute("""
                SELECT id
                FROM categories
                WHERE id = %s
                AND status = 'ACTIVE';
            """, (category_id,))

            category = cursor.fetchone()

            if category is None:

                connection.rollback()

                return jsonify({
                    "error": "Selected category does not exist or is inactive."
                }), 400

            # -------------------------------------------------
            # Create product
            # -------------------------------------------------

            cursor.execute("""
                INSERT INTO products
                (
                    product_name,
                    category_id,
                    buying_price,
                    selling_price,
                    quantity,
                    minimum_stock,
                    status
                )
                VALUES
                (
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    'ACTIVE'
                )
                RETURNING
                    id,
                    product_name,
                    category_id,
                    buying_price,
                    selling_price,
                    quantity,
                    minimum_stock,
                    status;
            """, (
                product_name,
                category_id,
                buying_price,
                selling_price,
                quantity,
                minimum_stock
            ))

            product = cursor.fetchone()

        connection.commit()

        return jsonify({

            "message": "Product created successfully.",

            "product": {
                "id": product[0],
                "product_name": product[1],
                "category_id": product[2],
                "buying_price": str(product[3]),
                "selling_price": str(product[4]),
                "quantity": str(product[5]),
                "minimum_stock": str(product[6]),
                "status": product[7]
            }

        }), 201

    except Exception as e:

        connection.rollback()

        print(
            "PRODUCT CREATE ERROR:",
            type(e).__name__,
            str(e)
        )

        return jsonify({
            "error": "Could not create product."
        }), 500

    finally:

        connection.close()


# =========================================================
# GET PRODUCTS
# =========================================================

@product_routes.route("/api/products", methods=["GET"])
def get_products():

    # Must be logged in
    if "user_id" not in session:

        return jsonify({
            "error": "Login required."
        }), 401

    connection = get_db_connection()

    try:

        with connection.cursor() as cursor:

            # -------------------------------------------------
            # ADMIN
            # -------------------------------------------------
            # Admin can see all products,
            # including inactive products.

            if session.get("role") == "ADMIN":

                cursor.execute("""
                    SELECT
                        p.id,
                        p.product_name,
                        p.category_id,
                        c.category_name,
                        p.buying_price,
                        p.selling_price,
                        p.quantity,
                        p.minimum_stock,
                        p.status,
                        p.created_at
                    FROM products p
                    JOIN categories c
                        ON p.category_id = c.id
                    ORDER BY p.id;
                """)

            # -------------------------------------------------
            # EMPLOYEE
            # -------------------------------------------------
            # Employees can only see active products.

            elif session.get("role") == "EMPLOYEE":

                cursor.execute("""
                    SELECT
                        p.id,
                        p.product_name,
                        p.category_id,
                        c.category_name,
                        p.buying_price,
                        p.selling_price,
                        p.quantity,
                        p.minimum_stock,
                        p.status,
                        p.created_at
                    FROM products p
                    JOIN categories c
                        ON p.category_id = c.id
                    WHERE p.status = 'ACTIVE'
                    ORDER BY p.id;
                """)

            else:

                return jsonify({
                    "error": "Access denied."
                }), 403

            products = cursor.fetchall()

        return jsonify({

            "products": [

                {
                    "id": product[0],
                    "product_name": product[1],
                    "category_id": product[2],
                    "category_name": product[3],
                    "buying_price": str(product[4]),
                    "selling_price": str(product[5]),
                    "quantity": str(product[6]),
                    "minimum_stock": str(product[7]),
                    "status": product[8],
                    "created_at": product[9].isoformat()
                }

                for product in products

            ]

        })

    finally:

        connection.close()


# =========================================================
# DEACTIVATE PRODUCT
# =========================================================

@product_routes.route(
    "/api/products/<int:product_id>/deactivate",
    methods=["PATCH"]
)
def deactivate_product(product_id):

    if not admin_required():

        return jsonify({
            "error": "Admin access required."
        }), 403

    connection = get_db_connection()

    try:

        with connection.cursor() as cursor:

            cursor.execute("""
                UPDATE products
                SET
                    status = 'INACTIVE',
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
                RETURNING
                    id,
                    product_name,
                    status;
            """, (product_id,))

            product = cursor.fetchone()

        if product is None:

            connection.rollback()

            return jsonify({
                "error": "Product not found."
            }), 404

        connection.commit()

        return jsonify({

            "message": "Product deactivated successfully.",

            "product": {
                "id": product[0],
                "product_name": product[1],
                "status": product[2]
            }

        })

    finally:

        connection.close()


# =========================================================
# REACTIVATE PRODUCT
# =========================================================

@product_routes.route(
    "/api/products/<int:product_id>/reactivate",
    methods=["PATCH"]
)
def reactivate_product(product_id):

    if not admin_required():

        return jsonify({
            "error": "Admin access required."
        }), 403

    connection = get_db_connection()

    try:

        with connection.cursor() as cursor:

            cursor.execute("""
                UPDATE products
                SET
                    status = 'ACTIVE',
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
                RETURNING
                    id,
                    product_name,
                    status;
            """, (product_id,))

            product = cursor.fetchone()

        if product is None:

            connection.rollback()

            return jsonify({
                "error": "Product not found."
            }), 404

        connection.commit()

        return jsonify({

            "message": "Product reactivated successfully.",

            "product": {
                "id": product[0],
                "product_name": product[1],
                "status": product[2]
            }

        })

    finally:

        connection.close()