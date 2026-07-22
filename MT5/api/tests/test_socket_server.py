from __future__ import annotations

import asyncio
import json
import struct
import threading
import time

from app.socket_server import MAX_FRAME_BYTES, MT5SocketDispatcher, MT5SocketServer, json_value


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
