from __future__ import annotations

import asyncio
import ipaddress
import json
import logging
import os
import struct
import threading
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import asdict, is_dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Callable

MAX_FRAME_BYTES = 1024 * 1024
HEADER = struct.Struct(">I")
SOCKET_PROTOCOL_VERSION = "1.1"
PUBLIC_IP_PROVIDERS = (
    ("https://api.ipify.org", "ipify"),
    ("https://checkip.amazonaws.com", "aws-checkip"),
    ("https://ifconfig.me/ip", "ifconfig-me"),
)
PUBLIC_IP_TIMEOUT_SECONDS = 4.0
PUBLIC_IP_MAX_RESPONSE_BYTES = 128
HISTORY_MAX_RANGE = timedelta(days=31)
HISTORY_DEFAULT_RANGE = timedelta(days=7)
HISTORY_MAX_LIMIT = 500
HISTORY_MAX_PAGE = 20
HISTORY_DEAL_KEYS = frozenset({
    "position", "from_time", "to_time", "cursor", "cursor_deal_ticket",
    "cursor_time_msc", "limit", "page",
})
DEAL_ENTRY_NAMES = {0: "in", 1: "out", 2: "inout", 3: "out_by"}
DEAL_REASON_NAMES = {
    0: "client", 1: "mobile", 2: "web", 3: "expert", 4: "sl",
    5: "tp", 6: "stopout", 7: "rollover", 8: "variation_margin",
    9: "split", 10: "corporate_action",
}
DEAL_SIDE_NAMES = {0: "buy", 1: "sell"}
logger = logging.getLogger("mt5.socket")


class PublicIPLookupError(RuntimeError):
    """Stable, non-sensitive failure returned when every fixed provider fails."""


class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Reject redirects so the fixed provider allowlist cannot be escaped."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, "redirects are disabled", headers, fp)


PUBLIC_IP_OPENER = urllib.request.build_opener(NoRedirectHandler())


def open_public_ip_provider(request: urllib.request.Request, timeout: float):
    return PUBLIC_IP_OPENER.open(request, timeout=timeout)


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
            "network.public_ip": self.public_ip,
        }

    def dispatch(self, operation: str, payload: dict[str, Any]) -> Any:
        handler = self._operations.get(operation)
        if not handler:
            raise ValueError(f"unsupported operation: {operation}")
        if operation == "network.public_ip":
            return json_value(handler(payload))
        with self._ipc_lock:
            return json_value(handler(payload))

    def health(self, _payload: dict[str, Any]) -> dict[str, Any]:
        status = json_value(connector().status())
        if not isinstance(status, dict):
            status = {"status": status}
        return {
            **status,
            "socket_protocol_version": SOCKET_PROTOCOL_VERSION,
            "socket_capabilities": sorted(self._operations),
        }

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
    def _history_time(value: Any, *, default: datetime) -> datetime:
        if value in (None, ""):
            return default
        if isinstance(value, datetime):
            parsed = value
        else:
            try:
                numeric = float(value)
            except (TypeError, ValueError):
                parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            else:
                if numeric > 10_000_000_000:
                    numeric /= 1000
                parsed = datetime.fromtimestamp(numeric, tz=timezone.utc)
        return parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)

    @staticmethod
    def _deal_value(deal: dict[str, Any], *keys: str, default: Any = "") -> Any:
        for key in keys:
            value = deal.get(key)
            if value not in (None, ""):
                return value
        return default

    @classmethod
    def _normalize_deal(cls, raw: Any) -> dict[str, Any] | None:
        deal = json_value(raw)
        if not isinstance(deal, dict):
            raise ValueError("MT5 history deal must be an object")
        ticket = int(cls._deal_value(deal, "ticket", "deal", default=0) or 0)
        position_ticket = int(cls._deal_value(deal, "position_ticket", "position_id", "position", default=0) or 0)
        order_ticket = int(cls._deal_value(deal, "order_ticket", "order", default=0) or 0)
        time_value = cls._deal_value(deal, "time", default=0)
        time_msc = int(cls._deal_value(deal, "time_msc", default=0) or 0)
        if not time_msc and time_value:
            time_msc = int(float(time_value) * 1000)
        entry_raw = cls._deal_value(deal, "entry", default="")
        reason_raw = cls._deal_value(deal, "reason", default="")
        side_raw = cls._deal_value(deal, "side", "type", default="")
        try:
            entry = DEAL_ENTRY_NAMES.get(int(entry_raw), str(entry_raw).lower())
        except (TypeError, ValueError):
            entry = str(entry_raw).lower()
        try:
            reason = DEAL_REASON_NAMES.get(int(reason_raw), str(reason_raw).lower())
        except (TypeError, ValueError):
            reason = str(reason_raw).lower()
        try:
            side = DEAL_SIDE_NAMES.get(int(side_raw), str(side_raw).lower())
        except (TypeError, ValueError):
            side = str(side_raw).lower()
        if not position_ticket or side not in {"buy", "sell"}:
            return None
        if not ticket or not time_msc:
            raise ValueError("MT5 history trade deal is missing ticket or time_msc")
        return {
            "deal_ticket": str(ticket),
            "position_ticket": str(position_ticket),
            "order_ticket": str(order_ticket) if order_ticket else "",
            "symbol": str(cls._deal_value(deal, "symbol", default="")),
            "side": side,
            "volume": float(cls._deal_value(deal, "volume", default=0) or 0),
            "price": float(cls._deal_value(deal, "price", default=0) or 0),
            "profit": float(cls._deal_value(deal, "profit", default=0) or 0),
            "commission": float(cls._deal_value(deal, "commission", default=0) or 0),
            "swap": float(cls._deal_value(deal, "swap", default=0) or 0),
            "time": int(float(time_value or time_msc / 1000)),
            "time_msc": time_msc,
            "entry": entry,
            "reason": reason,
            "magic": int(cls._deal_value(deal, "magic", default=0) or 0),
            "comment": str(cls._deal_value(deal, "comment", default=""))[:255],
            "source": "mt5_history",
        }

    @classmethod
    def history_deals(cls, payload: dict[str, Any]) -> dict[str, Any]:
        unknown = set(payload) - HISTORY_DEAL_KEYS
        if unknown:
            raise ValueError(f"unsupported history.deals field: {sorted(unknown)[0]}")
        now = datetime.now(timezone.utc)
        start = cls._history_time(payload.get("from_time"), default=now - HISTORY_DEFAULT_RANGE)
        end = cls._history_time(payload.get("to_time"), default=now + timedelta(seconds=1))
        if end <= start:
            raise ValueError("history.deals time range is invalid")
        if end - start > HISTORY_MAX_RANGE:
            raise ValueError("history.deals time range exceeds 31 days")
        limit = min(HISTORY_MAX_LIMIT, max(1, int(payload.get("limit") or 200)))
        page = min(HISTORY_MAX_PAGE, max(1, int(payload.get("page") or 1)))
        position = int(payload.get("position") or 0)
        if position < 0:
            raise ValueError("history.deals position is invalid")
        cursor = payload.get("cursor") or {}
        if cursor and not isinstance(cursor, dict):
            raise ValueError("history.deals cursor must be an object")
        cursor_time = int((cursor or {}).get("time_msc") or payload.get("cursor_time_msc") or 0)
        cursor_ticket = int((cursor or {}).get("deal_ticket") or payload.get("cursor_deal_ticket") or 0)
        raw_deals = service().get_history_deals(
            position=position or None,
            from_date=start,
            to_date=end,
        )
        deals: list[dict[str, Any]] = []
        for raw in raw_deals or []:
            deal = cls._normalize_deal(raw)
            if deal is None:
                continue
            deal_key = (int(deal["time_msc"]), int(deal["deal_ticket"]))
            if deal_key <= (cursor_time, cursor_ticket):
                continue
            if position and int(deal["position_ticket"]) != position:
                continue
            if not int(start.timestamp() * 1000) <= deal_key[0] <= int(end.timestamp() * 1000):
                continue
            deals.append(deal)
        deals.sort(key=lambda item: (int(item["time_msc"]), int(item["deal_ticket"])))
        offset = (page - 1) * limit
        selected = deals[offset:offset + limit]
        last = selected[-1] if selected else None
        return {
            "deals": selected,
            "cursor": {
                "time_msc": int(last["time_msc"]) if last else cursor_time,
                "deal_ticket": str(last["deal_ticket"]) if last else str(cursor_ticket or ""),
            },
            "has_more": offset + len(selected) < len(deals),
            "page": page,
            "limit": limit,
            "from_time": start.isoformat(),
            "to_time": end.isoformat(),
        }

    @staticmethod
    def history_orders(payload: dict[str, Any]) -> Any:
        return service().get_history_orders(ticket=int(payload["ticket"]) if payload.get("ticket") else None)

    @staticmethod
    def public_ip(payload: dict[str, Any]) -> dict[str, Any]:
        """Resolve container egress through the fixed provider allowlist only."""

        if payload:
            raise ValueError("network.public_ip payload must be empty")
        started = time.perf_counter()
        for url, provider in PUBLIC_IP_PROVIDERS:
            try:
                request = urllib.request.Request(
                    url,
                    headers={
                        "Accept": "text/plain",
                        "User-Agent": f"mt5-socket/{SOCKET_PROTOCOL_VERSION}",
                    },
                    method="GET",
                )
                with open_public_ip_provider(request, PUBLIC_IP_TIMEOUT_SECONDS) as response:
                    status = int(getattr(response, "status", 200) or 200)
                    if status != 200:
                        raise RuntimeError("unexpected HTTP status")
                    final_url = str(getattr(response, "geturl", lambda: url)() or "")
                    if final_url != url:
                        raise ValueError("provider redirect is not allowed")
                    body = response.read(PUBLIC_IP_MAX_RESPONSE_BYTES + 1)
                    if len(body) > PUBLIC_IP_MAX_RESPONSE_BYTES:
                        raise ValueError("response is too long")
                    raw = body.decode("ascii", errors="strict").strip()
                address = ipaddress.ip_address(raw)
                if not address.is_global:
                    raise ValueError("provider returned a non-public IP address")
                egress_ip = str(address)
                return {
                    "egress_ip": egress_ip,
                    "verified_at": datetime.now(timezone.utc).isoformat(),
                    "latency_ms": round((time.perf_counter() - started) * 1000, 3),
                    "source": f"mt5_socket:{provider}",
                }
            except Exception as exc:
                logger.warning("Public IP provider %s failed: %s", provider, type(exc).__name__)
        raise PublicIPLookupError("public IP lookup failed for all configured providers")


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
