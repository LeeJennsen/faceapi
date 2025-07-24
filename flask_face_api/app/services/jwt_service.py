import jwt, datetime
from app.config import Config

def generate_tokens(user_id: int):
    at = jwt.encode({
        'sub': str(user_id),
        'exp': datetime.datetime.utcnow() + datetime.timedelta(seconds=Config.JWT_EXPIRY_SECONDS)
    }, Config.JWT_SECRET_KEY, algorithm='HS256')

    rt = jwt.encode({
        'sub': str(user_id),
        'exp': datetime.datetime.utcnow() + datetime.timedelta(seconds=Config.JWT_REFRESH_EXPIRY_SECONDS)
    }, Config.JWT_SECRET_KEY, algorithm='HS256')

    return at, rt


def verify_token(token: str):
    try:
        if not token:
            print("No token provided")
            return None
        print("🔐 Using secret key to verify:", Config.JWT_SECRET_KEY)
        payload = jwt.decode(token, Config.JWT_SECRET_KEY, algorithms=['HS256'])
        print("✅ Token verified:", payload)
        return payload['sub']
    except jwt.ExpiredSignatureError:
        print("❌ Token expired")
        return None
    except jwt.InvalidTokenError as e:
        print("❌ Invalid token:", e)
        return None


