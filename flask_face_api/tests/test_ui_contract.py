import re
from pathlib import Path

import pytest


TEMPLATE_ROOT = Path(__file__).resolve().parents[1] / "templates" / "v1"


def _read_template(name: str) -> str:
    return (TEMPLATE_ROOT / name).read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("route", "expected_snippets"),
    [
        ("/v1/login", ["Trusted access for the FaceAPI2 control center.", "Sign In to Dashboard", "auth-shell.css"]),
        ("/v1/register", ["Create your operator profile", "Create Account", "auth-shell.js"]),
        ("/v1/forgot_password", ["Reset your password", "Send Recovery Code", "auth-shell.css"]),
    ],
)
def test_auth_pages_render_enterprise_shell(client, route, expected_snippets):
    response = client.get(route)

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    for snippet in expected_snippets:
        assert snippet in html

    for mojibake_token in ("\u00c2\u00b7", "\u00e2\u20ac\u2122", "\u00f0\u0178"):
        assert mojibake_token not in html


def test_dashboard_template_keeps_dom_targets_for_id_lookups():
    source = _read_template("dashboard.html")

    looked_up_ids = set(re.findall(r"getElementById\(\s*['\"]([^'\"]+)['\"]\s*\)", source))
    declared_ids = set(re.findall(r"id\s*=\s*['\"]([^'\"]+)['\"]", source))

    missing_ids = sorted(looked_up_ids - declared_ids)
    assert not missing_ids, f"Dashboard JS references missing ids: {missing_ids}"


def test_dashboard_settings_controls_render(client):
    response = client.get("/v1/dashboard")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    for snippet in (
        'id="theme-select"',
        'id="items-per-page-select"',
        'id="landing-page-select"',
        'id="refresh-interval-select"',
        'id="user-table-meta"',
    ):
        assert snippet in html


def test_dashboard_realtime_refresh_helper_is_defined_before_dom_ready_handler():
    source = _read_template("dashboard.html")

    helper_index = source.find("async function refreshRealtimeData()")
    dom_ready_index = source.find("document.addEventListener('DOMContentLoaded'")

    assert helper_index != -1
    assert dom_ready_index != -1
    assert helper_index < dom_ready_index


@pytest.mark.parametrize(
    ("route", "present_ids", "absent_ids"),
    [
        ("/v1/login", ['id="loginForm"'], ['id="regForm"', 'id="resetPasswordForm"']),
        ("/v1/register", ['id="regForm"'], ['id="loginForm"', 'id="resetPasswordForm"']),
        ("/v1/forgot_password", ['id="resetPasswordForm"'], ['id="loginForm"', 'id="regForm"']),
    ],
)
def test_auth_routes_render_separate_pages(client, route, present_ids, absent_ids):
    response = client.get(route)

    assert response.status_code == 200
    html = response.get_data(as_text=True)

    for snippet in present_ids:
        assert snippet in html

    for snippet in absent_ids:
        assert snippet not in html
