import bcrypt

def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()

def verify_password(pw: str, h: str) -> bool:
    return bcrypt.checkpw(pw.encode(), h.encode())

