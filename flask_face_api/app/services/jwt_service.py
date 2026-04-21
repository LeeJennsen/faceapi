from datetime import datetime, timedelta, timezone

import jwt
from loguru import logger

from app.config import Config


def generate_tokens(user_id: int):
    now = datetime.now(timezone.utc)
    access_token = jwt.encode(
        {
            "sub": str(user_id),
            "type": "access",
            "exp": now + timedelta(seconds=Config.JWT_EXPIRY_SECONDS),
        },
        Config.JWT_SECRET_KEY,
        algorithm="HS256",
    )

    refresh_token = jwt.encode(
        {
            "sub": str(user_id),
            "type": "refresh",
            "exp": now + timedelta(seconds=Config.JWT_REFRESH_EXPIRY_SECONDS),
        },
        Config.JWT_SECRET_KEY,
        algorithm="HS256",
    )

    return access_token, refresh_token


def verify_token(token: str):
    try:
        if not token:
            logger.warning("Token verification attempted without a token.")
            return None

        payload = jwt.decode(token, Config.JWT_SECRET_KEY, algorithms=["HS256"])
        return payload["sub"]
    except jwt.ExpiredSignatureError:
        logger.info("Token verification failed: token expired.")
        return None
    except jwt.InvalidTokenError as exc:
        logger.warning("Token verification failed: {}", exc)
        return None
