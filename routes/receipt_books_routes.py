from flask import Blueprint, request, jsonify, session, render_template
from db import get_db_connection


receipt_books_routes = Blueprint(
    "receipt_books_routes",
    __name__
)


# =========================================================
# GET ALL RECEIPT BOOKS
# =========================================================

@receipt_books_routes.route(
    "/api/receipt-books",
    methods=["GET"]
)
def get_receipt_books():

    if "user_id" not in session:
        return jsonify({
            "error": "Login required."
        }), 401

    connection = None

    try:

        connection = get_db_connection()
        cursor = connection.cursor()

        cursor.execute("""
            SELECT
                id,
                book_number,
                book_year,
                start_number,
                end_number,
                number_width,
                started_at,
                ended_at,
                status,
                created_at
            FROM receipt_books
            ORDER BY book_year DESC, book_number DESC;
        """)

        rows = cursor.fetchall()

        receipt_books = []

        for row in rows:

            receipt_books.append({
                "id": row[0],
                "book_number": row[1],
                "book_year": row[2],
                "start_number": row[3],
                "end_number": row[4],
                "number_width": row[5],
                "started_at": row[6],
                "ended_at": row[7],
                "status": row[8],
                "created_at": row[9]
            })

        return jsonify(receipt_books)

    except Exception as e:

        print(
            "RECEIPT BOOK GET ERROR:",
            type(e).__name__,
            str(e)
        )

        return jsonify({
            "error": "Could not load receipt books."
        }), 500

    finally:

        if connection:
            connection.close()


# =========================================================
# ADD RECEIPT BOOK
# =========================================================

@receipt_books_routes.route(
    "/api/receipt-books",
    methods=["POST"]
)
def add_receipt_book():

    if "user_id" not in session:
        return jsonify({
            "error": "Login required."
        }), 401

    # Only admin can manage receipt books
    if session.get("role") != "ADMIN":
        return jsonify({
            "error": "Admin access required."
        }), 403

    data = request.get_json()

    if not data:
        return jsonify({
            "error": "No receipt book data was provided."
        }), 400

    book_number = data.get("book_number")
    book_year = data.get("book_year")
    start_number = data.get("start_number")
    end_number = data.get("end_number")
    number_width = data.get("number_width", 4)

    # Check required fields
    if (
        book_number is None
        or book_year is None
        or start_number is None
        or end_number is None
    ):
        return jsonify({
            "error": "All receipt book details are required."
        }), 400

    # Convert values to integers
    try:

        book_number = int(book_number)
        book_year = int(book_year)
        start_number = int(start_number)
        end_number = int(end_number)
        number_width = int(number_width)

    except (TypeError, ValueError):

        return jsonify({
            "error": "Receipt book values must be numbers."
        }), 400

    # Validate values
    if book_number <= 0:
        return jsonify({
            "error": "Book number must be greater than 0."
        }), 400

    if book_year <= 0:
        return jsonify({
            "error": "Book year must be valid."
        }), 400

    if start_number < 0:
        return jsonify({
            "error": "Starting receipt number cannot be negative."
        }), 400

    if end_number <= start_number:
        return jsonify({
            "error": "Ending receipt number must be greater than starting number."
        }), 400

    if number_width <= 0:
        return jsonify({
            "error": "Number width must be greater than 0."
        }), 400

    connection = None

    try:

        connection = get_db_connection()
        cursor = connection.cursor()

        # -------------------------------------------------
        # Check for duplicate book number
        # -------------------------------------------------

        cursor.execute("""
            SELECT id
            FROM receipt_books
            WHERE book_number = %s
              AND book_year = %s;
        """, (
            book_number,
            book_year
        ))

        existing_book = cursor.fetchone()

        if existing_book:

            return jsonify({
                "error": "A receipt book with this number already exists for this year."
            }), 409

        # -------------------------------------------------
        # Check whether another book is currently active
        # -------------------------------------------------

        cursor.execute("""
            SELECT id
            FROM receipt_books
            WHERE status = 'ACTIVE'
            LIMIT 1
            FOR UPDATE;
        """)

        active_book = cursor.fetchone()

        # If there is already an active book,
        # the new book waits as PENDING.
        if active_book:
            status = "PENDING"
        else:
            status = "ACTIVE"

        # -------------------------------------------------
        # Insert new receipt book
        # -------------------------------------------------

        cursor.execute("""
            INSERT INTO receipt_books
            (
                book_number,
                book_year,
                start_number,
                end_number,
                number_width,
                status
            )
            VALUES
            (
                %s,
                %s,
                %s,
                %s,
                %s,
                %s
            )
            RETURNING id;
        """, (
            book_number,
            book_year,
            start_number,
            end_number,
            number_width,
            status
        ))

        receipt_book_id = cursor.fetchone()[0]

        connection.commit()

        return jsonify({
            "message": "Receipt book added successfully.",
            "receipt_book_id": receipt_book_id,
            "status": status
        }), 201

    except Exception as e:

        if connection:
            connection.rollback()

        print(
            "RECEIPT BOOK ADD ERROR:",
            type(e).__name__,
            str(e)
        )

        return jsonify({
            "error": "Could not add receipt book."
        }), 500

    finally:

        if connection:
            connection.close()


# =========================================================
# CLOSE RECEIPT BOOK
# =========================================================

@receipt_books_routes.route(
    "/api/receipt-books/<int:book_id>/close",
    methods=["POST"]
)
def close_receipt_book(book_id):

    if "user_id" not in session:
        return jsonify({
            "error": "Login required."
        }), 401

    # Only admin can close receipt books
    if session.get("role") != "ADMIN":
        return jsonify({
            "error": "Admin access required."
        }), 403

    connection = None

    try:

        connection = get_db_connection()
        cursor = connection.cursor()

        # -------------------------------------------------
        # Get the book
        # -------------------------------------------------

        cursor.execute("""
            SELECT
                id,
                status
            FROM receipt_books
            WHERE id = %s
            FOR UPDATE;
        """, (book_id,))

        book = cursor.fetchone()

        if not book:

            return jsonify({
                "error": "Receipt book not found."
            }), 404

        # -------------------------------------------------
        # Make sure the book is currently active
        # -------------------------------------------------

        if book[1] != "ACTIVE":

            return jsonify({
                "error": "Only an active receipt book can be closed."
            }), 400

        # -------------------------------------------------
        # Close current book
        # -------------------------------------------------

        cursor.execute("""
            UPDATE receipt_books
            SET
                status = 'CLOSED',
                ended_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s;
        """, (book_id,))

        # -------------------------------------------------
        # Find the next pending book
        # -------------------------------------------------

        cursor.execute("""
            SELECT
                id
            FROM receipt_books
            WHERE status = 'PENDING'
            ORDER BY
                book_year ASC,
                book_number ASC
            LIMIT 1
            FOR UPDATE;
        """)

        next_book = cursor.fetchone()

        activated_book_id = None

        # -------------------------------------------------
        # Activate next pending book
        # -------------------------------------------------

        if next_book:

            activated_book_id = next_book[0]

            cursor.execute("""
                UPDATE receipt_books
                SET
                    status = 'ACTIVE',
                    started_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s;
            """, (activated_book_id,))

        # -------------------------------------------------
        # Save changes
        # -------------------------------------------------

        connection.commit()

        return jsonify({
            "message": "Receipt book closed successfully.",
            "activated_book_id": activated_book_id
        }), 200

    except Exception as e:

        if connection:
            connection.rollback()

        print(
            "RECEIPT BOOK CLOSE ERROR:",
            type(e).__name__,
            str(e)
        )

        return jsonify({
            "error": "Could not close receipt book."
        }), 500

    finally:

        if connection:
            connection.close()


# =========================================================
# RECEIPT BOOK MANAGEMENT PAGE
# =========================================================

@receipt_books_routes.route(
    "/receipt-books"
)
def receipt_books_page():

    if "user_id" not in session:
        return "Login required.", 401

    if session.get("role") != "ADMIN":
        return "Admin access required.", 403

    return render_template(
        "receipt_books.html"
    )