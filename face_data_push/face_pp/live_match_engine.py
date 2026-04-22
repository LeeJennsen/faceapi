import json
import os
from datetime import datetime

import paho.mqtt.client as mqtt

from api_client import save_face_track_via_api
from db_utils import (
    fetch_registered_faces,
    get_next_track_id,
    get_next_unique_id,
    save_face_track,
)
from face_utils import base64_to_image, compare_faces, extract_aligned_face, get_face_embedding
from runtime import connect_mqtt, get_logger

THRESHOLD = 0.8
TOPIC = os.getenv("FACE_IMAGE_TOPIC", "face/images/incoming")
MQTT_HOST = os.getenv("MQTT_HOST", "mqtt")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))

LOGGER = get_logger(__name__, "logs/live-match-engine.log")


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

        known_faces = fetch_registered_faces()
        unique_id = None

        for person in known_faces:
            similarity, match = compare_faces(embedding, person["embedding"], threshold=THRESHOLD)
            LOGGER.info(
                "[%s] Compared with %s similarity=%.4f result=%s",
                filename,
                person["unique_id"][:6],
                similarity if similarity is not None else -1,
                "MATCH" if match else "no match",
            )
            if match:
                unique_id = person["unique_id"]
                LOGGER.info("[%s] Reusing unique_id %s", filename, unique_id)
                break

        if unique_id is None:
            unique_id = get_next_unique_id()
            LOGGER.info("[%s] Assigned new unique_id %s", filename, unique_id)

        track_id = get_next_track_id()
        custom_key = f"{camera_id}_{timestamp.strftime('%Y%m%d%H%M%S')}_{track_id}"
        if save_face_track_via_api(
            track_id,
            unique_id,
            image_b64,
            embedding,
            timestamp,
            camera_id,
            custom_key,
        ):
            LOGGER.info(
                "[%s] Stored detection via API track_id=%s unique_id=%s custom_key=%s",
                filename,
                track_id,
                unique_id,
                custom_key,
            )
        else:
            LOGGER.warning("[%s] API tracking write failed, falling back to direct MySQL insert.", filename)
            save_face_track(track_id, unique_id, image_b64, embedding, timestamp, camera_id, custom_key)
            LOGGER.info(
                "[%s] Stored detection via fallback track_id=%s unique_id=%s custom_key=%s",
                filename,
                track_id,
                unique_id,
                custom_key,
            )
    except Exception as exc:
        LOGGER.exception("Failed to process live match MQTT payload: %s", exc)


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
        LOGGER.info("Shutting down live match engine.")
    finally:
        client.disconnect()


if __name__ == "__main__":
    main()
