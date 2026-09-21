from flask import Blueprint, request, jsonify, session, render_template, redirect, url_for
from decimal import Decimal, InvalidOperation
from db import get_db_connection


product_routes = Blueprint("product_routes", __name__)


# ============================================================
# ACCESS CHECK
# ============================================================

def admin_required():
    return (
        "user_id" in session
        and session.get("role") == "ADMIN"
    )


# ============================================================
# PRODUCT MANAGEMENT PAGE
# ============================================================

@product_routes.route("/admin/products")
def product_management():

    if not admin_required():
        return redirect(url_for("login"))

    return render_template("product_management.html")


# ============================================================
# CREATE PRODUCT
# ============================================================

@product_routes.route("/api/products", methods=["POST"])
def create_product():

    if not admin_required():
        return jsonify({"error": "Admin access required."}), 403

    data = request.get_json() or {}

    product_name = str(data.get("product_name", "")).strip()
    category_id = data.get("category_id")
    buying_price = data.get("buying_price")
    selling_price = data.get("selling_price")
    quantity = data.get("quantity", 0)
    minimum_stock = data.get("minimum_stock", 0)

    if not product_name:
        return jsonify({"error": "Product name is required."}), 400

    if category_id in (None, ""):
        return jsonify({"error": "Category is required."}), 400

    try:
        category_id = int(category_id)
        buying_price = Decimal(str(buying_price))
        selling_price = Decimal(str(selling_price))
        quantity = Decimal(str(quantity))
        minimum_stock = Decimal(str(minimum_stock))
    except (ValueError, TypeError, InvalidOperation):
        return jsonify({"error": "Enter valid product values."}), 400

    if buying_price < 0 or selling_price < 0:
        return jsonify({"error": "Prices cannot be negative."}), 400

    if quantity < 0 or minimum_stock < 0:
        return jsonify({"error": "Stock values cannot be negative."}), 400

    connection = get_db_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT id
                FROM categories
                WHERE id = %s
                  AND status = 'ACTIVE';
            """, (category_id,))

            if cursor.fetchone() is None:
                connection.rollback()
                return jsonify({"error": "Category not found or inactive."}), 400

            cursor.execute("""
                INSERT INTO products
                (
                    product_name,
                    category_id,
                    buying_price,
                    selling_price,
                    quantity,
                    minimum_stock,
                    status,
                    created_at,
                    updated_at
                )
                VALUES
                (
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    'ACTIVE',
                    CURRENT_TIMESTAMP,
                    CURRENT_TIMESTAMP
                )
                RETURNING id;
            """, (
                product_name,
                category_id,
                buying_price,
                selling_price,
                quantity,
                minimum_stock
            ))

            product_id = cursor.fetchone()[0]

        connection.commit()

        return jsonify({
            "message": "Product created successfully.",
            "product_id": product_id
        }), 201

    except Exception as e:
        connection.rollback()
        print("CREATE PRODUCT ERROR:", type(e).__name__, str(e))
        return jsonify({"error": "Could not create product."}), 500

    finally:
        connection.close()


# ============================================================
# GET PRODUCTS
# ADMIN: all products
# EMPLOYEE: active products only
# ============================================================

@product_routes.route("/api/products", methods=["GET"])
def get_products():

    if "user_id" not in session:
        return jsonify({"error": "Login required."}), 401

    role = session.get("role")

    if role not in ["ADMIN", "EMPLOYEE"]:
        return jsonify({"error": "Access denied."}), 403

    connection = get_db_connection()

    try:
        with connection.cursor() as cursor:

            if role == "ADMIN":
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
                        p.created_at,
                        p.updated_at
                    FROM products p
                    LEFT JOIN categories c
                        ON p.category_id = c.id
                    ORDER BY
                        CASE
                            WHEN p.status = 'ACTIVE'
                             AND p.quantity <= p.minimum_stock
                            THEN 0
                            ELSE 1
                        END,
                        p.quantity ASC,
                        p.product_name ASC;
                """)
            else:
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
                        p.created_at,
                        p.updated_at
                    FROM products p
                    LEFT JOIN categories c
                        ON p.category_id = c.id
                    WHERE p.status = 'ACTIVE'
                    ORDER BY
                        CASE
                            WHEN p.quantity <= p.minimum_stock
                            THEN 0
                            ELSE 1
                        END,
                        p.quantity ASC,
                        p.product_name ASC;
                """)

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
                    "created_at": product[9].isoformat() if product[9] else None,
                    "updated_at": product[10].isoformat() if product[10] else None
                }
                for product in products
            ]
        })

    except Exception as e:
        print("GET PRODUCTS ERROR:", type(e).__name__, str(e))
        return jsonify({"error": "Could not load products."}), 500

    finally:
        connection.close()


# ============================================================
# EDIT PRODUCT PRICES / MINIMUM STOCK
# ADMIN ONLY
# ============================================================

@product_routes.route("/api/products/<int:product_id>", methods=["PATCH"])
def update_product(product_id):

    if not admin_required():
        return jsonify({"error": "Admin access required."}), 403

    data = request.get_json() or {}

    if not data:
        return jsonify({"error": "Request data is required."}), 400

    connection = get_db_connection()

    try:
        with connection.cursor() as cursor:

            cursor.execute("""
                SELECT
                    id,
                    product_name,
                    category_id,
                    buying_price,
                    selling_price,
                    quantity,
                    minimum_stock,
                    status
                FROM products
                WHERE id = %s
                FOR UPDATE;
            """, (product_id,))

            product = cursor.fetchone()

            if product is None:
                connection.rollback()
                return jsonify({"error": "Product not found."}), 404

            current_buying_price = product[3]
            current_selling_price = product[4]
            current_minimum_stock = product[6]

            buying_price = data.get("buying_price", current_buying_price)
            selling_price = data.get("selling_price", current_selling_price)
            minimum_stock = data.get("minimum_stock", current_minimum_stock)

            try:
                buying_price = Decimal(str(buying_price))
                selling_price = Decimal(str(selling_price))
                minimum_stock = Decimal(str(minimum_stock))
            except (ValueError, TypeError, InvalidOperation):
                connection.rollback()
                return jsonify({"error": "Enter valid values."}), 400

            if buying_price < 0 or selling_price < 0:
                connection.rollback()
                return jsonify({"error": "Prices cannot be negative."}), 400

            if minimum_stock < 0:
                connection.rollback()
                return jsonify({"error": "Minimum stock cannot be negative."}), 400

            cursor.execute("""
                UPDATE products
                SET
                    buying_price = %s,
                    selling_price = %s,
                    minimum_stock = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s;
            """, (
                buying_price,
                selling_price,
                minimum_stock,
                product_id
            ))

        connection.commit()

        return jsonify({
            "message": "Product updated successfully.",
            "product_id": product_id
        }), 200

    except Exception as e:
        connection.rollback()
        print("UPDATE PRODUCT ERROR:", type(e).__name__, str(e))
        return jsonify({"error": "Could not update product."}), 500

    finally:
        connection.close()


# ============================================================
# DEACTIVATE PRODUCT
# ============================================================

@product_routes.route("/api/products/<int:product_id>/deactivate", methods=["PATCH"])
def deactivate_product(product_id):

    if not admin_required():
        return jsonify({"error": "Admin access required."}), 403

    connection = get_db_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                UPDATE products
                SET
                    status = 'INACTIVE',
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s;
            """, (product_id,))

            if cursor.rowcount == 0:
                connection.rollback()
                return jsonify({"error": "Product not found."}), 404

        connection.commit()
        return jsonify({"message": "Product deactivated successfully."}), 200

    except Exception as e:
        connection.rollback()
        print("DEACTIVATE PRODUCT ERROR:", type(e).__name__, str(e))
        return jsonify({"error": "Could not deactivate product."}), 500

    finally:
        connection.close()


# ============================================================
# REACTIVATE PRODUCT
# ============================================================

@product_routes.route("/api/products/<int:product_id>/reactivate", methods=["PATCH"])
def reactivate_product(product_id):

    if not admin_required():
        return jsonify({"error": "Admin access required."}), 403

    connection = get_db_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                UPDATE products
                SET
                    status = 'ACTIVE',
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s;
            """, (product_id,))

            if cursor.rowcount == 0:
                connection.rollback()
                return jsonify({"error": "Product not found."}), 404

        connection.commit()
        return jsonify({"message": "Product reactivated successfully."}), 200

    except Exception as e:
        connection.rollback()
        print("REACTIVATE PRODUCT ERROR:", type(e).__name__, str(e))
        return jsonify({"error": "Could not reactivate product."}), 500

    finally:
        connection.close()
