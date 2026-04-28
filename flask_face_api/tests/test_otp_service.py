from contextlib import contextmanager
from datetime import datetime, timedelta
import app.services.otp_service as otp_service
from app.services.bcrypt_service import hash_password

def test_verify_otp_mysql_success(monkeypatch):
    # Mock the database record that would be returned
    otp_record = {
        "otp_code": hash_password("123456"),
        "expires_at": datetime.utcnow() + timedelta(minutes=10),
    }

    class FakeCursor:
        def execute(self, _query, _params):
            return None
        def fetchone(self):
            return otp_record

    class FakeConnection:
        def commit(self):
            return None

    @contextmanager
    def fake_mysql_cursor(*, dictionary=False):
        yield FakeConnection(), FakeCursor()

    # Override the real database connection with our fake one
    monkeypatch.setattr(otp_service, "mysql_cursor", fake_mysql_cursor)

    # Test that the service correctly verifies a good OTP
    assert otp_service.verify_otp("test@example.com", "123456") is True