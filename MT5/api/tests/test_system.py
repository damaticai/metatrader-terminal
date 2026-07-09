"""Tests for system/health endpoints (unauthenticated)."""


def test_root(unauth_client):
    r = unauth_client.get("/")
    assert r.status_code == 200
    data = r.json()
    assert data["message"] == "Welcome to MetaTrader 5 API"
    assert "docs" in data


def test_health(unauth_client):
    r = unauth_client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert "version" in data


def test_docs_page(unauth_client):
    r = unauth_client.get("/docs")
    assert r.status_code == 200


def test_openapi_schema(unauth_client):
    r = unauth_client.get("/openapi.json")
    assert r.status_code == 200
    schema = r.json()
    assert "paths" in schema
    assert "/health" in schema["paths"]
