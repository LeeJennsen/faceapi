import mysql.connector
import json
from datetime import datetime
import os
from dotenv import load_dotenv
import numpy as np # ADDED THIS LINE FOR NP.ARRAY
import time
load_dotenv()


def get_connection():
    return mysql.connector.connect(
        host='10.0.1.140',
        port=3306,
        user='glueck',
        password='pass',  # replace with actual password
        database='face_auth'
    )

def ensure_db():
    conn = None # <<< ADD THIS LINE - Initialize conn to None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute('''
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
        )''')

        time.sleep(15) # Sleep 15 seconds - Keep this if it was there for a reason

        cursor.execute('''
        CREATE TABLE IF NOT EXISTS face_persons (
            id INT AUTO_INCREMENT PRIMARY KEY,
            unique_id VARCHAR(255) NOT NULL UNIQUE,
            images_json JSON,
            embedding BLOB NOT NULL,
            label VARCHAR(255),
            created_at DATETIME NOT NULL,
            INDEX (unique_id)
        )''')

        conn.commit()
    except Exception as e: # <<< ADD THIS block to catch and print errors
        print(f"[DB ERROR] ensure_db failed: {e}")
    finally:
        if conn and conn.is_connected():
            conn.close()


def save_face_track(track_id, unique_id, image_base64, embedding, timestamp, camera_id, custom_track_key):
    conn = None # <<< ADD THIS LINE - Initialize conn to None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # custom_track_key is now passed in
        cursor.execute('''
            INSERT INTO face_tracking (track_id, unique_id, image_base64, embedding, timestamp, camera_id, custom_track_key)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        ''', (
            track_id,
            unique_id,
            image_base64,
            json.dumps(embedding.tolist()),
            timestamp,
            camera_id,
            custom_track_key
        ))
        conn.commit()
    except Exception as e:
        print(f"[DB ERROR] Failed to insert track: {e}")
    finally:
        if conn and conn.is_connected():
            conn.close()


def get_recent_embeddings(time_window_minutes=3):
    conn = None # <<< ADD THIS LINE - Initialize conn to None
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute('''
            SELECT track_id, unique_id, embedding FROM face_tracking
            WHERE timestamp >= NOW() - INTERVAL %s MINUTE
        ''', (time_window_minutes,))
        rows = cursor.fetchall()
        for row in rows:
            # Ensure np is imported if not already. If not, the previous error in the trace may not be DB related.
            # Usually from: import numpy as np at the top of the file
            row['embedding'] = np.array(json.loads(row['embedding']))
        return rows
    except Exception as e:
        print(f"[DB ERROR] get_recent_embeddings: {e}")
        return []
    finally:
        if conn and conn.is_connected():
            conn.close()

# ADDED OR VERIFIED THIS FUNCTION
def fetch_registered_faces():
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT unique_id, embedding FROM face_persons")
        rows = cursor.fetchall()
        for row in rows:
            row['embedding'] = np.array(json.loads(row['embedding']))
        return rows
    except Exception as e:
        print(f"[DB ERROR] fetch_registered_faces: {e}")
        return []
    finally:
        if conn and conn.is_connected():
            conn.close()

# ADDED OR VERIFIED THIS FUNCTION
def get_next_track_id():
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT MAX(id) FROM face_tracking")
        last_id = cursor.fetchone()[0] or 0
        return str(last_id + 1).zfill(3)
    except Exception as e:
        print(f"[ERROR] Cannot get next track_id: {e}")
        return "999"
    finally:
        if conn and conn.is_connected():
            conn.close()

# ADDED OR VERIFIED THIS FUNCTION
def get_next_unique_id():
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT MAX(id) FROM face_persons")
        last_id = cursor.fetchone()[0] or 0
        return f"person_{str(last_id + 1).zfill(3)}"
    except Exception as e:
        print(f"[ERROR] Cannot get next unique_id: {e}")
        return "person_999"
    finally:
        if conn and conn.is_connected():
            conn.close()
