from flask import jsonify, request
from flask_restx import Namespace, Resource
from app.db.mysql import get_mysql_connection
from app.services.jwt_service import verify_token
from functools import wraps
from datetime import datetime

api = Namespace('audit', description='Audit log operations')

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')
        if not token or ' ' not in token: return {'message': 'Token is missing'}, 401
        user_id = verify_token(token.split(" ")[1])
        if not user_id: return {'message': 'Token is invalid or expired'}, 401
        
        conn = get_mysql_connection()
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT role FROM users WHERE id=%s", (user_id,))
        user = cur.fetchone()
        cur.close()
        conn.close()
        if user and user['role'] == 'Admin': return f(*args, **kwargs)
        else: return {"message": "Admin privileges required."}, 403
    return decorated

@api.route('/logs')
class AuditLogs(Resource):
    @api.doc(description="Retrieve audit logs. Admin only.")
    @admin_required
    def get(self):
        try:
            conn = get_mysql_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT id, actor_email, action, details, timestamp FROM audit_logs ORDER BY timestamp DESC LIMIT 200")
            logs = cursor.fetchall()
            for log in logs:
                if isinstance(log.get('timestamp'), datetime):
                    log['timestamp'] = log['timestamp'].isoformat()
            cursor.close()
            conn.close()
            return jsonify({"logs": logs})
        except Exception as e:
            return {"message": f"Failed to fetch audit logs: {e}"}, 500