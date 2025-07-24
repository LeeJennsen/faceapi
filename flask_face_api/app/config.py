import os
from dotenv import load_dotenv
load_dotenv()

class Config:
    MYSQL_HOST = os.getenv("MYSQL_HOST")
    MYSQL_USER = os.getenv("MYSQL_USER")
    MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD")
    MYSQL_DATABASE = os.getenv("MYSQL_DATABASE")
    MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
    JWT_EXPIRY_SECONDS = int(os.getenv("JWT_EXPIRY_SECONDS"))
    JWT_REFRESH_EXPIRY_SECONDS = int(os.getenv("JWT_REFRESH_EXPIRY_SECONDS"))

