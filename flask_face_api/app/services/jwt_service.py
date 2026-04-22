from datetime import datetime, timedelta, timezone

import jwt
from loguru import logger

from app.config import Config


def _encode_token(user_id: int, token_type: str, expiry_seconds: int):
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {"sub": str(user_id), "type": token_type, "exp": now + timedelta(seconds=expiry_seconds)},
        Config.JWT_SECRET_KEY,
        algorithm="HS256",
    )


def generate_access_token(user_id: int):
    return _encode_token(user_id, "access", Config.JWT_EXPIRY_SECONDS)


def generate_refresh_token(user_id: int):
    return _encode_token(user_id, "refresh", Config.JWT_REFRESH_EXPIRY_SECONDS)


def generate_tokens(user_id: int):
    return generate_access_token(user_id), generate_refresh_token(user_id)


def verify_token(token: str, expected_type: str = "access"):
    try:
        if not token:
            logger.warning("Token verification attempted without a token.")
            return None

        payload = jwt.decode(token, Config.JWT_SECRET_KEY, algorithms=["HS256"])
        token_type = payload.get("type")
        if expected_type and token_type != expected_type:
            logger.warning("Token verification failed: expected {} token but received {}.", expected_type, token_type)
            return None
        return payload["sub"]
    except jwt.ExpiredSignatureError:
        logger.info("Token verification failed: token expired.")
        return None
    except jwt.InvalidTokenError as exc:
        logger.warning("Token verification failed: {}", exc)
        return None
