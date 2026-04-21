import json
import os
import time
import uuid
from datetime import datetime

import paho.mqtt.client as mqtt

from db_utils import get_recent_embeddings, save_face_track
from face_utils import base64_to_image, compare_faces, extract_aligned_face, get_face_embedding
from runtime import connect_mqtt, get_logger

THRESHOLD = 0.8
TIME_WINDOW_MINUTES = 3
TOPIC = os.getenv("FACE_IMAGE_TOPIC", "face/images/incoming")
MQTT_HOST = os.getenv("MQTT_HOST", "mqtt")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))

LOGGER = get_logger(__name__, "logs/face-recognition-engine.log")


def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode("utf-8"))
        image_b64 = payload["image"]
        camera_id = payload.get("camera_id")
        timestamp = datetime.fromisoformat(payload["timestamp"].replace("Z", "+00:00"))
        filename = payload.get("filename", "unknown_file")

        LOGGER.info("[%s] Received image from camera %s at %s", filename, camera_id, timestamp.isoformat())

        image = base64_to_image(image_b64)
        face = extract_aligned_face(image)
        if isinstance(face, str):
            LOGGER.warning("[%s] Face not found: %s", filename, face)
            return

        embedding = get_face_embedding(face)
        if embedding is None:
            LOGGER.warning("[%s] No embedding extracted.", filename)
            return

        stored_embeddings = get_recent_embeddings(TIME_WINDOW_MINUTES)
        track_id = str(uuid.uuid4())
        unique_id = str(uuid.uuid4())

        for row in stored_embeddings:
            similarity, match = compare_faces(embedding, row["embedding"], threshold=THRESHOLD)
            if match:
                unique_id = row["unique_id"]
                LOGGER.info("[%s] Reusing unique_id %s (similarity %.2f)", filename, unique_id, similarity)
                break

        save_face_track(track_id, unique_id, image_b64, embedding, timestamp, camera_id, custom_track_key=None)
        LOGGER.info("[%s] Stored detection track_id=%s unique_id=%s", filename, track_id, unique_id)
    except Exception as exc:
        LOGGER.exception("Failed to process MQTT face payload: %s", exc)


def main():
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_message = on_message

    if not connect_mqtt(client, MQTT_HOST, MQTT_PORT, LOGGER):
        raise SystemExit(1)

    client.subscribe(TOPIC)
    LOGGER.info("Subscribed to topic %s", TOPIC)

    try:
        client.loop_forever()
    except KeyboardInterrupt:
        LOGGER.info("Shutting down face recognition engine.")
    finally:
        client.disconnect()


if __name__ == "__main__":
    main()
