from flask import jsonify
from flask_restx import Namespace, Resource
from app.db.mysql import get_mysql_connection
from app.db.mongo import db as mongo_db
from app.services.jwt_service import verify_token
from functools import wraps
from flask import request
from datetime import datetime
from loguru import logger

api = Namespace('data', description='Data export operations')

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

def serialize_datetime(obj):
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError("Type not serializable")
    
@api.route('/export')
class ExportData(Resource):
    @api.doc(description="Export all major data from the database as a single JSON file. Admin only.")
    @admin_required
    def get(self):
        try:
            conn = get_mysql_connection()
            cursor = conn.cursor(dictionary=True)
            
            logger.info("Exporting: Fetching users...")
            cursor.execute("SELECT id, name, email, role, last_login, created_at FROM users")
            users = cursor.fetchall()
            logger.info(f"Found {len(users)} users.")
            
            logger.info("Exporting: Fetching face_persons...")
            cursor.execute("SELECT id, unique_id, label, created_at FROM face_persons")
            persons = cursor.fetchall()
            logger.info(f"Found {len(persons)} persons.")
            
            logger.info("Exporting: Fetching face_tracking...")
            cursor.execute("SELECT id, track_id, unique_id, timestamp, camera_id, custom_track_key FROM face_tracking")
            tracking = cursor.fetchall()
            logger.info(f"Found {len(tracking)} tracking records.")

            cursor.close()
            conn.close()

            logger.info("Exporting: Fetching mongo detections...")
            detections_collection = mongo_db.get_collection("detections")
            mongo_data = list(detections_collection.find({}, {'_id': 0}).limit(500))
            logger.info(f"Found {len(mongo_data)} mongo documents.")
            
            export_data = {
                "users": users,
                "persons": persons,
                "tracking": tracking,
                "mongo_detections_sample": mongo_data
            }
            
            # Manually serialize datetime objects
            for user in export_data["users"]:
                user["last_login"] = serialize_datetime(user["last_login"]) if user.get("last_login") else None
                user["created_at"] = serialize_datetime(user["created_at"]) if user.get("created_at") else None
            for person in export_data["persons"]:
                person["created_at"] = serialize_datetime(person["created_at"]) if person.get("created_at") else None
            for track in export_data["tracking"]:
                track["timestamp"] = serialize_datetime(track["timestamp"]) if track.get("timestamp") else None

            logger.info("Data export successful.")
            return jsonify(export_data)

        except Exception as e:
            logger.error(f"An error occurred during data export: {e}")
            return {"message": f"An error occurred during data export: {e}"}, 500