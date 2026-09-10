from getpass import getpass
from werkzeug.security import generate_password_hash

from db import get_db_connection

full_name=input("Admin full name: ").strip()
username=input("Admin Username: ").strip()
password=getpass("Admin password: ")

password_hash=generate_password_hash(password)

connection=get_db_connection()

try:
    with connection.cursor() as cursor:
        cursor.execute("""
        INSERT INTO admins(full_name, username, password_hash)
        VALUES(%s, %s, %s)""", (full_name, username, password_hash))

        connection.commit()

        print("Admin accoount created successfully")

finally:
    connection.close()