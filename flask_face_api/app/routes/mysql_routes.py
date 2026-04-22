import json
from datetime import datetime, timezone

from flask import request
from flask_restx import Namespace, Resource, fields
from loguru import logger

from app.db.mysql import mysql_cursor
from app.utils.serialization import (
    decode_json_field,
    ensure_image_data_uri,
    normalize_images_json,
    serialize_datetime,
)

mysql_ns = Namespace("faces-mysql", description="Face identity and tracking records (MySQL)")

face_persons_model = mysql_ns.model(
    "FacePerson",
    {
        "unique_id": fields.String(required=True),
        "images_json": fields.String(required=True),
        "embedding": fields.String(required=True),
        "label": fields.String(required=True),
    },
)

face_tracking_model = mysql_ns.model(
    "FaceTracking",
    {
        "track_id": fields.String(required=True),
        "unique_id": fields.String,
        "image_base64": fields.String(required=True),
        "embedding": fields.String(required=True),
        "timestamp": fields.String(required=True, description="Datetime in ISO format"),
        "camera_id": fields.String,
        "custom_track_key": fields.String,
    },
)

full_record_model = mysql_ns.model(
    "FullFaceRecord",
    {
        "person": fields.Nested(face_persons_model, required=True),
        "tracking": fields.Nested(face_tracking_model, required=True),
    },
)


def _request_json():
    return request.get_json(silent=True) or {}


def _normalize_embedding_for_db(value):
    if isinstance(value, str):
        return value
    if hasattr(value, "tolist"):
        return json.dumps(value.tolist())
    return json.dumps(value)


def _normalize_timestamp_for_db(value):
    if not isinstance(value, str):
        return value

    normalized = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return value

    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed.strftime("%Y-%m-%d %H:%M:%S")


def _serialize_person_row(row):
    serialized = dict(row)
    serialized["created_at"] = serialize_datetime(serialized.get("created_at"))
    serialized["embedding"] = decode_json_field(serialized.get("embedding"))
    serialized["images_json"] = normalize_images_json(serialized.get("images_json"))
    return serialized


def _serialize_tracking_row(row):
    serialized = dict(row)
    serialized["timestamp"] = serialize_datetime(serialized.get("timestamp"))
    serialized["embedding"] = decode_json_field(serialized.get("embedding"))
    serialized["image_base64"] = ensure_image_data_uri(serialized.get("image_base64"))
    return serialized


def _serialize_full_record_row(row):
    serialized = dict(row)
    serialized["created_at"] = serialize_datetime(serialized.get("created_at"))
    serialized["timestamp"] = serialize_datetime(serialized.get("timestamp"))
    serialized["person_embedding"] = decode_json_field(serialized.get("person_embedding"))
    serialized["tracking_embedding"] = decode_json_field(serialized.get("tracking_embedding"))
    serialized["image_base64"] = ensure_image_data_uri(serialized.get("image_base64"))
    serialized["images_json"] = normalize_images_json(serialized.get("images_json"))
    return serialized


@mysql_ns.route("/persons")
class FacePersonResource(Resource):
    @mysql_ns.doc(description="Get all face persons")
    def get(self):
        try:
            with mysql_cursor(dictionary=True) as (_, cursor):
                cursor.execute(
                    "SELECT id, unique_id, images_json, embedding, label, created_at FROM face_persons"
                )
                rows = [_serialize_person_row(row) for row in cursor.fetchall()]
            return {"data": rows}, 200
        except Exception:
            logger.exception("Failed to fetch face persons.")
            return {"message": "Internal Server Error"}, 500

    @mysql_ns.expect(face_persons_model)
    @mysql_ns.doc(description="Insert a new face person")
    def post(self):
        data = _request_json()
        try:
            with mysql_cursor() as (conn, cursor):
                cursor.execute(
                    """
                    INSERT INTO face_persons (unique_id, images_json, embedding, label, created_at)
                    VALUES (%s, %s, %s, %s, NOW())
                    """,
                    (
                        data["unique_id"],
                        data["images_json"],
                        data["embedding"],
                        data["label"],
                    ),
                )
                conn.commit()
            return {"message": "Inserted successfully"}, 201
        except Exception:
            logger.exception("Failed to insert face person.")
            return {"message": "Insert failed"}, 500


@mysql_ns.route("/tracking")
class FaceTrackingResource(Resource):
    @mysql_ns.doc(description="Get all face tracking records")
    def get(self):
        try:
            with mysql_cursor(dictionary=True) as (_, cursor):
                cursor.execute(
                    """
                    SELECT id, track_id, unique_id, image_base64, embedding,
                           timestamp, camera_id, custom_track_key
                    FROM face_tracking
                    """
                )
                rows = [_serialize_tracking_row(row) for row in cursor.fetchall()]
            return {"data": rows}, 200
        except Exception:
            logger.exception("Failed to fetch face tracking records.")
            return {"message": "Internal Server Error"}, 500

    @mysql_ns.expect(face_tracking_model)
    @mysql_ns.doc(description="Insert a new face tracking record")
    def post(self):
        data = _request_json()
        try:
            with mysql_cursor() as (conn, cursor):
                cursor.execute(
                    """
                    INSERT INTO face_tracking (
                        track_id, unique_id, image_base64, embedding,
                        timestamp, camera_id, custom_track_key
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        data["track_id"],
                        data.get("unique_id"),
                        data["image_base64"],
                        _normalize_embedding_for_db(data["embedding"]),
                        _normalize_timestamp_for_db(data["timestamp"]),
                        data.get("camera_id"),
                        data.get("custom_track_key"),
                    ),
                )
                conn.commit()
            return {"message": "Inserted successfully"}, 201
        except Exception:
            logger.exception("Failed to insert face tracking record.")
            return {"message": "Insert failed"}, 500


@mysql_ns.route("/full-record")
class FullFaceRecordResource(Resource):
    @mysql_ns.doc(description="Insert into face_persons and face_tracking in one call")
    @mysql_ns.expect(full_record_model)
    def post(self):
        data = _request_json()
        person_data = data.get("person") or {}
        tracking_data = data.get("tracking") or {}

        try:
            with mysql_cursor() as (conn, cursor):
                cursor.execute(
                    """
                    INSERT INTO face_persons (unique_id, images_json, embedding, label, created_at)
                    VALUES (%s, %s, %s, %s, NOW())
                    """,
                    (
                        person_data["unique_id"],
                        person_data["images_json"],
                        person_data["embedding"],
                        person_data["label"],
                    ),
                )

                cursor.execute(
                    """
                    INSERT INTO face_tracking (track_id, unique_id, image_base64, embedding, timestamp, camera_id, custom_track_key)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        tracking_data["track_id"],
                        tracking_data.get("unique_id"),
                        tracking_data["image_base64"],
                        _normalize_embedding_for_db(tracking_data["embedding"]),
                        _normalize_timestamp_for_db(tracking_data["timestamp"]),
                        tracking_data.get("camera_id"),
                        tracking_data.get("custom_track_key"),
                    ),
                )
                conn.commit()
            return {"message": "Both records inserted successfully"}, 201
        except Exception:
            logger.exception("Failed to insert combined face person and tracking record.")
            return {"message": "Insert failed"}, 500

    @mysql_ns.doc(description="Get joined face_persons and tracking records by unique_id")
    def get(self):
        try:
            with mysql_cursor(dictionary=True) as (_, cursor):
                cursor.execute(
                    """
                    SELECT 
                        p.id as person_id, p.unique_id, p.label, p.images_json, 
                        p.embedding as person_embedding, p.created_at,
                        t.id as tracking_id, t.track_id, t.image_base64, 
                        t.embedding as tracking_embedding, t.timestamp, 
                        t.camera_id, t.custom_track_key
                    FROM face_persons p
                    JOIN face_tracking t ON p.unique_id = t.unique_id
                    """
                )
                rows = [_serialize_full_record_row(row) for row in cursor.fetchall()]
            return {"data": rows}, 200
        except Exception:
            logger.exception("Failed to fetch joined face person and tracking records.")
            return {"message": "Internal Server Error"}, 500
