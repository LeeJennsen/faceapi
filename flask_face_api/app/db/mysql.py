from contextlib import contextmanager
from threading import Lock

import mysql.connector
from loguru import logger
from mysql.connector.pooling import MySQLConnectionPool

from app.config import Config

_pool = None
_pool_lock = Lock()


def _build_pool() -> MySQLConnectionPool:
    return MySQLConnectionPool(
        pool_name=Config.MYSQL_POOL_NAME,
        pool_size=Config.MYSQL_POOL_SIZE,
        host=Config.MYSQL_HOST,
        port=Config.MYSQL_PORT,
        user=Config.MYSQL_USER,
        password=Config.MYSQL_PASSWORD,
        database=Config.MYSQL_DATABASE,
    )


def get_mysql_pool() -> MySQLConnectionPool:
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                _pool = _build_pool()
                logger.info("MySQL connection pool initialized")
    return _pool


def get_mysql_connection():
    return get_mysql_pool().get_connection()


@contextmanager
def mysql_connection():
    conn = get_mysql_connection()
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def mysql_cursor(*, dictionary: bool = False):
    with mysql_connection() as conn:
        cursor = conn.cursor(dictionary=dictionary)
        try:
            yield conn, cursor
        finally:
            cursor.close()


def init_mysql(app):
    try:
        app.extensions["mysql_pool"] = get_mysql_pool()
        logger.info("MySQL integration ready")
    except mysql.connector.Error as exc:
        logger.error("MySQL initialization failed: {}", exc)


def check_mysql_connection() -> tuple[bool, str | None]:
    try:
        connection = get_mysql_connection()
    except mysql.connector.Error as exc:
        logger.warning("MySQL health check failed during connection acquisition: {}", exc)
        return False, str(exc)

    try:
        connection.ping(reconnect=False, attempts=1, delay=0)
        return True, None
    except mysql.connector.Error as exc:
        logger.warning("MySQL health check failed during ping: {}", exc)
        return False, str(exc)
    finally:
        connection.close()
