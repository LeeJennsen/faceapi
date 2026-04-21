import json
import os
import uuid
from datetime import datetime

import cv2
import numpy as np
import paho.mqtt.client as mqtt

from db_utils import get_connection
from face_utils import extract_aligned_face, get_face_embedding, image_to_base64
from runtime import connect_mqtt, get_logger

IMAGES_DIR = "./images"
TOPIC = os.getenv("FACE_IMAGE_TOPIC", "face/images/incoming")
MQTT_HOST = os.getenv("MQTT_HOST", "mqtt")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))

LOGGER = get_logger(__name__, "logs/register-batch-faces.log")


def register_folder_person(folder_path, label, mqtt_client):
    face_images = []
    embeddings = []

    for filename in sorted(os.listdir(folder_path)):
        if not filename.lower().endswith((".jpg", ".jpeg", ".png")):
            continue

        image_path = os.path.join(folder_path, filename)
        image = cv2.imread(image_path)
        face = extract_aligned_face(image)
        if isinstance(face, str):
            LOGGER.warning("Skipping %s: %s", filename, face)
            continue

        embedding = get_face_embedding(face)
        if embedding is None:
            LOGGER.warning("Skipping %s: no embedding extracted", filename)
            continue

        embeddings.append(embedding)
        face_b64 = image_to_base64(face)
        face_images.append(face_b64)

        payload = {
            "image": face_b64,
            "timestamp": datetime.utcnow().isoformat(),
            "camera_id": filename,
            "filename": filename,
        }
        mqtt_client.publish(TOPIC, json.dumps(payload))
        LOGGER.info("Published registration preview image for %s", filename)

    if len(embeddings) < 5:
        LOGGER.warning("Skipped %s: only %d valid faces were available", label, len(embeddings))
        return

    avg_embedding = np.mean(embeddings, axis=0)
    unique_id = str(uuid.uuid4())
    created_at = datetime.utcnow()

    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO face_persons (unique_id, images_json, embedding, label, created_at)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                unique_id,
                json.dumps(face_images),
                json.dumps(avg_embedding.tolist()),
                label,
                created_at,
            ),
        )
        conn.commit()
        LOGGER.info("Saved registered face set for %s as %s", label, unique_id)
    except Exception as exc:
        LOGGER.error("Failed to insert face registration for %s: %s", label, exc)
    finally:
        if conn and conn.is_connected():
            conn.close()


def main():
    mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    if not connect_mqtt(mqtt_client, MQTT_HOST, MQTT_PORT, LOGGER):
        raise SystemExit(1)

    mqtt_client.loop_start()
    try:
        for person_folder in sorted(os.listdir(IMAGES_DIR)):
            folder_path = os.path.join(IMAGES_DIR, person_folder)
            if os.path.isdir(folder_path):
                register_folder_person(folder_path, label=person_folder, mqtt_client=mqtt_client)
    finally:
        mqtt_client.loop_stop()
        mqtt_client.disconnect()


if __name__ == "__main__":
    main()
