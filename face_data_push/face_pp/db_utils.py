import json
import os

import mysql.connector
import numpy as np

from runtime import get_logger

LOGGER = get_logger(__name__, "logs/face-pp-db.log")


def get_connection():
    return mysql.connector.connect(
        host=os.getenv("MYSQL_HOST", "mysql"),
        port=int(os.getenv("MYSQL_PORT", "3306")),
        user=os.getenv("MYSQL_USER", "faceuser"),
        password=os.getenv("MYSQL_PASSWORD"),
        database=os.getenv("MYSQL_DATABASE", "face_auth"),
    )


def ensure_db():
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS face_tracking (
                id INT AUTO_INCREMENT PRIMARY KEY,
                track_id VARCHAR(255) NOT NULL,
                unique_id VARCHAR(255) NOT NULL,
                image_base64 LONGTEXT NOT NULL,
                embedding BLOB NOT NULL,
                timestamp DATETIME NOT NULL,
                camera_id VARCHAR(255),
                custom_track_key VARCHAR(255),
                INDEX (track_id),
                INDEX (timestamp)
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS face_persons (
                id INT AUTO_INCREMENT PRIMARY KEY,
                unique_id VARCHAR(255) NOT NULL UNIQUE,
                images_json JSON,
                embedding BLOB NOT NULL,
                label VARCHAR(255),
                created_at DATETIME NOT NULL,
                INDEX (unique_id)
            )
            """
        )

        conn.commit()
    except Exception as exc:
        LOGGER.error("Failed to ensure database schema: %s", exc)
    finally:
        if conn and conn.is_connected():
            conn.close()


def save_face_track(track_id, unique_id, image_base64, embedding, timestamp, camera_id, custom_track_key):
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO face_tracking (track_id, unique_id, image_base64, embedding, timestamp, camera_id, custom_track_key)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                track_id,
                unique_id,
                image_base64,
                json.dumps(np.asarray(embedding).tolist()),
                timestamp,
                camera_id,
                custom_track_key,
            ),
        )
        conn.commit()
    except Exception as exc:
        LOGGER.error("Failed to save face track %s: %s", track_id, exc)
    finally:
        if conn and conn.is_connected():
            conn.close()


def get_recent_embeddings(time_window_minutes=3):
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT track_id, unique_id, embedding FROM face_tracking
            WHERE timestamp >= NOW() - INTERVAL %s MINUTE
            """,
            (time_window_minutes,),
        )
        rows = cursor.fetchall()
        for row in rows:
            row["embedding"] = np.array(json.loads(row["embedding"]))
        return rows
    except Exception as exc:
        LOGGER.error("Failed to fetch recent embeddings: %s", exc)
        return []
    finally:
        if conn and conn.is_connected():
            conn.close()


def fetch_registered_faces():
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT unique_id, embedding FROM face_persons")
        rows = cursor.fetchall()
        for row in rows:
            row["embedding"] = np.array(json.loads(row["embedding"]))
        return rows
    except Exception as exc:
        LOGGER.error("Failed to fetch registered faces: %s", exc)
        return []
    finally:
        if conn and conn.is_connected():
            conn.close()


def get_next_track_id():
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT MAX(id) FROM face_tracking")
        last_id = cursor.fetchone()[0] or 0
        return str(last_id + 1).zfill(3)
    except Exception as exc:
        LOGGER.error("Failed to determine next track_id: %s", exc)
        return "999"
    finally:
        if conn and conn.is_connected():
            conn.close()


def get_next_unique_id():
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT MAX(id) FROM face_persons")
        last_id = cursor.fetchone()[0] or 0
        return f"person_{str(last_id + 1).zfill(3)}"
    except Exception as exc:
        LOGGER.error("Failed to determine next unique_id: %s", exc)
        return "person_999"
    finally:
        if conn and conn.is_connected():
            conn.close()
