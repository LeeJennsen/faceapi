import paho.mqtt.client as mqtt
from paho.mqtt.client import MQTT_ERR_SUCCESS 
import time
import random
import json
import os
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime, timedelta

# MQTT Broker
broker = "mqtt" # For testing use this public broker
port = 1883 # If want tls, use 8883 and need configuration
topic = "face/data/raw"

os.makedirs("counters", exist_ok=True)

# Set up logging
os.makedirs("logs", exist_ok=True)
log_file = "logs/pub.log"

logging.basicConfig(
    level = logging.INFO,
    handlers = [
        RotatingFileHandler(
            log_file, 
            maxBytes = 1_000_000,
            backupCount = 5,
            encoding = 'utf-8'),        
    ],
    format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

logger = logging.getLogger(__name__)

CONNACK_NAMES = {
    0: "Success",
    1: "Refused: Unacceptable Protocol",
    2: "Refused: Identifier Rejected",
    3: "Refused: Server Unavailable",
    4: "Refused: Bad Credentials",
    5: "Refused: Not Authorized"
}

# File for storing track id and face unique id counter
track_id_file = "counters/track-id-counter.txt"
face_unique_id_file = "counters/face-unique-id-counter.txt"

# Function to load track id
def load_id(file):
    try:
        if os.path.exists(file):
            with open(file, "r") as f:
                return int(f.read().strip())
    except (ValueError, IOError):
        logger.warning("Warning: Invalid content in %s. Starting from 1.", file)
    return 1

# Save track id 
def save_id(id, file):
    temp_file = f"{file}.tmp"
    try:
        with open(temp_file, "w") as f:
            f.write(str(id))
        os.replace(temp_file, file)  # Atomic on POSIX systems
    except IOError as e:
        logger.warning("Error saving ID to %s: %s", file, e, exc_info=True)

# Load track id counter
track_id_counter = load_id(track_id_file)
face_unique_id_counter = load_id(face_unique_id_file)

# Callback when connected to broker
def on_connect(client, userdata, flags, reasonCode, properties=None):
    status = CONNACK_NAMES.get(reasonCode.value, f"Unknown connection code: {reasonCode.value}")

    if reasonCode == MQTT_ERR_SUCCESS: 
        logger.info("Connected to broker: %s", status)
    else:
        logger.error("Connection failed, result code: %s", status)

def generate_face_data():
    global track_id_counter
    global face_unique_id_counter

    age_groups = ["<18", "18-24", "25-34", "35-44", "45-54", "55-64", "65+", "unknown"]
    cam_groups = ["cam001", "cam002", "cam003", "cam004"]
    emotion_groups = ["happy", "angry", "sad", "neutral"]
    location_groups = ["loc001", "loc002"]

    track_id_str = f"{track_id_counter:03d}"
    track_id_counter += 1
    save_id(track_id_counter, track_id_file) # Save track id after each increment

    face_unique_id_str = f"{face_unique_id_counter:03d}"
    face_unique_id_counter += 1
    save_id(face_unique_id_counter, face_unique_id_file) # Save face unique id after each increment

    start_time = datetime.utcnow()
    random_seconds = random.uniform(5.0, 25.0)
    end_time = start_time + timedelta(seconds=random_seconds)

    return {
        "device_id": "Jetson-Orin-NX01",
        "face_unique_id": face_unique_id_str,
        "start_timestamp": start_time.isoformat() + "Z",
        "end_timestamp": end_time.isoformat() + "Z",
        "camera_id": random.choice(cam_groups),
        "detections": [
            {
                "track_id": track_id_str,
                "object_type": "face",
                "bounding_box": {
                    "x": round(random.uniform(0, 1920),2),
                    "y": round(random.uniform(0, 1080),2),
                    "width": round(random.uniform(50, 300),2),
                    "height": round(random.uniform(50, 300),2),
                },
                "confidence": round(random.uniform(0.75, 0.99),2),
                "gender": random.choice(["male", "female", "unknown"]),
                "age": random.choice(age_groups),
                "emotion": random.choice(emotion_groups),
                "attention_time": round(random.uniform(0.1, 30.0),2),
                "length_of_stay": round(random.uniform(1.0, 120.0),2),
                "location": random.choice(location_groups),
                "frame_reference": 0, # For now put as 0
                "face_quality_score": round(random.uniform(0.75, 1.0), 2)
            }
        ]
    }

def main(): 
    # Create mqtt client
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = on_connect

    max_connect_retries = 15
    connected = False

    for attempt in range(max_connect_retries):
        try:
            logger.info("Attempting MQTT connection to %s:%d (attempt %d/%d)", broker, port, attempt + 1, max_connect_retries)
            client.connect(broker, port, 60)
            connected = True
            break
        except Exception as e:
            logger.warning("MQTT connection failed: %s", e, exc_info=True)
            if attempt < max_connect_retries - 1:
                retry_delay = (attempt + 1) * 2
                logger.info("Retrying in %d seconds...", retry_delay)
                time.sleep(retry_delay)

    if not connected:
        logger.error("Failed to connect after %d attempts", max_connect_retries)
        return

    try:
        client.loop_start()

        while True:
            face_data = generate_face_data()
            payload = json.dumps(face_data)

            try:
                result = client.publish(topic, payload)

                if result.rc == MQTT_ERR_SUCCESS:
                    logger.info("Published face data to %s, Face unique id: %s", topic, face_data['face_unique_id'])
                else:
                    logger.error("Publish failed: result code %d", result.rc)

            except Exception as e:
                logger.exception("Exception during publish")              
            
            time.sleep(random.uniform(30.0, 60.0)) # Time between face data generated

    except KeyboardInterrupt:
        logger.info("Stopping simulator")
        time.sleep(1) # In case MQTT still have one last message to send
        client.loop_stop()
        client.disconnect()
        save_id(track_id_counter, track_id_file) # Save the latest track id
        save_id(face_unique_id_counter, face_unique_id_file) # Save the latest face unique id

    except Exception as e:
        logger.error("Unexpected error: %s", e, exc_info=True)
        client.loop_stop()
        client.disconnect()

if __name__ == "__main__":
    main()
