from __future__ import annotations

import sys
from types import ModuleType
from types import SimpleNamespace

import pytest

class _MT5ImportStub(SimpleNamespace):
    def __getattr__(self, name):
        value = abs(hash(name)) % 1_000_000 + 1
        setattr(self, name, value)
        return value


sys.modules["MetaTrader5"] = _MT5ImportStub()
sys.modules.setdefault("pandas", SimpleNamespace())
market_data_stub = ModuleType("app.services.market_data")
market_data_stub.market_data_service = SimpleNamespace()
sys.modules["app.services.market_data"] = market_data_stub
time_sync_stub = ModuleType("app.utils.time_sync")
time_sync_stub.broker_datetime_from_utc = lambda value, _symbol=None: value
time_sync_stub.normalize_mt5_records = lambda value, _symbol=None: value
sys.modules["app.utils.time_sync"] = time_sync_stub

from app.services import trade as trade_module
from app.services.trade import TradeService
from app.utils.exceptions import MT5OrderError


def _fake_mt5(**overrides):
    values = {
        "ORDER_TYPE_BUY": 0,
        "ORDER_TYPE_SELL": 1,
        "ORDER_FILLING_IOC": 1,
        "ORDER_FILLING_FOK": 0,
        "ORDER_FILLING_RETURN": 2,
        "ORDER_TIME_GTC": 0,
        "TRADE_ACTION_DEAL": 1,
        "TRADE_RETCODE_PLACED": 10008,
        "TRADE_RETCODE_DONE": 10009,
        "TRADE_RETCODE_DONE_PARTIAL": 10010,
        "last_error": lambda: (1, "Success"),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _prepare_market_order(monkeypatch, result):
    fake = _fake_mt5(
        symbol_info_tick=lambda _symbol: SimpleNamespace(ask=2400.1, bid=2399.9),
        order_send=lambda _request: result,
    )
    monkeypatch.setattr(trade_module, "mt5", fake)
    monkeypatch.setattr(
        trade_module.mt5_connector,
        "initialize",
        lambda: True,
    )
    monkeypatch.setattr(
        trade_module.market_data_service,
        "ensure_symbol_selected",
        lambda _symbol: None,
        raising=False,
    )
    return fake


def test_market_order_preserves_no_money_retcode(monkeypatch):
    result = SimpleNamespace(retcode=10019, comment="No money")
    _prepare_market_order(monkeypatch, result)

    with pytest.raises(MT5OrderError) as caught:
        TradeService().send_market_order("XAUUSD", 0.01, "BUY", 0)

    assert caught.value.code == 10019


def test_empty_response_with_invalid_comment_is_explicit_input_failure(monkeypatch):
    fake = _prepare_market_order(monkeypatch, None)
    fake.last_error = lambda: (-2, 'Invalid "comment" argument')

    with pytest.raises(MT5OrderError) as caught:
        TradeService().send_market_order(
            "XAUUSD",
            0.01,
            "BUY",
            0,
            comment="invalid",
        )

    assert caught.value.code == -2
    assert "last_error" in caught.value.detail


def test_partial_fill_is_accepted_and_preserves_actual_volume(monkeypatch):
    result = SimpleNamespace(
        retcode=10010,
        comment="Done partially",
        volume=0.02,
        price=2400.1,
        _asdict=lambda: {
            "retcode": 10010,
            "comment": "Done partially",
            "volume": 0.02,
            "price": 2400.1,
        },
    )
    _prepare_market_order(monkeypatch, result)
    service = TradeService()
    monkeypatch.setattr(service, "_positions_for_order", lambda *_args: [])

    response = service.execute_market_order({
        "symbol": "XAUUSD",
        "volume": 0.03,
        "order_type": "BUY",
        "sl": 0,
        "tp": None,
        "deviation": 20,
        "comment": "",
        "magic": 1,
        "type_filling": "FOK",
    })

    assert response["success"] is True
    assert response["partial_fill"] is True
    assert response["actual_volume"] == 0.02
    assert response["summary"]["volume"] == 0.02


def test_full_market_order_uses_order_ticket_without_waiting_for_position_snapshot(monkeypatch):
    result = SimpleNamespace(
        retcode=10009,
        comment="Done",
        order=70001,
        deal=80001,
        volume=0.01,
        price=2400.1,
        _asdict=lambda: {
            "retcode": 10009,
            "comment": "Done",
            "order": 70001,
            "deal": 80001,
            "volume": 0.01,
            "price": 2400.1,
        },
    )
    _prepare_market_order(monkeypatch, result)
    service = TradeService()
    monkeypatch.setattr(service, "_positions_for_order", lambda *_args: [])

    response = service.execute_market_order({
        "symbol": "XAUUSD",
        "volume": 0.01,
        "order_type": "BUY",
        "sl": 0,
        "tp": None,
        "deviation": 20,
        "comment": "",
        "magic": 1,
        "type_filling": "FOK",
    })

    assert response["position_ticket"] == "70001"
    assert response["order_ticket"] == "70001"
    assert response["confirmation_source"] == "order_ticket"
    assert response["summary"]["ticket"] == "70001"
    assert response["order_result"]["position"] == "70001"


def test_partial_market_order_falls_back_to_history_position_ticket(monkeypatch):
    result = SimpleNamespace(
        retcode=10010,
        comment="Done partially",
        order=70002,
        volume=0.02,
        price=2400.1,
        _asdict=lambda: {
            "retcode": 10010,
            "comment": "Done partially",
            "order": 70002,
            "volume": 0.02,
            "price": 2400.1,
        },
    )
    fake = _prepare_market_order(monkeypatch, result)
    fake.history_deals_get = lambda *, ticket: [SimpleNamespace(_asdict=lambda: {
        "ticket": 80002,
        "order": ticket,
        "position_id": 90002,
        "entry": 0,
        "symbol": "XAUUSD",
        "magic": 1,
        "volume": 0.02,
        "price": 2400.1,
        "time": 1,
        "time_msc": 1000,
    })]
    service = TradeService()
    monkeypatch.setattr(service, "_positions_for_order", lambda *_args: [])

    response = service.execute_market_order({
        "symbol": "XAUUSD",
        "volume": 0.03,
        "order_type": "BUY",
        "sl": 0,
        "tp": None,
        "deviation": 20,
        "comment": "",
        "magic": 1,
        "type_filling": "FOK",
    })

    assert response["position_ticket"] == "90002"
    assert response["order_ticket"] == "70002"
    assert response["confirmation_source"] == "history_deal"


def test_close_missing_position_is_idempotent_success(monkeypatch):
    service = TradeService()
    monkeypatch.setattr(service, "get_positions", lambda *args, **kwargs: [])

    response = service.close_position_details(2198284468)

    assert response["success"] is True
    assert response["idempotent"] is True
    assert response["summary"]["ticket"] == "2198284468"


def test_close_all_keeps_successful_tickets_and_structured_failures(monkeypatch):
    service = TradeService()
    positions = [
        {"ticket": 101, "type": 0},
        {"ticket": 102, "type": 0},
    ]
    calls = 0

    def positions_snapshot(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        return positions if calls == 1 else [{"ticket": 102, "type": 0}]

    def close(ticket, **_kwargs):
        if ticket == 102:
            raise MT5OrderError(
                "Close failed: No money",
                code=10019,
                detail="retcode=10019",
            )
        return {"success": True, "summary": {"ticket": str(ticket)}}

    monkeypatch.setattr(trade_module.mt5_connector, "initialize", lambda: True)
    monkeypatch.setattr(service, "get_positions", positions_snapshot)
    monkeypatch.setattr(service, "close_position_details", close)

    response = service.close_all_positions_details()

    assert response["success"] is False
    assert response["closed_count"] == 1
    assert response["failed_count"] == 1
    assert response["closed"][0]["summary"]["ticket"] == "101"
    assert response["errors"][0]["ticket"] == 102
    assert response["errors"][0]["retcode"] == "10019"
    assert response["errors"][0]["exception_type"] == "MT5OrderError"
