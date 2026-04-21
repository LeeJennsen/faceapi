from flask import jsonify
from flask_restx import Namespace, Resource
from loguru import logger

from app.auth import admin_required
from app.db.mongo import get_face_collection
from app.db.mysql import mysql_cursor
from app.utils.serialization import (
    decode_json_field,
    ensure_image_data_uri,
    normalize_images_json,
    serialize_datetime,
)

api = Namespace("data", description="Data export operations")


@api.route("/export")
class ExportData(Resource):
    @api.doc(description="Export all major data from the database as a single JSON file. Admin only.")
    @admin_required
    def get(self):
        try:
            with mysql_cursor(dictionary=True) as (_, cursor):
                cursor.execute("SELECT id, name, email, role, last_login, created_at FROM users")
                users = cursor.fetchall()
                cursor.execute("SELECT * FROM face_persons")
                persons = cursor.fetchall()
                cursor.execute("SELECT * FROM face_tracking")
                tracking = cursor.fetchall()

            mongo_data = list(get_face_collection().find({}, {"_id": 0}).limit(500))

            for user in users:
                user["last_login"] = serialize_datetime(user.get("last_login"))
                user["created_at"] = serialize_datetime(user.get("created_at"))

            for person in persons:
                person["created_at"] = serialize_datetime(person.get("created_at"))
                person["embedding"] = decode_json_field(person.get("embedding"))
                person["images_json"] = normalize_images_json(person.get("images_json"))

            for track in tracking:
                track["timestamp"] = serialize_datetime(track.get("timestamp"))
                track["embedding"] = decode_json_field(track.get("embedding"))
                track["image_base64"] = ensure_image_data_uri(track.get("image_base64"))

            export_data = {
                "users": users,
                "persons": persons,
                "tracking": tracking,
                "mongo_detections_sample": mongo_data,
            }
            logger.info("Admin export completed successfully.")
            return jsonify(export_data)
        except Exception:
            logger.exception("An error occurred during data export.")
            return {"message": "An error occurred during data export."}, 500
