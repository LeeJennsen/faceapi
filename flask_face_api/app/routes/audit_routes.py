from flask import jsonify
from flask_restx import Namespace, Resource
from loguru import logger

from app.auth import admin_required
from app.db.mysql import mysql_cursor
from app.utils.serialization import serialize_datetime

api = Namespace("audit", description="Audit log operations")


@api.route("/logs")
class AuditLogs(Resource):
    @api.doc(description="Retrieve audit logs. Admin only.")
    @admin_required
    def get(self):
        try:
            with mysql_cursor(dictionary=True) as (_, cursor):
                cursor.execute(
                    "SELECT id, actor_email, action, details, timestamp FROM audit_logs ORDER BY timestamp DESC LIMIT 200"
                )
                logs = cursor.fetchall()

            for log in logs:
                log["timestamp"] = serialize_datetime(log.get("timestamp"))

            return jsonify({"logs": logs})
        except Exception:
            logger.exception("Failed to fetch audit logs.")
            return {"message": "Failed to fetch audit logs."}, 500
