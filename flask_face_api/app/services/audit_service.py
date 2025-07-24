from app.db.mysql import get_mysql_connection

def log_activity(actor_email, action, details=""):
    """Logs an activity to the audit_logs table."""
    try:
        conn = get_mysql_connection()
        cur = conn.cursor()
        query = "INSERT INTO audit_logs (actor_email, action, details) VALUES (%s, %s, %s)"
        cur.execute(query, (actor_email, action, details))
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Failed to log activity: {e}")