from fastapi import APIRouter
from app.services.mt5_service import mt5_service
from app.services.connector import mt5_connector
from app.utils.exceptions import MT5ConnectionError
from app.models.trading import TerminalLoginRequest
from app.utils.cache import cache_manager
from typing import Dict, Any
import MetaTrader5 as mt5

router = APIRouter(prefix="/terminal", tags=["Terminal"])


@router.get("/info")
def get_terminal_info() -> Dict[str, Any]:
    info = mt5_service.get_terminal_info()
    if info is None:
        raise MT5ConnectionError("Failed to get terminal info")
    return info._asdict() if hasattr(info, '_asdict') else dict(info)


@router.get("/account/info")
def get_account_info() -> Dict[str, Any]:
    account_info = mt5_service.get_account_info()
    if account_info is None:
        raise MT5ConnectionError("Failed to get account info")
    return account_info._asdict() if hasattr(account_info, '_asdict') else dict(account_info)


@router.get("/status")
def get_terminal_status() -> Dict[str, Any]:
    return mt5_connector.status()


@router.post("/login")
def login_terminal(request: TerminalLoginRequest) -> Dict[str, Any]:
    account_info = mt5_connector.login(request.login, request.password, request.server)
    cache_manager.clear()
    terminal_info = mt5_service.get_terminal_info()
    account_payload = account_info._asdict() if hasattr(account_info, "_asdict") else dict(account_info)
    terminal_payload = terminal_info._asdict() if hasattr(terminal_info, "_asdict") else dict(terminal_info)
    return {
        "success": True,
        "account_info": account_payload,
        "terminal_info": terminal_payload,
        "trade_allowed": bool(terminal_payload.get("trade_allowed")),
        "status": mt5_connector.status(),
    }


@router.get("/snapshot")
def get_terminal_snapshot() -> Dict[str, Any]:
    account_info = mt5_service.get_account_info()
    if account_info is None:
        raise MT5ConnectionError("Failed to get account info")
    account_payload = account_info._asdict() if hasattr(account_info, "_asdict") else dict(account_info)
    positions = mt5_service.get_positions()
    return {
        "account_info": account_payload,
        "positions": positions,
        "positions_count": len(positions),
        "open_trades_count": 0,
        "fallback_used": False,
        "inconsistent": False,
        "error": "",
    }


@router.get("/version")
def get_mt5_version():
    mt5_service.initialize()
    return {"version": mt5.version()}


@router.post("/disconnect")
def disconnect():
    if not mt5.shutdown():
        raise MT5ConnectionError("Failed to disconnect from MT5 terminal")
    mt5_connector._initialized = False
    return {"status": "disconnected"}


@router.get("/ping")
def ping():
    mt5_service.initialize()
    info = mt5.terminal_info()
    if info is None:
        raise MT5ConnectionError("Terminal not connected")
    return {"ping": info.ping_last}


@router.get("/last_error")
def get_last_error():
    code, msg = mt5.last_error()
    return {"error_code": code, "error_message": msg}
