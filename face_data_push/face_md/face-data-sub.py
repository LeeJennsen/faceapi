import paho.mqtt.client as mqtt
from paho.mqtt.client import MQTT_ERR_SUCCESS 
import os 
import json
import time
from datetime import datetime
import requests # For cloud api 
import logging
from logging.handlers import RotatingFileHandler
from urllib.parse import urlsplit, urlunsplit

# Broker / API settings
broker = os.getenv("MQTT_HOST", "mqtt")
port = int(os.getenv("MQTT_PORT", "1883"))
topic = os.getenv("FACE_DATA_TOPIC", "face/data/raw")
api_base_url = os.getenv("FACE_API_BASE_URL", "http://host.docker.internal:5000").rstrip("/")
api_timeout_seconds = float(os.getenv("FACE_API_TIMEOUT_SECONDS", "10"))
default_api_base_urls = (
    "http://host.docker.internal:5000",
    "http://localhost:5000",
    "http://nginx:80",
    "http://api:5000",
)

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


def normalize_api_base_url(raw_url):
    value = (raw_url or "").strip()
    if not value:
        return None

    if "://" not in value:
        value = f"http://{value}"

    try:
        parsed = urlsplit(value)
    except ValueError:
        return None

    hostname = parsed.hostname
    if not hostname:
        return None

    port = parsed.port
    if port is None:
        if hostname in {"host.docker.internal", "localhost", "127.0.0.1"}:
            port = 5000
        elif hostname == "nginx":
            port = 80
        elif hostname == "api":
            port = 5000

    netloc = hostname if port is None else f"{hostname}:{port}"
    path = parsed.path.rstrip("/")
    return urlunsplit((parsed.scheme or "http", netloc, path, "", "")).rstrip("/")


def get_api_base_url_candidates():
    candidates = []
    seen = set()

    for raw_url in (api_base_url, *default_api_base_urls):
        normalized = normalize_api_base_url(raw_url)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        candidates.append(normalized)

    return candidates

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
    for base_url in get_api_base_url_candidates():
        url = f"{base_url}/api/v1/faces-mongo/"
        try:
            response = requests.post(url, json=data, timeout=api_timeout_seconds)
            if response.status_code == 200:
                logger.info("Forwarded to API successfully via %s", base_url)
                return True

            logger.warning(
                "API forward via %s failed - Status: %d, Response: %s",
                base_url,
                response.status_code,
                response.text,
            )
        except requests.RequestException as exc:
            logger.warning("API forward via %s failed: %s", base_url, exc)

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
