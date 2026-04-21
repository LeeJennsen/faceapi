import base64
import json
import os
import time
from datetime import datetime

import paho.mqtt.client as mqtt

from runtime import connect_mqtt, get_logger

MQTT_BROKER = os.getenv("MQTT_HOST", "mqtt")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
TOPIC = os.getenv("FACE_IMAGE_TOPIC", "face/images/incoming")

LOGGER = get_logger(__name__, "logs/image-pusher.log")


def encode_image_to_base64(filepath):
    with open(filepath, "rb") as file_handle:
        return base64.b64encode(file_handle.read()).decode("utf-8")


def push_images():
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    if not connect_mqtt(client, MQTT_BROKER, MQTT_PORT, LOGGER):
        raise SystemExit(1)

    image_dir = "./images"
    client.loop_start()
    try:
        for filename in sorted(os.listdir(image_dir)):
            if not filename.lower().endswith((".png", ".jpg", ".jpeg")):
                continue

            path = os.path.join(image_dir, filename)
            message = {
                "image": encode_image_to_base64(path),
                "timestamp": datetime.utcnow().isoformat(),
                "camera_id": filename,
                "filename": filename,
            }

            client.publish(TOPIC, json.dumps(message))
            LOGGER.info("Published image %s", filename)
            time.sleep(1)
    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    push_images()
