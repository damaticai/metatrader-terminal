from __future__ import annotations

import asyncio
import json
import struct
import threading
import time
from datetime import datetime, timedelta, timezone

import pytest

from app import socket_server
from app.socket_server import (
    MAX_FRAME_BYTES,
    PUBLIC_IP_MAX_RESPONSE_BYTES,
    PUBLIC_IP_PROVIDERS,
    PublicIPLookupError,
    SOCKET_PROTOCOL_VERSION,
    MT5SocketDispatcher,
    MT5SocketServer,
    json_value,
)


async def read_response(reader):
    size = struct.unpack(">I", await reader.readexactly(4))[0]
    return json.loads((await reader.readexactly(size)).decode())


def test_socket_server_handles_coalesced_and_split_frames():
    class Dispatcher:
        def dispatch(self, operation, payload):
            return {"operation": operation, "payload": payload}

    async def scenario():
        server = MT5SocketServer(Dispatcher())
        listener = await server.start("127.0.0.1", 0)
        port = listener.sockets[0].getsockname()[1]
        reader, writer = await asyncio.open_connection("127.0.0.1", port)

        def frame(request):
            raw = json.dumps(request).encode()
            return struct.pack(">I", len(raw)) + raw

        first = frame({"id": "one", "operation": "health", "payload": {}})
        second = frame({"id": "two", "operation": "market.tick", "payload": {"symbol": "XAUUSD"}})
        writer.write(first[:3])
        await writer.drain()
        writer.write(first[3:] + second)
        await writer.drain()

        assert (await read_response(reader))["id"] == "one"
        assert (await read_response(reader))["result"]["payload"]["symbol"] == "XAUUSD"
        writer.close()
        await writer.wait_closed()
        listener.close()
        await listener.wait_closed()

    asyncio.run(scenario())


def test_socket_server_rejects_oversized_frame_and_serializes_values():
    assert json_value((1, 2)) == [1, 2]

    async def scenario():
        server = MT5SocketServer()
        listener = await server.start("127.0.0.1", 0)
        port = listener.sockets[0].getsockname()[1]
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        writer.write(struct.pack(">I", MAX_FRAME_BYTES + 1))
        await writer.drain()
        response = await read_response(reader)
        assert response["ok"] is False
        assert response["error"]["code"] == "FRAME_TOO_LARGE"
        writer.close()
        listener.close()
        await listener.wait_closed()

    asyncio.run(scenario())


def test_socket_server_returns_structured_error_for_invalid_json():
    async def scenario():
        server = MT5SocketServer()
        listener = await server.start("127.0.0.1", 0)
        port = listener.sockets[0].getsockname()[1]
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        raw = b"{not-json"
        writer.write(struct.pack(">I", len(raw)) + raw)
        await writer.drain()
        response = await read_response(reader)
        assert response["id"] == ""
        assert response["ok"] is False
        assert response["error"]["code"] == "JSONDecodeError"
        writer.close()
        await writer.wait_closed()
        listener.close()
        await listener.wait_closed()

    asyncio.run(scenario())


def test_dispatcher_serializes_all_mt5_ipc_calls():
    dispatcher = MT5SocketDispatcher()
    state = {"active": 0, "maximum": 0}
    state_lock = threading.Lock()

    def operation(_payload):
        with state_lock:
            state["active"] += 1
            state["maximum"] = max(state["maximum"], state["active"])
        time.sleep(0.02)
        with state_lock:
            state["active"] -= 1
        return True

    dispatcher._operations = {"test": operation}

    async def scenario():
        await asyncio.gather(*(
            asyncio.to_thread(dispatcher.dispatch, "test", {})
            for _ in range(8)
        ))

    asyncio.run(scenario())
    assert state["maximum"] == 1


def test_health_advertises_socket_protocol_version(monkeypatch):
    class FakeConnector:
        @staticmethod
        def status():
            return {"connected": True}

    monkeypatch.setattr(socket_server, "connector", lambda: FakeConnector())

    result = MT5SocketDispatcher().dispatch("health", {})

    assert result["connected"] is True
    assert result["socket_protocol_version"] == SOCKET_PROTOCOL_VERSION
    assert "network.public_ip" in result["socket_capabilities"]


class FakeHTTPResponse:
    def __init__(self, body: bytes, status: int = 200, final_url: str = ""):
        self.body = body
        self.status = status
        self.final_url = final_url

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, limit: int) -> bytes:
        return self.body[:limit]

    def geturl(self) -> str:
        return self.final_url or PUBLIC_IP_PROVIDERS[0][0]


def test_public_ip_operation_is_registered_and_returns_verified_result(monkeypatch):
    calls = []

    def fake_open(request, timeout):
        calls.append((request.full_url, timeout))
        return FakeHTTPResponse(b"8.8.8.8\n")

    monkeypatch.setattr(socket_server, "open_public_ip_provider", fake_open)
    dispatcher = MT5SocketDispatcher()

    class ForbiddenIPCLock:
        def __enter__(self):
            raise AssertionError("public IP lookup must not hold the MT5 IPC lock")

        def __exit__(self, *_args):
            return False

    dispatcher._ipc_lock = ForbiddenIPCLock()

    result = dispatcher.dispatch("network.public_ip", {})

    assert "network.public_ip" in dispatcher._operations
    assert result["egress_ip"] == "8.8.8.8"
    assert result["source"] == "mt5_socket:ipify"
    assert isinstance(result["latency_ms"], float)
    assert result["latency_ms"] >= 0
    assert result["verified_at"].endswith("+00:00")
    assert calls == [(PUBLIC_IP_PROVIDERS[0][0], socket_server.PUBLIC_IP_TIMEOUT_SECONDS)]


def test_public_ip_falls_back_in_fixed_order(monkeypatch):
    calls = []

    def fake_open(request, timeout):
        calls.append((request.full_url, timeout))
        if len(calls) == 1:
            raise TimeoutError("provider details must not escape")
        return FakeHTTPResponse(
            b"2001:4860:4860::8888",
            final_url=PUBLIC_IP_PROVIDERS[1][0],
        )

    monkeypatch.setattr(socket_server, "open_public_ip_provider", fake_open)

    result = MT5SocketDispatcher().dispatch("network.public_ip", {})

    assert result["egress_ip"] == "2001:4860:4860::8888"
    assert result["source"] == "mt5_socket:aws-checkip"
    assert [item[0] for item in calls] == [url for url, _provider in PUBLIC_IP_PROVIDERS[:2]]


@pytest.mark.parametrize(
    ("factory", "expected_exception"),
    [
        (lambda: FakeHTTPResponse(b"8.8.8.8", status=503), PublicIPLookupError),
        (lambda: TimeoutError("timed out"), PublicIPLookupError),
        (lambda: FakeHTTPResponse(b"not-an-ip"), PublicIPLookupError),
        (lambda: FakeHTTPResponse(b"127.0.0.1"), PublicIPLookupError),
        (
            lambda: FakeHTTPResponse(b"8.8.8.8", final_url="http://127.0.0.1/private"),
            PublicIPLookupError,
        ),
        (
            lambda: FakeHTTPResponse(b"1" * (PUBLIC_IP_MAX_RESPONSE_BYTES + 1)),
            PublicIPLookupError,
        ),
    ],
)
def test_public_ip_rejects_unsafe_provider_responses(monkeypatch, factory, expected_exception):
    def fake_open(_request, timeout):
        assert timeout == socket_server.PUBLIC_IP_TIMEOUT_SECONDS
        value = factory()
        if isinstance(value, Exception):
            raise value
        return value

    monkeypatch.setattr(socket_server, "open_public_ip_provider", fake_open)

    with pytest.raises(expected_exception, match="all configured providers"):
        MT5SocketDispatcher().dispatch("network.public_ip", {})


def test_public_ip_redirect_handler_never_follows_location():
    request = socket_server.urllib.request.Request(PUBLIC_IP_PROVIDERS[0][0])

    with pytest.raises(socket_server.urllib.error.HTTPError) as exc:
        socket_server.NoRedirectHandler().redirect_request(
            request,
            None,
            302,
            "Found",
            {},
            "http://127.0.0.1/private",
        )

    assert exc.value.filename == PUBLIC_IP_PROVIDERS[0][0]


def test_public_ip_rejects_arbitrary_target_without_network_access(monkeypatch):
    def unexpected_open(*_args, **_kwargs):
        raise AssertionError("network must not be called")

    monkeypatch.setattr(socket_server, "open_public_ip_provider", unexpected_open)

    with pytest.raises(ValueError, match="payload must be empty"):
        MT5SocketDispatcher().dispatch(
            "network.public_ip",
            {"url": "http://169.254.169.254/latest/meta-data"},
        )


def test_public_ip_all_failures_return_stable_structured_error(monkeypatch):
    def fake_open(_request, timeout):
        assert timeout == socket_server.PUBLIC_IP_TIMEOUT_SECONDS
        raise TimeoutError("secret endpoint detail")

    monkeypatch.setattr(socket_server, "open_public_ip_provider", fake_open)

    async def scenario():
        server = MT5SocketServer()
        listener = await server.start("127.0.0.1", 0)
        port = listener.sockets[0].getsockname()[1]
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        request = json.dumps({
            "id": "public-ip-failure",
            "operation": "network.public_ip",
            "payload": {},
        }).encode()
        writer.write(struct.pack(">I", len(request)) + request)
        await writer.drain()
        response = await read_response(reader)
        writer.close()
        await writer.wait_closed()
        listener.close()
        await listener.wait_closed()
        return response

    response = asyncio.run(scenario())
    assert response == {
        "id": "public-ip-failure",
        "ok": False,
        "error": {
            "code": "PublicIPLookupError",
            "message": "public IP lookup failed for all configured providers",
        },
    }


def test_history_deals_is_bounded_sorted_and_cursor_driven(monkeypatch):
    now = datetime.now(timezone.utc)
    base = int((now - timedelta(minutes=1)).timestamp() * 1000)

    class FakeHistory:
        def get_history_deals(self, **kwargs):
            assert kwargs["position"] == 70001
            assert kwargs["to_date"] - kwargs["from_date"] < timedelta(hours=1)
            return [
                {
                    "ticket": 100, "position_id": 0, "order": 0,
                    "symbol": "", "type": 2, "volume": 0,
                    "price": 0, "profit": 1000, "time_msc": base + 500,
                    "entry": 0, "reason": 0, "comment": "Deposit",
                },
                {
                    "ticket": 102, "position_id": 70001, "order": 502,
                    "symbol": "XAUUSD", "type": 1, "volume": 0.4,
                    "price": 2411.5, "profit": 8.0, "commission": -0.2,
                    "swap": -0.1, "time": (base + 2000) // 1000,
                    "time_msc": base + 2000, "entry": 1, "reason": 4,
                },
                {
                    "ticket": 101, "position_id": 70001, "order": 501,
                    "symbol": "XAUUSD", "type": 0, "volume": 1.0,
                    "price": 2400.5, "profit": 0, "commission": -0.5,
                    "swap": 0, "time": (base + 1000) // 1000,
                    "time_msc": base + 1000, "entry": 0, "reason": 3,
                },
                {
                    "ticket": 103, "position_id": 70002, "order": 503,
                    "symbol": "EURUSD", "type": 0, "volume": 0.1,
                    "price": 1.1, "profit": 0, "time_msc": base + 3000,
                    "entry": 0, "reason": 0,
                },
            ]

    monkeypatch.setattr(socket_server, "service", lambda: FakeHistory())
    result = MT5SocketDispatcher.history_deals({
        "position": "70001",
        "from_time": (now - timedelta(minutes=2)).isoformat(),
        "to_time": now.isoformat(),
        "cursor": {"time_msc": base + 1000, "deal_ticket": "101"},
        "limit": 1,
        "page": 1,
    })

    assert [deal["deal_ticket"] for deal in result["deals"]] == ["102"]
    assert result["deals"][0] == {
        "deal_ticket": "102", "position_ticket": "70001", "order_ticket": "502",
        "symbol": "XAUUSD", "side": "sell", "volume": 0.4, "price": 2411.5,
        "profit": 8.0, "commission": -0.2, "swap": -0.1,
        "time": (base + 2000) // 1000, "time_msc": base + 2000,
        "entry": "out", "reason": "sl", "magic": 0, "comment": "",
        "source": "mt5_history",
    }
    assert result["cursor"] == {"time_msc": base + 2000, "deal_ticket": "102"}
    with pytest.raises(ValueError, match="unsupported history.deals field"):
        MT5SocketDispatcher.history_deals({"url": "https://attacker.invalid"})
    with pytest.raises(ValueError, match="exceeds 31 days"):
        MT5SocketDispatcher.history_deals({
            "from_time": (now - timedelta(days=32)).isoformat(),
            "to_time": now.isoformat(),
        })
