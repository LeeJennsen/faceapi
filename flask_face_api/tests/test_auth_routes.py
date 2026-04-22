from contextlib import contextmanager
from datetime import datetime

import app.auth as auth_module
from app.routes import auth_routes


def _fake_mysql_cursor(actor, all_rows):
    @contextmanager
    def fake_mysql_cursor(*, dictionary=False):
        class FakeCursor:
            def __init__(self):
                self._result = None

            def execute(self, query, params=()):
                normalized_query = " ".join(query.split())
                if "WHERE id=%s" in normalized_query:
                    self._result = dict(actor)
                else:
                    self._result = [dict(row) for row in all_rows]

            def fetchone(self):
                if self._result is None:
                    return None
                return dict(self._result)

            def fetchall(self):
                return [dict(row) for row in (self._result or [])]

            def close(self):
                return None

        class FakeConnection:
            def close(self):
                return None

        yield FakeConnection(), FakeCursor()

    return fake_mysql_cursor


def test_users_all_returns_self_for_viewer(client, monkeypatch):
    actor = {
        "id": 7,
        "name": "Viewer User",
        "email": "viewer@example.com",
        "role": "Viewer",
        "last_login": None,
        "created_at": datetime(2026, 4, 23, 1, 2, 3),
    }

    monkeypatch.setattr(auth_module, "verify_token", lambda _token: str(actor["id"]))
    monkeypatch.setattr(auth_routes, "mysql_cursor", _fake_mysql_cursor(actor, []))

    response = client.get(
        "/api/v1/users/all",
        headers={"Authorization": "Bearer viewer-token"},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert len(payload["users"]) == 1
    assert payload["users"][0]["email"] == actor["email"]
    assert payload["users"][0]["role"] == "Viewer"


def test_users_all_returns_full_list_for_admin(client, monkeypatch):
    actor = {
        "id": 1,
        "name": "Admin User",
        "email": "admin@example.com",
        "role": "Admin",
        "last_login": None,
        "created_at": datetime(2026, 4, 23, 1, 2, 3),
    }
    all_rows = [
        actor,
        {
            "id": 2,
            "name": "Viewer User",
            "email": "viewer@example.com",
            "role": "Viewer",
            "last_login": None,
            "created_at": datetime(2026, 4, 23, 2, 3, 4),
        },
    ]

    monkeypatch.setattr(auth_module, "verify_token", lambda _token: str(actor["id"]))
    monkeypatch.setattr(auth_routes, "mysql_cursor", _fake_mysql_cursor(actor, all_rows))

    response = client.get(
        "/api/v1/users/all",
        headers={"Authorization": "Bearer admin-token"},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert len(payload["users"]) == 2
    assert {user["email"] for user in payload["users"]} == {"admin@example.com", "viewer@example.com"}


def test_refresh_returns_new_access_token_for_valid_refresh_token(client, monkeypatch):
    actor = {
        "id": 7,
        "name": "Viewer User",
        "email": "viewer@example.com",
        "role": "Viewer",
    }

    @contextmanager
    def fake_mysql_cursor(*, dictionary=False):
        class FakeCursor:
            def execute(self, query, params=()):
                return None

            def fetchone(self):
                return dict(actor)

            def close(self):
                return None

        class FakeConnection:
            def close(self):
                return None

        yield FakeConnection(), FakeCursor()

    monkeypatch.setattr(auth_routes, "verify_token", lambda token, expected_type="access": str(actor["id"]))
    monkeypatch.setattr(auth_routes, "generate_access_token", lambda user_id: f"access-for-{user_id}")
    monkeypatch.setattr(auth_routes, "mysql_cursor", fake_mysql_cursor)

    response = client.post("/api/v1/users/refresh", json={"refresh_token": "valid-refresh-token"})

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["access_token"] == "access-for-7"
    assert payload["user"]["email"] == actor["email"]
    assert payload["user"]["role"] == actor["role"]


def test_refresh_rejects_invalid_refresh_token(client, monkeypatch):
    monkeypatch.setattr(auth_routes, "verify_token", lambda token, expected_type="access": None)

    response = client.post("/api/v1/users/refresh", json={"refresh_token": "expired-refresh-token"})

    assert response.status_code == 401
    assert response.get_json()["message"] == "Invalid or expired refresh token."
