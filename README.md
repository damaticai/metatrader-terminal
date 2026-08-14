# MetaTrader Terminal Socket Service

This image runs MetaTrader 5 under Wine and exposes its Python IPC through a
loopback-only Raw TCP service. It is designed to sit behind the MT5 VPS Agent;
it does not expose an HTTP or REST trading API.

## Runtime boundary

- `127.0.0.1:18812`: MT5 Raw TCP service, available only to the VPS host Agent.
- `6901`: the existing browser desktop/noVNC service.
- MetaTrader5 Python calls are serialized through one execution lock.
- The image does not listen on or publish port `8000`.

The VPS Agent is the only component that may forward commands from the central
gateway. Do not publish `18812` on a public interface.

## Protocol

Each frame is:

1. Four-byte unsigned big-endian payload length.
2. A UTF-8 JSON object of exactly that length.

The maximum frame size is 1 MiB. A request has this shape:

```json
{
  "id": "request-id",
  "operation": "account.snapshot",
  "payload": {"symbols": ["XAUUSD"]}
}
```

Success and failure responses are respectively:

```json
{"id":"request-id","ok":true,"result":{}}
```

```json
{"id":"request-id","ok":false,"error":{"code":"ValueError","message":"..."}}
```

Supported operations:

- `health`
- `terminal.login`
- `account.snapshot`
- `symbols.list`
- `market.tick`
- `market.symbol_info`
- `market.candles`
- `trade.open`
- `trade.close`
- `trade.close_all`
- `history.deals`
- `history.orders`
- `network.public_ip` (fixed HTTPS provider allowlist; empty payload only)

`trade.open` accepts an optional Agent-generated `execution_id`. A successful
v1.3 response always includes `position_ticket`, `order_ticket`,
`confirmed_at`, and the same `execution_id`; a missing position ticket is a
failed confirmation rather than a usable open result.

`trade.events.subscribe` is a dedicated, long-lived connection. It accepts an
empty payload, returns the normal success frame, then emits frames shaped as
`{"type":"trade.event","payload":...}`. The terminal scans MT5 history every
20 ms without waiting ahead of a trade call, de-duplicates by deal ticket, and
reports `position.opened` / `position.closed` events. It is loopback-only like
every other Socket operation.

Protocol version `1.3` advertises its version, operation list, and event-stream
`detection_p95_ms` / `slo_ok` telemetry in the `health` response. Consumers
must fail closed if a required capability is absent or the event stream's p95
exceeds its 30 ms detection SLO.

## Running

From the repository root:

```bash
docker compose -f MT5/docker-compose.yml up --build
```

The compose file binds the Socket endpoint to `127.0.0.1:18812`. MT5 account
credentials are supplied through the existing environment variables:
`MT5_LOGIN`, `MT5_PASSWORD`, and `MT5_SERVER`.

## Tests

```bash
cd MT5/api
pytest -q
```

The tests cover framing, split/coalesced packets, invalid JSON, oversized
frames, serialized IPC dispatch, connector health, fixed-provider public-IP
validation/fallbacks, and the pinned MT5 image.
