import json
import os
from datetime import datetime
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen

from runtime import get_logger

FACE_API_BASE_URL = os.getenv("FACE_API_BASE_URL", "http://host.docker.internal:5000").rstrip("/")
FACE_API_TIMEOUT_SECONDS = float(os.getenv("FACE_API_TIMEOUT_SECONDS", "10"))
DEFAULT_API_BASE_URLS = (
    "http://host.docker.internal:5000",
    "http://localhost:5000",
    "http://nginx:80",
    "http://api:5000",
)

LOGGER = get_logger(__name__, "logs/face-api-client.log")


def _normalize_api_base_url(raw_url):
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


def _api_base_url_candidates():
    candidates = []
    seen = set()

    for raw_url in (FACE_API_BASE_URL, *DEFAULT_API_BASE_URLS):
        normalized = _normalize_api_base_url(raw_url)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        candidates.append(normalized)

    return candidates


def _serialize_embedding(embedding):
    if isinstance(embedding, str):
        return embedding
    if hasattr(embedding, "tolist"):
        return json.dumps(embedding.tolist())
    return json.dumps(embedding)


def _serialize_timestamp(timestamp):
    if isinstance(timestamp, datetime):
        return timestamp.isoformat()
    return str(timestamp)


def post_json(path: str, payload: dict) -> bool:
    body = json.dumps(payload).encode("utf-8")

    for base_url in _api_base_url_candidates():
        url = f"{base_url}{path}"
        request = Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urlopen(request, timeout=FACE_API_TIMEOUT_SECONDS) as response:
                status_code = getattr(response, "status", response.getcode())
                if 200 <= status_code < 300:
                    LOGGER.info("API request to %s succeeded", url)
                    return True

                response_body = response.read().decode("utf-8", errors="replace")
                LOGGER.warning("API request to %s returned %s: %s", url, status_code, response_body)
        except HTTPError as exc:
            response_body = exc.read().decode("utf-8", errors="replace")
            LOGGER.warning("API request to %s failed with %s: %s", url, exc.code, response_body)
        except URLError as exc:
            LOGGER.warning("API request to %s failed: %s", url, exc)
        except Exception as exc:
            LOGGER.warning("Unexpected API request failure for %s: %s", url, exc)

    return False


def save_face_track_via_api(
    track_id,
    unique_id,
    image_base64,
    embedding,
    timestamp,
    camera_id=None,
    custom_track_key=None,
) -> bool:
    payload = {
        "track_id": str(track_id),
        "unique_id": str(unique_id),
        "image_base64": image_base64,
        "embedding": _serialize_embedding(embedding),
        "timestamp": _serialize_timestamp(timestamp),
        "camera_id": camera_id,
        "custom_track_key": custom_track_key,
    }
    return post_json("/api/v1/faces-mysql/tracking", payload)
