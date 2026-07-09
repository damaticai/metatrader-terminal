import time
from datetime import datetime, timezone
from typing import Any, Optional

import MetaTrader5 as mt5

from app.utils.config import settings


TIME_KEYS_SECONDS = ("time", "time_update", "time_setup", "time_done", "expiration")
TIME_KEYS_MILLISECONDS = ("time_msc", "time_update_msc", "time_done_msc", "time_setup_msc")
MAX_AUTO_OFFSET_SECONDS = 14 * 3600
RECENT_TICK_SECONDS = 6 * 3600

_cached_offset_seconds: Optional[int] = None
_cached_offset_at: float = 0.0


def _configured_offset() -> Optional[int]:
    value = getattr(settings.env, "MT5_TIME_OFFSET_SECONDS", None)
    return int(value) if value is not None else None


def _round_to_hour(seconds: float) -> int:
    return int(round(seconds / 3600.0) * 3600)


def broker_utc_offset_seconds(symbol: Optional[str] = None) -> int:
    configured = _configured_offset()
    if configured is not None:
        return configured

    global _cached_offset_seconds, _cached_offset_at
    now = time.time()
    if _cached_offset_seconds is not None and now - _cached_offset_at < 3600:
        return _cached_offset_seconds

    candidates: list[str] = []
    if symbol:
        candidates.append(symbol)
    try:
        for selected in mt5.symbols_get() or []:
            name = getattr(selected, "name", "")
            if name and name not in candidates:
                candidates.append(name)
            if len(candidates) >= 20:
                break
    except Exception:
        pass

    for candidate in candidates:
        try:
            mt5.symbol_select(candidate, True)
            tick = mt5.symbol_info_tick(candidate)
            tick_time = getattr(tick, "time", None) if tick else None
            if not tick_time:
                continue
            raw_diff = float(tick_time) - now
            rounded = _round_to_hour(raw_diff)
            residual = abs(raw_diff - rounded)
            if abs(rounded) <= MAX_AUTO_OFFSET_SECONDS and residual <= RECENT_TICK_SECONDS:
                _cached_offset_seconds = rounded
                _cached_offset_at = now
                return rounded
        except Exception:
            continue

    return _cached_offset_seconds or 0


def normalize_epoch_seconds(value: Any, offset_seconds: int) -> Optional[int]:
    if value in (None, ""):
        return None
    try:
        return int(float(value)) - int(offset_seconds)
    except (TypeError, ValueError):
        return None


def normalize_epoch_milliseconds(value: Any, offset_seconds: int) -> Optional[int]:
    if value in (None, ""):
        return None
    try:
        return int(float(value)) - int(offset_seconds) * 1000
    except (TypeError, ValueError):
        return None


def utc_datetime_from_epoch(value: Any) -> Optional[datetime]:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    timestamp = int(float(value))
    if timestamp > 10_000_000_000:
        timestamp //= 1000
    return datetime.fromtimestamp(timestamp, tz=timezone.utc)


def broker_datetime_from_utc(value: Any, symbol: Optional[str] = None) -> Optional[datetime]:
    utc_dt = utc_datetime_from_epoch(value)
    if utc_dt is None:
        return None
    return datetime.fromtimestamp(int(utc_dt.timestamp()) + broker_utc_offset_seconds(symbol), tz=timezone.utc)


def normalize_mt5_time_fields(payload: dict[str, Any], symbol: Optional[str] = None) -> dict[str, Any]:
    result = dict(payload)
    offset = broker_utc_offset_seconds(symbol or str(result.get("symbol") or ""))
    result["mt5_server_utc_offset_seconds"] = offset

    for key in TIME_KEYS_SECONDS:
        if key in result and result.get(key) not in (None, ""):
            raw_key = f"{key}_raw"
            result.setdefault(raw_key, result.get(key))
            normalized = normalize_epoch_seconds(result.get(key), offset)
            if normalized is not None:
                result[key] = normalized
                result[f"{key}_utc"] = normalized

    for key in TIME_KEYS_MILLISECONDS:
        if key in result and result.get(key) not in (None, ""):
            raw_key = f"{key}_raw"
            result.setdefault(raw_key, result.get(key))
            normalized = normalize_epoch_milliseconds(result.get(key), offset)
            if normalized is not None:
                result[key] = normalized
                result[f"{key}_utc"] = normalized

    return result


def normalize_mt5_records(records: list[dict[str, Any]], symbol: Optional[str] = None) -> list[dict[str, Any]]:
    return [normalize_mt5_time_fields(record, symbol or str(record.get("symbol") or "")) for record in records]
