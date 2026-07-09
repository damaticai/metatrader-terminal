"""Tests for history endpoints."""
import pytest


def test_get_deals_no_params(client):
    """Deals endpoint should work without date params (defaults to all history)."""
    r = client.get("/api/v1/history/deals")
    assert r.status_code == 200


def test_get_deals_with_dates(client):
    r = client.get("/api/v1/history/deals", params={
        "from_date": "2025-01-01T00:00:00",
        "to_date": "2025-12-31T23:59:59",
    })
    assert r.status_code == 200
    data = r.json()
    assert data is None or isinstance(data, list)


def test_get_deals_with_position(client):
    r = client.get("/api/v1/history/deals", params={
        "from_date": "2025-01-01T00:00:00",
        "to_date": "2025-12-31T23:59:59",
        "position": 0,
    })
    assert r.status_code == 200


def test_get_orders_no_params(client):
    r = client.get("/api/v1/history/orders")
    assert r.status_code == 200


def test_get_orders_with_dates(client):
    r = client.get("/api/v1/history/orders", params={
        "from_date": "2025-01-01T00:00:00",
        "to_date": "2025-12-31T23:59:59",
    })
    assert r.status_code == 200
    data = r.json()
    assert data is None or isinstance(data, list)


def test_get_order_by_ticket_not_found(client):
    r = client.get("/api/v1/history/order_by_ticket/999999999")
    assert r.status_code in (404, 500)
