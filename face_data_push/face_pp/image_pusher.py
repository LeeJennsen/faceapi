import os
import time
import base64
import paho.mqtt.client as mqtt
from datetime import datetime
import json

MQTT_BROKER = '10.0.1.140'
MQTT_PORT = 1883
TOPIC = 'face/images/incoming'

def encode_image_to_base64(filepath):
    with open(filepath, 'rb') as f:
        return base64.b64encode(f.read()).decode('utf-8')

def push_images():
    client = mqtt.Client()
    client.connect(MQTT_BROKER, MQTT_PORT, 60)
    image_dir = './images'

    for filename in os.listdir(image_dir):
        if filename.lower().endswith(('.png', '.jpg', '.jpeg')):
            path = os.path.join(image_dir, filename)
            encoded = encode_image_to_base64(path)

            camera_id = filename  # Use filename as camera_id

            message = {
                'image': encoded,
                'timestamp': datetime.utcnow().isoformat(),
                'camera_id': camera_id,
                'filename': filename
            }

            client.publish(TOPIC, json.dumps(message))
            print(f"[+] Pushed {filename} from {camera_id}")
            time.sleep(1)

    client.disconnect()

if __name__ == '__main__':
    push_images()

