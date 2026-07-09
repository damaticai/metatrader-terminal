"""Tests for symbols endpoints."""
import pytest


def test_get_all_symbols(client):
    r = client.get("/api/v1/symbols/")
    assert r.status_code == 200
    symbols = r.json()
    assert isinstance(symbols, list)
    assert len(symbols) > 0


def test_get_symbol_info(client):
    r = client.get("/api/v1/symbols/EURUSD")
    assert r.status_code == 200
    data = r.json()
    assert "name" in data or "symbol" in data


def test_get_symbol_info_query(client):
    r = client.get("/api/v1/symbols/info", params={"symbol": "EURUSD"})
    assert r.status_code == 200


def test_get_symbol_info_path(client):
    r = client.get("/api/v1/symbols/info/EURUSD")
    assert r.status_code == 200


def test_get_symbol_tick(client):
    r = client.get("/api/v1/symbols/ticks/EURUSD")
    assert r.status_code == 200
    data = r.json()
    assert "bid" in data
    assert "ask" in data
    assert data["bid"] > 0
    assert data["ask"] > 0


def test_get_tick_auto_selects_symbol(client):
    """Symbols not in Market Watch should be auto-selected."""
    r = client.get("/api/v1/symbols/ticks/GBPJPY")
    assert r.status_code == 200
    data = r.json()
    assert "bid" in data


def test_select_symbol(client):
    r = client.post("/api/v1/symbols/select/EURUSD")
    assert r.status_code == 200
    data = r.json()
    assert data["selected"] is True
    assert data["symbol"] == "EURUSD"


def test_select_unknown_symbol(client):
    r = client.post("/api/v1/symbols/select/FAKESYMBOL123")
    assert r.status_code == 404


def test_check_symbol(client):
    r = client.get("/api/v1/symbols/check/EURUSD")
    assert r.status_code == 200
    data = r.json()
    assert "visible" in data
    assert "name" in data


def test_check_unknown_symbol(client):
    r = client.get("/api/v1/symbols/check/FAKESYMBOL123")
    assert r.status_code in (404, 500)


def test_get_rates_pos(client):
    r = client.get("/api/v1/symbols/rates/pos", params={
        "symbol": "EURUSD",
        "timeframe": "H1",
        "num_bars": 10,
    })
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert len(data) <= 10
    if data:
        assert "time" in data[0]
        assert "open" in data[0]
        assert "close" in data[0]


def test_get_rates_range(client):
    r = client.get("/api/v1/symbols/rates/range", params={
        "symbol": "EURUSD",
        "timeframe": "D1",
        "start": "2025-01-01T00:00:00",
        "end": "2025-01-31T00:00:00",
    })
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
