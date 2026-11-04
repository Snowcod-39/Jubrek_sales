import os

from flask import Flask, render_template, request, redirect, url_for, session
from werkzeug.security import check_password_hash
from dotenv import load_dotenv

from db import get_db_connection

from routes.employee_routes import employee_routes
from routes.category_routes import category_routes
from routes.product_routes import product_routes
from routes.stock_routes import stock_routes
from routes.sales_routes import sales_routes
from routes.expenses_routes import expenses_routes
from routes.reports_routes import reports_routes
from routes.receipt_books_routes import receipt_books_routes
from routes.orders_routes import orders_routes
from routes.dashboard_routes import dashboard_routes

load_dotenv()

app = Flask(__name__)

app.secret_key = os.getenv("FLASK_SECRET_KEY")
app.register_blueprint(employee_routes)
app.register_blueprint(category_routes)
app.register_blueprint(product_routes)
app.register_blueprint(stock_routes)
app.register_blueprint(sales_routes)
app.register_blueprint(expenses_routes)
app.register_blueprint(reports_routes)
app.register_blueprint(receipt_books_routes)
app.register_blueprint(orders_routes)
app.register_blueprint(dashboard_routes)


@app.route("/")
def home():
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        connection = get_db_connection()

        try:
            with connection.cursor() as cursor:

                # Check administrators first
                cursor.execute("""
                    SELECT id, full_name, username, password_hash
                    FROM admins
                    WHERE username = %s
                    AND status = 'ACTIVE'
                """, (username,))

                user = cursor.fetchone()

                if user:
                    user_id, full_name, db_username, password_hash = user

                    if check_password_hash(password_hash, password):
                        session["user_id"] = user_id
                        session["username"] = db_username
                        session["full_name"] = full_name
                        session["role"] = "ADMIN"

                        return redirect(url_for("admin_dashboard"))

                # If not an admin, check employees
                cursor.execute("""
                    SELECT id, full_name, username, password_hash
                    FROM employees
                    WHERE username = %s
                    AND status = 'ACTIVE'
                """, (username,))

                user = cursor.fetchone()

                if user:
                    user_id, full_name, db_username, password_hash = user

                    if check_password_hash(password_hash, password):
                        session["user_id"] = user_id
                        session["username"] = db_username
                        session["full_name"] = full_name
                        session["role"] = "EMPLOYEE"

                        return redirect(url_for("employee_dashboard"))

        finally:
            connection.close()

        return render_template(
            "login.html",
            error="Invalid username or password."
        )

    return render_template("login.html")


@app.route("/admin/dashboard")
def admin_dashboard():

    if "user_id" not in session or session.get("role") != "ADMIN":
        return redirect(url_for("login"))

    return render_template("admin_dashboard.html")


@app.route("/employee/dashboard")
def employee_dashboard():

    if "user_id" not in session or session.get("role") != "EMPLOYEE":
        return redirect(url_for("login"))

    return render_template("employee_dashboard.html")


@app.route("/logout")
def logout():

    session.clear()

    return redirect(url_for("login"))


@app.route("/test-db")
def test_db():

    try:
        connection = get_db_connection()

        with connection.cursor() as cursor:
            cursor.execute("SELECT current_database(), current_user;")
            result = cursor.fetchone()

        connection.close()

        return f"Database connected successfully! Database: {result[0]}, User: {result[1]}"

    except Exception as e:
        return f"Database connection failed: {type(e).__name__}: {e}", 500


if __name__ == "__main__":
    app.run(debug=True)