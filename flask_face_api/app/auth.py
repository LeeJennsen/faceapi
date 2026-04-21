from functools import wraps

from flask import g, request
from loguru import logger

from app.db.mysql import mysql_cursor
from app.services.jwt_service import verify_token


def get_bearer_token() -> str | None:
    auth_header = request.headers.get("Authorization", "").strip()
    if not auth_header:
        return None

    parts = auth_header.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1].strip() or None


def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = get_bearer_token()
        if not token:
            return {"message": "Missing Bearer token."}, 401

        user_id = verify_token(token)
        if not user_id:
            return {"message": "Invalid or expired token."}, 401

        g.current_user_id = str(user_id)
        return f(*args, **kwargs)

    return decorated


def admin_required(f):
    @wraps(f)
    @token_required
    def decorated(*args, **kwargs):
        try:
            with mysql_cursor(dictionary=True) as (_, cursor):
                cursor.execute(
                    "SELECT id, email, role FROM users WHERE id=%s",
                    (g.current_user_id,),
                )
                user = cursor.fetchone()
        except Exception:
            logger.exception("Admin authorization failed while loading current user.")
            return {"message": "Unable to authorize request."}, 500

        if not user:
            return {"message": "User not found."}, 404
        if user["role"] != "Admin":
            return {"message": "Admin privileges required."}, 403

        g.current_user_email = user["email"]
        g.current_user_role = user["role"]
        return f(*args, **kwargs)

    return decorated
