from flask import Blueprint, request, jsonify, session
from werkzeug.security import generate_password_hash

from db import get_db_connection


employee_routes = Blueprint("employee_routes", __name__)


def admin_required():
    return "user_id" in session and session.get("role") == "ADMIN"


@employee_routes.route("/api/employees", methods=["POST"])
def create_employee():
    if not admin_required():
        return jsonify({"error": "Admin access required."}), 403

    data = request.get_json()

    if not data:
        return jsonify({"error": "Request data is required."}), 400

    full_name = data.get("full_name", "").strip()
    username = data.get("username", "").strip()
    password = data.get("password", "")

    if not full_name or not username or not password:
        return jsonify({
            "error": "Full name, username and password are required."
        }), 400

    password_hash = generate_password_hash(password)

    connection = get_db_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                INSERT INTO employees
                    (full_name, username, password_hash)
                VALUES
                    (%s, %s, %s)
                RETURNING id, full_name, username, status;
            """, (full_name, username, password_hash))

            employee = cursor.fetchone()

        connection.commit()

        return jsonify({
            "message": "Employee created successfully.",
            "employee": {
                "id": employee[0],
                "full_name": employee[1],
                "username": employee[2],
                "status": employee[3]
            }
        }), 201

    except Exception as e:
        connection.rollback()

        if "employees_username_key" in str(e):
            return jsonify({
                "error": "Username already exists."
            }), 409

        return jsonify({
            "error": "Could not create employee."
        }), 500

    finally:
        connection.close()


@employee_routes.route("/api/employees", methods=["GET"])
def get_employees():
    if not admin_required():
        return jsonify({"error": "Admin access required."}), 403

    connection = get_db_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT id, full_name, username, status, created_at
                FROM employees
                ORDER BY id;
            """)

            employees = cursor.fetchall()

        return jsonify({
            "employees": [
                {
                    "id": employee[0],
                    "full_name": employee[1],
                    "username": employee[2],
                    "status": employee[3],
                    "created_at": employee[4].isoformat()
                }
                for employee in employees
            ]
        })

    finally:
        connection.close()


@employee_routes.route(
    "/api/employees/<int:employee_id>/deactivate",
    methods=["PATCH"]
)
def deactivate_employee(employee_id):
    if not admin_required():
        return jsonify({"error": "Admin access required."}), 403

    connection = get_db_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                UPDATE employees
                SET status = 'INACTIVE',
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
                RETURNING id, full_name, username, status;
            """, (employee_id,))

            employee = cursor.fetchone()

        if employee is None:
            connection.rollback()
            return jsonify({
                "error": "Employee not found."
            }), 404

        connection.commit()

        return jsonify({
            "message": "Employee deactivated successfully.",
            "employee": {
                "id": employee[0],
                "full_name": employee[1],
                "username": employee[2],
                "status": employee[3]
            }
        })

    finally:
        connection.close()


@employee_routes.route(
    "/api/employees/<int:employee_id>/reactivate",
    methods=["PATCH"]
)
def reactivate_employee(employee_id):
    if not admin_required():
        return jsonify({"error": "Admin access required."}), 403

    connection = get_db_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                UPDATE employees
                SET status = 'ACTIVE',
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
                RETURNING id, full_name, username, status;
            """, (employee_id,))

            employee = cursor.fetchone()

        if employee is None:
            connection.rollback()
            return jsonify({
                "error": "Employee not found."
            }), 404

        connection.commit()

        return jsonify({
            "message": "Employee reactivated successfully.",
            "employee": {
                "id": employee[0],
                "full_name": employee[1],
                "username": employee[2],
                "status": employee[3]
            }
        })

    finally:
        connection.close()