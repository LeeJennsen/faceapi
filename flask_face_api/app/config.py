import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BASE_DIR / ".env")


def _get_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _get_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    return int(value)


class Config:
    APP_NAME = os.getenv("APP_NAME", "faceapi2")
    API_VERSION = os.getenv("API_VERSION", "1.0")
    API_TITLE = os.getenv("API_TITLE", "faceapi2 API")
    API_DESCRIPTION = os.getenv(
        "API_DESCRIPTION",
        "Face recognition platform API and dashboard.",
    )

    FLASK_ENV = os.getenv("FLASK_ENV", "production")
    DEBUG = _get_bool("FLASK_DEBUG", FLASK_ENV == "development")
    HOST = os.getenv("FLASK_HOST", "0.0.0.0")
    PORT = _get_int("PORT", _get_int("FLASK_PORT", 5000))

    MYSQL_HOST = os.getenv("MYSQL_HOST", "mysql")
    MYSQL_PORT = _get_int("MYSQL_PORT", 3306)
    MYSQL_USER = os.getenv("MYSQL_USER")
    MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD")
    MYSQL_DATABASE = os.getenv("MYSQL_DATABASE")
    MYSQL_POOL_NAME = os.getenv("MYSQL_POOL_NAME", "faceapi2_pool")
    MYSQL_POOL_SIZE = _get_int("MYSQL_POOL_SIZE", 5)

    MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/face_metadata")
    MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "face_metadata")
    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    REDIS_ENABLED = _get_bool("REDIS_ENABLED", False)

    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
    JWT_EXPIRY_SECONDS = _get_int("JWT_EXPIRY_SECONDS", 3600)
    JWT_REFRESH_EXPIRY_SECONDS = _get_int("JWT_REFRESH_EXPIRY_SECONDS", 604800)

    SMTP_SERVER = os.getenv("SMTP_SERVER")
    SMTP_PORT = _get_int("SMTP_PORT", 465)
    SMTP_USERNAME = os.getenv("SMTP_USERNAME")
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
    FROM_EMAIL = os.getenv("FROM_EMAIL")
    FROM_NAME = os.getenv("FROM_NAME", "faceapi2 Team")

    ADMIN_PROMOTION_CODE = os.getenv("ADMIN_PROMOTION_CODE")

    LOG_DIR = os.getenv("LOG_DIR", "logs")
    LOG_LEVEL = os.getenv("LOG_LEVEL", "DEBUG" if DEBUG else "INFO").upper()
    GRAFANA_PUBLIC_URL = os.getenv("GRAFANA_PUBLIC_URL", "http://localhost:3000")
    PROMETHEUS_PUBLIC_URL = os.getenv("PROMETHEUS_PUBLIC_URL", "http://localhost:9090")
    ALERTMANAGER_PUBLIC_URL = os.getenv("ALERTMANAGER_PUBLIC_URL", "http://localhost:9093")
    LOKI_PUBLIC_URL = os.getenv("LOKI_PUBLIC_URL", "http://localhost:3100")

    @classmethod
    def validate_required_settings(cls) -> list[str]:
        required_fields = (
            "MYSQL_USER",
            "MYSQL_PASSWORD",
            "MYSQL_DATABASE",
            "JWT_SECRET_KEY",
        )
        return [field for field in required_fields if not getattr(cls, field)]
