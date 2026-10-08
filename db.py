import os

import psycopg

from dotenv import load_dotenv

load_dotenv()


def get_db_connection():

    connection = psycopg.connect(
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT"),
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
    )

    # =====================================================
    # JUBREK TIMEZONE
    # =====================================================
    # Railway/PostgreSQL may use UTC by default.
    # Jubrek operates in Kenya, so all database sessions
    # should use East Africa Time (Africa/Nairobi).
    #
    # Africa/Nairobi = UTC+3
    # =====================================================

    with connection.cursor() as cursor:
        cursor.execute(
            "SET TIME ZONE 'Africa/Nairobi';"
        )

    return connection

