import os
os.environ["TF_ENABLE_ONEDNN_OPTS"] = "0"

import base64
import json
import uuid
import paho.mqtt.client as mqtt
from datetime import datetime
import numpy as np
from face_utils import (
    base64_to_image,
    extract_aligned_face,
    compare_faces,
    image_to_base64,
    get_face_embedding
)
from db_utils import save_face_track, get_recent_embeddings
import time # ADDED THIS LINE

THRESHOLD = 0.8
TIME_WINDOW_MINUTES = 3
TOPIC = "face/images/incoming" # Assuming this engine also listens to incoming images

def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode('utf-8'))
        image_b64 = payload['image']
        camera_id = payload.get('camera_id')
        timestamp = datetime.fromisoformat(payload['timestamp'])
        filename = payload.get('filename', 'unknown_file') # Added filename for better logging

        print(f"[{filename}] Received image from camera {camera_id} at {timestamp}")

        image = base64_to_image(image_b64)
        face = extract_aligned_face(image)
        if isinstance(face, str):
            print(f"[{filename}] [!] Face not found: {face}")
            return

        embedding = get_face_embedding(face)
        if embedding is None:
            print(f"[{filename}] [!] No embedding found.")
            return

        stored = get_recent_embeddings(TIME_WINDOW_MINUTES)

        track_id = str(uuid.uuid4())      # Always new detection session
        unique_id = str(uuid.uuid4())     # Assume new person if no match found

        for row in stored:
            existing_emb = np.array(json.loads(row['embedding']))
            sim, match = compare_faces(embedding, existing_emb, threshold=THRESHOLD)
            if match:
                unique_id = row['unique_id']  # Reuse person ID
                print(f"[{filename}] [MATCH] Reusing unique_id {unique_id} (similarity: {sim:.2f})")
                break

        save_face_track(track_id, unique_id, image_b64, embedding, timestamp, camera_id, custom_track_key=None)
        print(f"[{filename}] [+] Stored detection: track_id={track_id}, unique_id={unique_id}")

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
        # This engine also needs MQTT connection to receive images, so exiting is appropriate.
        exit(1) # Exits the script if connection truly fails

    client.loop_start() # Start the MQTT loop in a separate thread
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
