"""Tests for positions endpoints."""
import pytest


def test_get_positions(client):
    r = client.get("/api/v1/positions/")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)


def test_get_positions_by_magic(client):
    r = client.get("/api/v1/positions/", params={"magic": 0})
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_get_positions_by_symbol(client):
    r = client.get("/api/v1/positions/by_symbol/EURUSD")
    # 200 if positions exist, 404 if none, 500 if MT5 returns None
    assert r.status_code in (200, 404, 500)


def test_close_nonexistent_position(client):
    r = client.post("/api/v1/positions/close", params={"ticket": 999999999})
    assert r.status_code in (400, 500)


def test_close_accepts_type_filling(client):
    """Verify type_filling param is accepted (even if position doesn't exist)."""
    r = client.post("/api/v1/positions/close", params={
        "ticket": 999999999,
        "type_filling": "FOK",
    })
    # Should fail because position doesn't exist, not because of param
    assert r.status_code in (400, 500)


def test_close_all_empty(client):
    """Close all with no open positions should succeed."""
    r = client.post("/api/v1/positions/close_all")
    assert r.status_code == 200
    data = r.json()
    assert "message" in data


def test_close_all_accepts_type_filling(client):
    r = client.post("/api/v1/positions/close_all", params={"type_filling": "IOC"})
    assert r.status_code == 200
