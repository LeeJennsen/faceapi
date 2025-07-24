import os
import json
import uuid
import cv2
import numpy as np
from datetime import datetime
from face_utils import base64_to_image, extract_aligned_face, get_face_embedding, image_to_base64
from db_utils import get_connection
import paho.mqtt.client as mqtt
import time # ADD THIS LINE FOR time.sleep

IMAGES_DIR = './images'
TOPIC = 'face/images/incoming'

# MQTT setup
mqtt_client = mqtt.Client()

# Add a retry loop for MQTT connection
mqtt_connected = False
max_retries = 10
retry_delay = 5 # seconds

for i in range(max_retries):
    try:
        print(f"[MQTT] Attempting to connect to MQTT broker from register_faces (attempt {i+1}/{max_retries})...")
        mqtt_client.connect("10.0.1.140", 1883, 60)
        mqtt_connected = True
        print("[MQTT] Successfully connected to MQTT broker from register_faces.")
        break
    except Exception as e:
        print(f"[MQTT ERROR] Connection failed for register_faces: {e}. Retrying in {retry_delay} seconds...")
        time.sleep(retry_delay)

if not mqtt_connected:
    print("[MQTT FATAL] Could not connect to MQTT broker from register_faces after multiple retries. Exiting.")
    # You might want to sys.exit(1) here if the script cannot proceed without MQTT
    # For now, it will just continue and likely fail later if it truly needs MQTT.
    # Given its primary role is DB registration, MQTT is secondary for this specific script's core function.

conn = None # Keep this line as is

# ... (rest of your existing code in register_batch_faces.py)

conn = None

def register_folder_person(folder_path, label):
    face_images = []
    embeddings = []

    for fname in sorted(os.listdir(folder_path)):
        if fname.lower().endswith(('.jpg', '.jpeg', '.png')):
            path = os.path.join(folder_path, fname)
            image = cv2.imread(path)
            face = extract_aligned_face(image)
            if isinstance(face, str):
                print(f"[!] Skipping {fname}: {face}")
                continue

            embedding = get_face_embedding(face)
            if embedding is not None:
                embeddings.append(embedding)
                face_b64 = image_to_base64(face)
                face_images.append(face_b64)

                payload = {
                    'image': face_b64,
                    'timestamp': datetime.utcnow().isoformat(),
                    'camera_id': fname,  # using filename directly
                    'filename': fname
                }
                mqtt_client.publish(TOPIC, json.dumps(payload))
                print(f"[MQTT] Pushed {fname} as camera_id={fname}")
            else:
                print(f"[!] No embedding for {fname}")

    if len(embeddings) < 5:
        print(f"[!] Skipped {label}: only {len(embeddings)} valid faces")
        return

    avg_embedding = np.mean(embeddings, axis=0)
    unique_id = str(uuid.uuid4())  # could be replaced with "person_XXX" format if needed
    created_at = datetime.utcnow()

    conn = None # <<< ADD THIS LINE
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO face_persons (unique_id, images_json, embedding, label, created_at)
            VALUES (%s, %s, %s, %s, %s)
        ''', (
            unique_id,
            json.dumps(face_images),
            json.dumps(avg_embedding.tolist()),
            label,
            created_at
        ))
        conn.commit()
        print(f"[DB] ✅ Saved {label} as {unique_id}")
    except Exception as e:
        print(f"[DB ERROR] Failed to insert {label}: {e}")
    finally:
        if conn and conn.is_connected():
            conn.close()

def main():
    for person_folder in sorted(os.listdir(IMAGES_DIR)):
        folder_path = os.path.join(IMAGES_DIR, person_folder)
        if os.path.isdir(folder_path):
            register_folder_person(folder_path, label=person_folder)

if __name__ == '__main__':
    main()

