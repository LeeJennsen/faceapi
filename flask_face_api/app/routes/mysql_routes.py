# app/routes/mysql_routes.py

from flask_restx import Namespace, Resource, fields, reqparse
from flask import request
from loguru import logger
from app.db.mysql import get_mysql_connection
from datetime import datetime
import traceback


mysql_ns = Namespace('faces-mysql', description='Face identity and tracking records (MySQL)')

# --- Schema definitions for Swagger UI ---
face_persons_model = mysql_ns.model("FacePerson", {
    "unique_id": fields.String(required=True),
    "images_json": fields.String(required=True),
    "embedding": fields.String(required=True),
    "label": fields.String(required=True),
})

face_tracking_model = mysql_ns.model("FaceTracking", {
    "track_id": fields.String(required=True),
    "unique_id": fields.String,
    "image_base64": fields.String(required=True),
    "embedding": fields.String(required=True),
    "timestamp": fields.String(required=True, description="Datetime in ISO format"),
    "camera_id": fields.String,
    "custom_track_key": fields.String,
})

full_record_model = mysql_ns.model("FullFaceRecord", {
    "person": fields.Nested(face_persons_model, required=True),
    "tracking": fields.Nested(face_tracking_model, required=True),
})


# --- FACE_PERSONS ENDPOINTS ---

@mysql_ns.route('/persons')
class FacePersonResource(Resource):
    @mysql_ns.doc(description="Get all face persons")
    def get(self):
        try:
            conn = get_mysql_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT id, unique_id, images_json, embedding, label, created_at FROM face_persons")
            rows = cursor.fetchall()

            # Convert datetime to string for JSON serialization
            for row in rows:
                if isinstance(row.get("created_at"), datetime):
                    row["created_at"] = row["created_at"].isoformat()

            cursor.close()
            conn.close()
            return {"data": rows}, 200
        except Exception as e:
            logger.error("MySQL GET error:\n" + traceback.format_exc())
            return {"message": "Internal Server Error"}, 500


    @mysql_ns.expect(face_persons_model)
    @mysql_ns.doc(description="Insert a new face person")
    def post(self):
        data = request.json
        try:
            conn = get_mysql_connection()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO face_persons (unique_id, images_json, embedding, label, created_at)
                VALUES (%s, %s, %s, %s, NOW())
            """, (
                data["unique_id"],
                data["images_json"],
                data["embedding"],
                data["label"]
            ))
            conn.commit()
            cursor.close()
            conn.close()
            return {"message": "Inserted successfully"}, 201
        except Exception as e:
            logger.error(e)
            return {"message": "Insert failed"}, 500

# --- FACE_TRACKING ENDPOINTS ---

@mysql_ns.route('/tracking')
class FaceTrackingResource(Resource):
    @mysql_ns.doc(description="Get all face tracking records")
    def get(self):
        try:
            logger.info("Starting GET /tracking")
            conn = get_mysql_connection()
            cursor = conn.cursor(dictionary=True)
            logger.info("MySQL connection and cursor established for tracking.")

            cursor.execute("""
                SELECT id, track_id, unique_id, image_base64, embedding,
                       timestamp, camera_id, custom_track_key
                FROM face_tracking
            """)
            rows = cursor.fetchall()

            for row in rows:
                if isinstance(row.get("embedding"), bytes):
                    row["embedding"] = row["embedding"].decode("utf-8")
                if isinstance(row.get("timestamp"), datetime):
                    row["timestamp"] = row["timestamp"].isoformat()

                logger.debug(f"Row: {row}")

            cursor.close()
            conn.close()
            logger.info("MySQL connection closed successfully.")
            return {"data": rows}, 200

        except Exception as e:
            logger.error("MySQL GET /tracking error:\n" + traceback.format_exc())
            return {"message": "Internal Server Error"}, 500
        

    @mysql_ns.expect(face_tracking_model)
    @mysql_ns.doc(description="Insert a new face tracking record")
    def post(self):
        data = request.json
        try:
            conn = get_mysql_connection()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO face_tracking (
                    track_id, unique_id, image_base64, embedding,
                    timestamp, camera_id, custom_track_key
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (
                data["track_id"],
                data.get("unique_id"),
                data["image_base64"],
                data["embedding"],
                data["timestamp"],
                data.get("camera_id"),
                data.get("custom_track_key")
            ))
            conn.commit()
            cursor.close()
            conn.close()
            return {"message": "Inserted successfully"}, 201
        except Exception as e:
            logger.error(e)
            return {"message": "Insert failed"}, 500


# --- FULL RECORD COMBINED ENDPOINTS ---
        
@mysql_ns.route('/full-record')
class FullFaceRecordResource(Resource):

    @mysql_ns.doc(description="Insert into face_persons and face_tracking in one call")
    @mysql_ns.expect(mysql_ns.model("FullRecord", {
        "person": fields.Nested(face_persons_model, required=True),
        "tracking": fields.Nested(face_tracking_model, required=True)
    }))
    def post(self):
        data = request.json
        person_data = data.get("person")
        tracking_data = data.get("tracking")

        try:
            conn = get_mysql_connection()
            cursor = conn.cursor()

            cursor.execute("""
                INSERT INTO face_persons (unique_id, images_json, embedding, label, created_at)
                VALUES (%s, %s, %s, %s, NOW())
            """, (
                person_data["unique_id"],
                person_data["images_json"],
                person_data["embedding"],
                person_data["label"]
            ))

            cursor.execute("""
                INSERT INTO face_tracking (track_id, unique_id, image_base64, embedding, timestamp, camera_id, custom_track_key)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (
                tracking_data["track_id"],
                tracking_data.get("unique_id"),
                tracking_data["image_base64"],
                tracking_data["embedding"],
                tracking_data["timestamp"],
                tracking_data.get("camera_id"),
                tracking_data.get("custom_track_key")
            ))

            conn.commit()
            cursor.close()
            conn.close()
            return {"message": "Both records inserted successfully"}, 201
        except Exception as e:
            logger.error("Full POST error: " + str(e))
            return {"message": "Insert failed"}, 500

    @mysql_ns.doc(description="Get joined face_persons and tracking records by unique_id")
    def get(self):
        try:
            conn = get_mysql_connection()
            cursor = conn.cursor(dictionary=True)

            cursor.execute("""
                SELECT 
                    p.id as person_id, p.unique_id, p.label, p.images_json, 
                    p.embedding as person_embedding, p.created_at,
                    t.id as tracking_id, t.track_id, t.image_base64, 
                    t.embedding as tracking_embedding, t.timestamp, 
                    t.camera_id, t.custom_track_key
                FROM face_persons p
                JOIN face_tracking t ON p.unique_id = t.unique_id
            """)

            rows = cursor.fetchall()

            # Convert datetime and bytes to string
            for row in rows:
                if isinstance(row.get("created_at"), datetime):
                    row["created_at"] = row["created_at"].isoformat()
                if isinstance(row.get("timestamp"), datetime):
                    row["timestamp"] = row["timestamp"].isoformat()
                if isinstance(row.get("tracking_embedding"), bytes):
                    row["tracking_embedding"] = row["tracking_embedding"].decode("utf-8", errors="ignore")

            conn.close()
            return {"data": rows}, 200
        except Exception as e:
            logger.error("Full GET error:\n" + traceback.format_exc())
            return {"message": "Internal Server Error"}, 500
