from flask import Blueprint, request, jsonify, session

from db import get_db_connection


category_routes = Blueprint("category_routes", __name__)


def admin_required():
    return "user_id" in session and session.get("role") == "ADMIN"


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

        if "categories_category_name_key" in str(e):
            return jsonify({
                "error": "Category name already exists."
            }), 409

        return jsonify({
            "error": "Could not create category."
        }), 500

    finally:
        connection.close()


@category_routes.route("/api/categories", methods=["GET"])
def get_categories():
    if not admin_required():
        return jsonify({"error": "Admin access required."}), 403

    connection = get_db_connection()

    try:
        with connection.cursor() as cursor:
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