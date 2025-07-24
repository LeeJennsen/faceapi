import os
import mysql.connector
from app.config import Config

def get_mysql_connection():
    return mysql.connector.connect(
     host=("mysql"),
     user=os.getenv("MYSQL_USER"),
     password=os.getenv("MYSQL_PASSWORD"),
     database=os.getenv("MYSQL_DATABASE"),
     port=3306

    )

def init_mysql(app):
    try:
        app.mysql = get_mysql_connection()
        print("MySQL connected")
    except mysql.connector.Error as err:
        print(f"MySQL connection error: {err}")
