"""Tests for API authentication."""


def test_protected_endpoint_requires_api_key(unauth_client):
    r = unauth_client.get("/api/v1/terminal/info")
    assert r.status_code in (401, 403)


def test_protected_endpoint_rejects_bad_key(unauth_client):
    r = unauth_client.get(
        "/api/v1/terminal/info",
        headers={"X-API-Key": "invalid-key-12345"},
    )
    assert r.status_code in (401, 403)


def test_protected_endpoint_accepts_valid_key(client):
    r = client.get("/api/v1/terminal/info")
    # 200 if MT5 connected, 500 if IPC issue — but not 401/403
    assert r.status_code != 401
    assert r.status_code != 403
