from contextlib import contextmanager
from datetime import datetime, timedelta

from app.services import otp_service
from app.services.bcrypt_service import hash_password


class FakeRedis:
    def __init__(self):
        self.store = {}

    def setex(self, key, _ttl, value):
        self.store[key] = value

    def get(self, key):
        return self.store.get(key)

    def delete(self, key):
        self.store.pop(key, None)


def test_generate_and_store_otp_uses_redis_when_available(monkeypatch):
    fake_redis = FakeRedis()

    monkeypatch.setattr(otp_service, "get_redis_client", lambda: fake_redis)
    monkeypatch.setattr(otp_service, "send_email", lambda email, otp: True)

    assert otp_service.generate_and_store_otp("redis@example.com") is True
    assert fake_redis.store


def test_verify_otp_prefers_redis_and_cleans_up(monkeypatch):
    fake_redis = FakeRedis()
    fake_redis.setex("faceapi2:otp:redis@example.com", 600, hash_password("654321"))

    monkeypatch.setattr(otp_service, "get_redis_client", lambda: fake_redis)

    assert otp_service.verify_otp("redis@example.com", "654321") is True
    assert "faceapi2:otp:redis@example.com" not in fake_redis.store


def test_verify_otp_falls_back_to_mysql(monkeypatch):
    otp_record = {
        "otp_code": hash_password("123456"),
        "expires_at": datetime.utcnow() + timedelta(minutes=10),
    }

    class FakeCursor:
        def execute(self, _query, _params):
            return None

        def fetchone(self):
            return otp_record

        def close(self):
            return None

    class FakeConnection:
        def commit(self):
            return None

        def close(self):
            return None

    @contextmanager
    def fake_mysql_cursor(*, dictionary=False):
        assert dictionary is True
        yield FakeConnection(), FakeCursor()

    monkeypatch.setattr(otp_service, "get_redis_client", lambda: None)
    monkeypatch.setattr(otp_service, "mysql_cursor", fake_mysql_cursor)

    assert otp_service.verify_otp("mysql@example.com", "123456") is True
