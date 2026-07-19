import sys
from types import SimpleNamespace

sys.modules.setdefault("MetaTrader5", SimpleNamespace())

from app.services import connector as connector_module


def _connector_with(terminal_info, account_info):
    connector = connector_module.MT5Connector()
    connector._initialized = True
    connector_module.mt5 = SimpleNamespace(
        terminal_info=lambda: terminal_info,
        account_info=lambda: account_info,
    )
    return connector


def test_status_requires_real_broker_connection_for_trade_ready():
    connector = _connector_with(
        SimpleNamespace(connected=False, trade_allowed=True),
        SimpleNamespace(login=277761748, server="Demo"),
    )

    status = connector.status()

    assert status["terminal_ready"] is True
    assert status["logged_in"] is True
    assert status["trade_allowed"] is True
    assert status["broker_connected"] is False
    assert status["trade_ready"] is False


def test_status_is_trade_ready_only_when_all_conditions_are_true():
    connector = _connector_with(
        SimpleNamespace(connected=True, trade_allowed=True),
        SimpleNamespace(login=277761748, server="Demo"),
    )

    status = connector.status()

    assert status["broker_connected"] is True
    assert status["trade_ready"] is True
