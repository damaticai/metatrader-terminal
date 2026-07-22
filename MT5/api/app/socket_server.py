from __future__ import annotations

import asyncio
import json
import logging
import os
import struct
import threading
import uuid
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Callable

MAX_FRAME_BYTES = 1024 * 1024
HEADER = struct.Struct(">I")
logger = logging.getLogger("mt5.socket")


def connector():
    from app.services.connector import mt5_connector
    return mt5_connector


def service():
    from app.services.mt5_service import mt5_service
    return mt5_service


def json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if hasattr(value, "item"):
        return value.item()
    if hasattr(value, "_asdict"):
        return {key: json_value(item) for key, item in value._asdict().items()}
    if is_dataclass(value):
        return json_value(asdict(value))
    if isinstance(value, dict):
        return {str(key): json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_value(item) for item in value]
    return str(value)


class MT5SocketDispatcher:
    """Single-threaded dispatch boundary around the MetaTrader5 IPC package."""

    def __init__(self) -> None:
        self._ipc_lock = threading.Lock()
        self._operations: dict[str, Callable[[dict[str, Any]], Any]] = {
            "health": self.health,
            "terminal.login": self.login,
            "account.snapshot": self.snapshot,
            "symbols.list": self.symbols,
            "market.tick": self.tick,
            "market.symbol_info": self.symbol_info,
            "market.candles": self.candles,
            "trade.open": self.open_trade,
            "trade.close": self.close_trade,
            "trade.close_all": self.close_all,
            "history.deals": self.history_deals,
            "history.orders": self.history_orders,
        }

    def dispatch(self, operation: str, payload: dict[str, Any]) -> Any:
        handler = self._operations.get(operation)
        if not handler:
            raise ValueError(f"unsupported operation: {operation}")
        with self._ipc_lock:
            return json_value(handler(payload))

    @staticmethod
    def health(_payload: dict[str, Any]) -> dict[str, Any]:
        return connector().status()

    @staticmethod
    def login(payload: dict[str, Any]) -> Any:
        return connector().login(int(payload["login"]), str(payload["password"]), str(payload["server"]))

    @staticmethod
    def snapshot(payload: dict[str, Any]) -> dict[str, Any]:
        mt5 = service()
        account = mt5.get_account_info()
        positions = mt5.get_positions()
        ticks: dict[str, Any] = {}
        for symbol in dict.fromkeys(str(item) for item in payload.get("symbols", []) if str(item)):
            ticks[symbol] = mt5.get_symbol_info_tick(symbol)
        account_dict = json_value(account) or {}
        account_dict["online"] = True
        return {"account": account_dict, "positions": positions or [], "ticks": ticks}

    @staticmethod
    def symbols(_payload: dict[str, Any]) -> list[str]:
        return service().get_symbols()

    @staticmethod
    def tick(payload: dict[str, Any]) -> dict[str, Any]:
        return service().get_symbol_info_tick(str(payload["symbol"]))

    @staticmethod
    def symbol_info(payload: dict[str, Any]) -> dict[str, Any]:
        return service().get_symbol_info(str(payload["symbol"]))

    @staticmethod
    def candles(payload: dict[str, Any]) -> Any:
        return service().copy_rates_from_pos(
            str(payload["symbol"]),
            str(payload.get("timeframe") or "M1"),
            int(payload.get("start_pos") or 0),
            min(5000, max(1, int(payload.get("count") or 500))),
        )

    @staticmethod
    def open_trade(payload: dict[str, Any]) -> dict[str, Any]:
        order = {
            "symbol": str(payload["symbol"]),
            "volume": float(payload["volume"]),
            "order_type": str(payload.get("side") or payload.get("order_type") or "BUY").upper(),
            "sl": float(payload.get("sl") or 0),
            "tp": float(payload["tp"]) if payload.get("tp") not in (None, "") else None,
            "deviation": int(payload.get("deviation") or 20),
            "comment": str(payload.get("comment") or "")[:31],
            "magic": int(payload.get("magic") or 0),
            "type_filling": str(payload.get("type_filling") or "FOK"),
        }
        return service().execute_market_order(order)

    @staticmethod
    def close_trade(payload: dict[str, Any]) -> dict[str, Any]:
        return service().close_position_details(
            int(payload["ticket"]),
            volume=float(payload["volume"]) if payload.get("volume") not in (None, "") else None,
            deviation=int(payload.get("deviation") or 20),
            comment=str(payload.get("comment") or "")[:31],
            type_filling=str(payload.get("type_filling") or "FOK"),
        )

    @staticmethod
    def close_all(payload: dict[str, Any]) -> dict[str, Any]:
        return service().close_all_positions_details(
            order_type=str(payload.get("side") or "all"),
            magic=int(payload["magic"]) if payload.get("magic") not in (None, "") else None,
            type_filling=str(payload.get("type_filling") or "FOK"),
        )

    @staticmethod
    def history_deals(payload: dict[str, Any]) -> Any:
        return service().get_history_deals(position=int(payload["position"]) if payload.get("position") else None)

    @staticmethod
    def history_orders(payload: dict[str, Any]) -> Any:
        return service().get_history_orders(ticket=int(payload["ticket"]) if payload.get("ticket") else None)


class MT5SocketServer:
    def __init__(self, dispatcher: MT5SocketDispatcher | None = None) -> None:
        self.dispatcher = dispatcher or MT5SocketDispatcher()
        self.server: asyncio.AbstractServer | None = None

    async def start(self, host: str | None = None, port: int | None = None) -> asyncio.AbstractServer:
        self.server = await asyncio.start_server(
            self.handle_client,
            host or os.getenv("MT5_SOCKET_HOST", "127.0.0.1"),
            int(port or int(os.getenv("MT5_SOCKET_PORT", "18812"))),
            limit=MAX_FRAME_BYTES + HEADER.size,
        )
        return self.server

    async def serve_forever(self) -> None:
        server = await self.start()
        addresses = ", ".join(str(sock.getsockname()) for sock in server.sockets or [])
        logger.info("MT5 Socket service listening on %s", addresses)
        async with server:
            await server.serve_forever()

    async def handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            while True:
                try:
                    header = await reader.readexactly(HEADER.size)
                except asyncio.IncompleteReadError:
                    return
                length = HEADER.unpack(header)[0]
                if length <= 0 or length > MAX_FRAME_BYTES:
                    await self._write(writer, {"id": "", "ok": False, "error": {"code": "FRAME_TOO_LARGE", "message": "invalid frame length"}})
                    return
                raw = await reader.readexactly(length)
                request_id = ""
                try:
                    request = json.loads(raw.decode("utf-8"))
                    request_id = str(request.get("id") or uuid.uuid4())
                    operation = str(request.get("operation") or "")
                    payload = request.get("payload") or {}
                    if not isinstance(payload, dict):
                        raise ValueError("payload must be an object")
                    result = await asyncio.to_thread(self.dispatcher.dispatch, operation, payload)
                    response = {"id": request_id, "ok": True, "result": result}
                except Exception as exc:
                    logger.exception("MT5 Socket request failed")
                    response = {"id": request_id, "ok": False, "error": {"code": type(exc).__name__, "message": str(exc)}}
                await self._write(writer, response)
        finally:
            writer.close()
            await writer.wait_closed()

    @staticmethod
    async def _write(writer: asyncio.StreamWriter, payload: dict[str, Any]) -> None:
        raw = json.dumps(json_value(payload), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        writer.write(HEADER.pack(len(raw)) + raw)
        await writer.drain()


def main() -> None:
    asyncio.run(MT5SocketServer().serve_forever())


if __name__ == "__main__":
    main()
