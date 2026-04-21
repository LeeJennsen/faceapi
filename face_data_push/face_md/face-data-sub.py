import paho.mqtt.client as mqtt
from paho.mqtt.client import MQTT_ERR_SUCCESS 
import os 
import json
import time
from datetime import datetime
import requests # For cloud api 
import logging
from logging.handlers import RotatingFileHandler

# Broker / API settings
broker = os.getenv("MQTT_HOST", "mqtt")
port = int(os.getenv("MQTT_PORT", "1883"))
topic = os.getenv("FACE_DATA_TOPIC", "face/data/raw")
api_base_url = os.getenv("FACE_API_BASE_URL", "http://api:5000").rstrip("/")

# Set up logging
os.makedirs("logs", exist_ok=True)
log_file = "logs/sub.log"

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

# Callback when connected to broker
def on_connect(client, userdata, flags, reasonCode, properties=None):
    status = CONNACK_NAMES.get(reasonCode.value, f"Unknown connection code: {reasonCode.value}")

    if reasonCode == MQTT_ERR_SUCCESS:
        client.subscribe(topic)
        logger.info("Subscribed to topic: %s", topic)
    else:
        logger.error("Connection failed, reason code: %s", status)

# Callback when receive message
def on_message(client, userdata, msg):
    # Decode received data
    received_data = json.loads(msg.payload.decode())
    logger.info("Face data received from %s, Face unique id: %s", msg.topic, received_data['face_unique_id'])
    logger.debug("Full data:\n%s", json.dumps(received_data, indent=2))

    # Attempt API forward with 3 retries 
    max_api_forward_retries = 3
    api_success = False

    for attempt in range(max_api_forward_retries):
        if forward_to_api(received_data):
            api_success = True
            break
        else:
            if attempt < max_api_forward_retries - 1:  # Don't sleep on last attempt
                retry_delay = (attempt + 1) * 2  # Exponential backoff (2, 4 sec)
                logger.warning("Attempt %d failed - retrying in %ds...", attempt + 1, retry_delay)
                time.sleep(retry_delay)

    # Forward to api
    if not api_success:
        logger.error("Failed to forward to API after 3 attempts")
    try:
        # Stored received data
        save_received_data(received_data)
    
    except Exception as e:
        logger.warning("Data failed to save locally: %s", e, exc_info=True)

# Store received data from the topic
def save_received_data(data, folder="data"):
    try:
        os.makedirs(folder, exist_ok=True)

        # Extract first detection's track_id
        track_id = data["detections"][0]["track_id"]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        filename = f"{track_id}_{timestamp}.json"
        filepath = os.path.join(folder, filename)
        
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)
            f.flush()
        
        logger.info("Saved received data to %s", filepath)
        return filepath
        
    except (KeyError, IndexError) as e:
        logger.error("Missing track_id in data: %s", e)
    except Exception as e:
        logger.exception("Unexpected error saving file")

# Function for forwarding face data to cloud API
def forward_to_api(data):
    try:
        url = f"{api_base_url}/api/v1/faces-mongo/"
        headers = {"Content-Type": "application/json"} # Specify that we're sending JSON
        response = requests.post(url, json=data)
        #headers = {"Authorization": f"Bearer {your_jwt_token}"} # Replace with real JWT credentials
        #response = requests.post(url, json=data, headers=headers)

        if response.status_code == 200:
            logger.info("Forwarded to API successfully")
            return True
        else:
            logger.error("API forward failed - Status: %d, Response: %s", response.status_code, response.text)
            return False
    except Exception as e:
        logger.exception("Exception during API forward")
        return False

def main():
    # Create mqtt client
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = on_connect
    client.on_message = on_message

    connected = False
    max_connect_retries = 15

    for attempt in range(max_connect_retries):
        try:
            logger.info("Attempting MQTT connection to %s:%d (attempt %d)...", broker, port, attempt + 1)
            client.connect(broker, port, 60)
            connected = True
            break
        except Exception as e:
            logger.warning("MQTT connection failed (attempt %d/%d) - %s", attempt + 1, max_connect_retries, e, exc_info=True)
            if attempt < max_connect_retries - 1:
                retry_delay = (attempt + 1) * 2
                logger.info("Retrying in %ds...", retry_delay)
                time.sleep(retry_delay)

    if not connected:
            logger.error("Failed to connect to MQTT broker after %d attempts", max_connect_retries)
            return

    try:
        client.loop_forever()

    except KeyboardInterrupt:
        logger.info("Disconnecting...")
        client.disconnect()

    except Exception as e:
        logger.error("Runtime error: %s", e, exc_info=True)

if __name__ == "__main__":
    main()
