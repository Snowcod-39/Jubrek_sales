from flask import Blueprint, request, jsonify, session, render_template, redirect, url_for
from db import get_db_connection


category_routes = Blueprint("category_routes", __name__)


def admin_required():
    return (
        "user_id" in session
        and session.get("role") == "ADMIN"
    )


def category_read_required():
    return (
        "user_id" in session
        and session.get("role") in ["ADMIN", "EMPLOYEE"]
    )


# ============================================================
# ADMIN CATEGORY MANAGEMENT PAGE
# ============================================================

@category_routes.route("/admin/categories")
def category_management():
    if not admin_required():
        return redirect(url_for("login"))

    return render_template("category_management.html")


# ============================================================
# CREATE CATEGORY
# ADMIN ONLY
# ============================================================

@category_routes.route("/api/categories", methods=["POST"])
def create_category():
    if not admin_required():
        return jsonify({"error": "Admin access required."}), 403

    data = request.get_json()

    if not data:
        return jsonify({"error": "Request data is required."}), 400

    category_name = data.get("category_name", "").strip()

    if not category_name:
        return jsonify({
            "error": "Category name is required."
        }), 400

    connection = get_db_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                INSERT INTO categories
                    (category_name)
                VALUES
                    (%s)
                RETURNING id, category_name, status;
            """, (category_name,))

            category = cursor.fetchone()

        connection.commit()

        return jsonify({
            "message": "Category created successfully.",
            "category": {
                "id": category[0],
                "category_name": category[1],
                "status": category[2]
            }
        }), 201

    except Exception as e:
        connection.rollback()

        if "categories_category_name_unique_lower" in str(e):
            return jsonify({
                "error": "Category name already exists."
            }), 409

        return jsonify({
            "error": "Could not create category."
        }), 500

    finally:
        connection.close()


# ============================================================
# GET CATEGORIES
# ADMIN:
#   - Sees ACTIVE and INACTIVE categories
#
# EMPLOYEE:
#   - Sees ACTIVE categories only
# ============================================================

@category_routes.route("/api/categories", methods=["GET"])
def get_categories():
    if not category_read_required():
        return jsonify({"error": "Login required."}), 403

    connection = get_db_connection()

    try:
        with connection.cursor() as cursor:

            if session.get("role") == "EMPLOYEE":
                cursor.execute("""
                    SELECT id, category_name, status, created_at
                    FROM categories
                    WHERE status = 'ACTIVE'
                    ORDER BY id;
                """)
            else:
                cursor.execute("""
                    SELECT id, category_name, status, created_at
                    FROM categories
                    ORDER BY id;
                """)

            categories = cursor.fetchall()

        return jsonify({
            "categories": [
                {
                    "id": category[0],
                    "category_name": category[1],
                    "status": category[2],
                    "created_at": category[3].isoformat()
                }
                for category in categories
            ]
        })

    finally:
        connection.close()


# ============================================================
# DEACTIVATE CATEGORY
# ADMIN ONLY
# ============================================================

@category_routes.route(
    "/api/categories/<int:category_id>/deactivate",
    methods=["PATCH"]
)
def deactivate_category(category_id):

    if not admin_required():
        return jsonify({"error": "Admin access required."}), 403

    connection = get_db_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                UPDATE categories
                SET status = 'INACTIVE',
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
                RETURNING id, category_name, status;
            """, (category_id,))

            category = cursor.fetchone()

        if category is None:
            connection.rollback()
            return jsonify({"error": "Category not found."}), 404

        connection.commit()

        return jsonify({
            "message": "Category deactivated successfully.",
            "category": {
                "id": category[0],
                "category_name": category[1],
                "status": category[2]
            }
        })

    finally:
        connection.close()


# ============================================================
# REACTIVATE CATEGORY
# ADMIN ONLY
# ============================================================

@category_routes.route(
    "/api/categories/<int:category_id>/reactivate",
    methods=["PATCH"]
)
def reactivate_category(category_id):

    if not admin_required():
        return jsonify({"error": "Admin access required."}), 403

    connection = get_db_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                UPDATE categories
                SET status = 'ACTIVE',
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
                RETURNING id, category_name, status;
            """, (category_id,))

            category = cursor.fetchone()

        if category is None:
            connection.rollback()
            return jsonify({"error": "Category not found."}), 404

        connection.commit()

        return jsonify({
            "message": "Category reactivated successfully.",
            "category": {
                "id": category[0],
                "category_name": category[1],
                "status": category[2]
            }
        })

    finally:
        connection.close()