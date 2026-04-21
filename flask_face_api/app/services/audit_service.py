from loguru import logger

from app.db.mysql import mysql_cursor


def log_activity(actor_email, action, details=""):
    try:
        with mysql_cursor() as (conn, cursor):
            cursor.execute(
                "INSERT INTO audit_logs (actor_email, action, details) VALUES (%s, %s, %s)",
                (actor_email, action, details),
            )
            conn.commit()
    except Exception as exc:
        logger.warning("Failed to persist audit log for {}: {}", actor_email, exc)
