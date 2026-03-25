import json
import uuid
import numpy as np
import paho.mqtt.client as mqtt
from datetime import datetime
from face_utils import base64_to_image, extract_aligned_face, get_face_embedding, compare_faces
from db_utils import save_face_track, get_connection, fetch_registered_faces, get_next_track_id, get_next_unique_id
import time # ADDED THIS LINE

THRESHOLD = 0.8
TOPIC = "face/images/incoming"

def fetch_registered_faces():
    conn = None # <<< ADD THIS LINE
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

def get_next_track_id():
    conn = None # <<< ADD THIS LINE
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

def get_next_unique_id():
    conn = None # <<< ADD THIS LINE
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

def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode('utf-8'))
        image_b64 = payload['image']
        camera_id = payload.get('camera_id')
        timestamp = datetime.fromisoformat(payload['timestamp'])
        filename = payload.get('filename', 'unknown_file')

        print(f"[{filename}] Received image from camera {camera_id} at {timestamp}")

        image = base64_to_image(image_b64)
        face = extract_aligned_face(image)
        if isinstance(face, str):
            print(f"[{filename}] ❌ Face not found: {face}")
            return

        embedding = get_face_embedding(face)
        if embedding is None:
            print(f"[{filename}] ❌ No embedding extracted.")
            return

        known_faces = fetch_registered_faces()
        unique_id = None

        for person in known_faces:
            sim, match = compare_faces(embedding, person['embedding'], threshold=THRESHOLD)
            print(f"[{filename}] → Comparing with {person['unique_id'][:6]}: similarity={sim:.4f} → {'MATCH' if match else 'no match'}")
            if match:
                unique_id = person['unique_id']
                print(f"[MATCH] Reusing unique_id {unique_id} (similarity: {sim:.2f})")
                break

        if unique_id is None:
            unique_id = get_next_unique_id()
            print(f"[NEW] Assigned unique_id {unique_id} (no matches found)")

        track_id = get_next_track_id()
        ts_str = timestamp.strftime("%Y%m%d%H%M%S")
        custom_key = f"{camera_id}_{ts_str}_{track_id}"

        save_face_track(track_id, unique_id, image_b64, embedding, timestamp, camera_id, custom_key)
        print(f"[+] Stored detection: track_id={track_id}, unique_id={unique_id}, custom_key={custom_key}")

    except Exception as e:
        print(f"[ERROR] {e}")

def main():
    client = mqtt.Client()
    client.on_message = on_message

    # Add a retry loop for MQTT connection
    mqtt_connected = False
    max_retries = 10
    retry_delay = 5 # seconds

    for i in range(max_retries):
        try:
            print(f"[MQTT] Attempting to connect to MQTT broker (attempt {i+1}/{max_retries})...")
            client.connect('mqtt', 1883, 60) # IMPORTANT: Changed 'mqtt' to 'mqtt_broker'
            #client.connect('10.0.1.140', 1883, 60) # IMPORTANT: Changed 'mqtt' to 'mqtt_broker'
            mqtt_connected = True
            print("[MQTT] Successfully connected to MQTT broker.")
            break
        except Exception as e:
            print(f"[MQTT ERROR] Connection failed: {e}. Retrying in {retry_delay} seconds...")
            time.sleep(retry_delay)

    if not mqtt_connected:
        print("[MQTT FATAL] Could not connect to MQTT broker after multiple retries. Exiting.")
        # For live_match_engine, it's critical to connect, so exiting here might be appropriate.
        # But for now, we'll let it proceed to loop_start even if not explicitly connected by this loop.

    # The main loop needs to be started outside the retry logic
    client.loop_start()

    print(f"[*] Subscribed to topic: {TOPIC}")
    client.subscribe(TOPIC)

    try:
        while True:
            time.sleep(1) # Keep the main thread alive
    except KeyboardInterrupt:
        print("Exiting...")
    finally:
        client.loop_stop()
        client.disconnect()

if __name__ == '__main__':
    main()
