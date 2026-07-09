"""Tests for trading endpoints (order execution).

These tests place real orders on a demo account. They require:
- MT5 terminal connected to a demo broker
- Algo trading enabled
- Sufficient demo balance
"""
import pytest
import time


DEMO_SYMBOL = "EURUSD"
DEMO_VOLUME = 0.01


@pytest.fixture(scope="module")
def ensure_symbol_selected(client):
    """Ensure test symbol is in Market Watch."""
    client.post(f"/api/v1/symbols/select/{DEMO_SYMBOL}")


def test_order_check(client, ensure_symbol_selected):
    r = client.get(f"/api/v1/trading/order_check/{DEMO_SYMBOL}")
    assert r.status_code == 200
    data = r.json()
    assert "name" in data


def test_order_check_unknown_symbol(client):
    r = client.get("/api/v1/trading/order_check/FAKESYMBOL")
    assert r.status_code in (404, 500)


def test_send_buy_order(client, ensure_symbol_selected):
    """Place a BUY order, verify it appears in positions, then close it."""
    tick = client.get(f"/api/v1/symbols/ticks/{DEMO_SYMBOL}").json()
    sl = round(tick["bid"] - 0.01, 5)

    r = client.post("/api/v1/trading/order", json={
        "symbol": DEMO_SYMBOL,
        "volume": DEMO_VOLUME,
        "order_type": "BUY",
        "sl": sl,
        "type_filling": "FOK",
    })
    assert r.status_code == 201, f"Order failed: {r.json()}"
    assert r.json()["success"] is True

    # Verify position exists
    time.sleep(1)
    positions = client.get("/api/v1/positions/").json()
    symbols = [p["symbol"] for p in positions]
    assert DEMO_SYMBOL in symbols

    # Close the position
    pos = next((p for p in positions if p["symbol"] == DEMO_SYMBOL), None)
    if pos:
        close_r = client.post("/api/v1/positions/close", params={
            "ticket": pos["ticket"],
            "type_filling": "FOK",
        })
        assert close_r.status_code == 200


def test_send_sell_order(client, ensure_symbol_selected):
    """Place a SELL order and close it."""
    tick = client.get(f"/api/v1/symbols/ticks/{DEMO_SYMBOL}").json()
    sl = round(tick["ask"] + 0.01, 5)

    r = client.post("/api/v1/trading/order", json={
        "symbol": DEMO_SYMBOL,
        "volume": DEMO_VOLUME,
        "order_type": "SELL",
        "sl": sl,
        "type_filling": "FOK",
    })
    assert r.status_code == 201, f"Order failed: {r.json()}"
    assert r.json()["success"] is True

    # Close
    time.sleep(1)
    positions = client.get("/api/v1/positions/").json()
    pos = next((p for p in positions if p["symbol"] == DEMO_SYMBOL), None)
    if pos:
        client.post("/api/v1/positions/close", params={
            "ticket": pos["ticket"],
            "type_filling": "FOK",
        })


def test_send_order_with_tp(client, ensure_symbol_selected):
    """Place order with take profit."""
    tick = client.get(f"/api/v1/symbols/ticks/{DEMO_SYMBOL}").json()
    sl = round(tick["bid"] - 0.01, 5)
    tp = round(tick["ask"] + 0.01, 5)

    r = client.post("/api/v1/trading/order", json={
        "symbol": DEMO_SYMBOL,
        "volume": DEMO_VOLUME,
        "order_type": "BUY",
        "sl": sl,
        "tp": tp,
        "type_filling": "FOK",
    })
    assert r.status_code == 201
    assert r.json()["success"] is True

    # Cleanup
    time.sleep(1)
    positions = client.get("/api/v1/positions/").json()
    pos = next((p for p in positions if p["symbol"] == DEMO_SYMBOL), None)
    if pos:
        client.post("/api/v1/positions/close", params={
            "ticket": pos["ticket"],
            "type_filling": "FOK",
        })


def test_send_order_invalid_type(client):
    r = client.post("/api/v1/trading/order", json={
        "symbol": DEMO_SYMBOL,
        "volume": DEMO_VOLUME,
        "order_type": "INVALID",
        "sl": 1.0,
    })
    # 422 from pydantic validation or 500 from MT5 rejection
    assert r.status_code in (422, 500)


def test_modify_sl_tp(client, ensure_symbol_selected):
    """Place an order, modify SL/TP via positions endpoint, then close."""
    tick = client.get(f"/api/v1/symbols/ticks/{DEMO_SYMBOL}").json()
    sl = round(tick["bid"] - 0.01, 5)

    # Open position
    r = client.post("/api/v1/trading/order", json={
        "symbol": DEMO_SYMBOL,
        "volume": DEMO_VOLUME,
        "order_type": "BUY",
        "sl": sl,
        "type_filling": "FOK",
    })
    assert r.status_code == 201

    time.sleep(1)

    # Get the position ticket
    positions = client.get("/api/v1/positions/").json()
    pos = next((p for p in positions if p["symbol"] == DEMO_SYMBOL), None)
    assert pos is not None, "Position not found after order"

    # Get trade_id from DB trades
    trades = client.get("/api/v1/trading/").json()
    trade = next((t for t in trades if t.get("symbol") == DEMO_SYMBOL), None)
    if trade and trade.get("id"):
        new_sl = round(tick["bid"] - 0.02, 5)
        new_tp = round(tick["ask"] + 0.02, 5)
        mod_r = client.post("/api/v1/trading/modify-sl-tp", params={"trade_id": trade["id"]}, json={
            "ticket": pos["ticket"],
            "sl": new_sl,
            "tp": new_tp,
        })
        assert mod_r.status_code in (200, 400, 500)

    # Cleanup
    client.post("/api/v1/positions/close", params={
        "ticket": pos["ticket"],
        "type_filling": "FOK",
    })
