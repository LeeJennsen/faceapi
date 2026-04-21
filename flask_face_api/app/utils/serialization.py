import json
from datetime import date, datetime


def serialize_datetime(value):
    if value is None:
        return None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def decode_json_field(value):
    if isinstance(value, (bytes, bytearray)):
        value = value.decode("utf-8", errors="ignore")
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def ensure_image_data_uri(value):
    if isinstance(value, (bytes, bytearray)):
        value = value.decode("utf-8", errors="ignore")
    if isinstance(value, str) and value and not value.startswith("data:image"):
        return f"data:image/jpeg;base64,{value}"
    return value


def normalize_images_json(value):
    parsed = decode_json_field(value)
    if isinstance(parsed, list):
        return [ensure_image_data_uri(item) for item in parsed]
    return parsed
