import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime
from typing import Optional, List, Dict
from .connector import mt5_connector
from app.utils.constants import MT5Timeframe
from app.utils.exceptions import MT5SymbolNotFoundError
from app.utils.cache import cache_manager
from app.utils.time_sync import broker_datetime_from_utc, normalize_mt5_records, normalize_mt5_time_fields

class MarketDataService:
    def get_symbols(self) -> List[str]:
        cache_key = "all_symbols_list"
        cached_symbols = cache_manager.get(cache_key)
        if cached_symbols:
            return cached_symbols

        mt5_connector.initialize()
        symbols = mt5.symbols_get()
        if not symbols:
            return []
            
        symbols_list = [s.name for s in symbols]
        cache_manager.set(cache_key, symbols_list, ttl=3600)
        return symbols_list

    def get_timeframe(self, timeframe_str: str) -> int:
        try:
            return MT5Timeframe[timeframe_str.upper()].value
        except KeyError:
            valid_timeframes = ', '.join([t.name for t in MT5Timeframe])
            raise ValueError(f"Invalid timeframe: '{timeframe_str}'. Valid options are: {valid_timeframes}.")

    def get_symbol_info(self, symbol: str) -> Dict:
        cache_key = f"symbol_info_{symbol}"
        cached_info = cache_manager.get(cache_key)
        if cached_info:
            return cached_info

        mt5_connector.initialize()
        info = mt5.symbol_info(symbol)
        if not info:
            raise MT5SymbolNotFoundError(f"Symbol '{symbol}' not found.")
        
        info_dict = info._asdict()
        cache_manager.set(cache_key, info_dict, ttl=300)  # Symbol info changes rarely
        return info_dict

    def select_symbol(self, symbol: str) -> bool:
        mt5_connector.initialize()
        cache_key = f"symbol_selected_{symbol}"
        if cache_manager.get(cache_key):
            return True
        selected = mt5.symbol_select(symbol, True)
        if selected:
            cache_manager.set(cache_key, True, ttl=86400)
        return selected

    def ensure_symbol_selected(self, symbol: str) -> None:
        if not self.select_symbol(symbol):
            raise MT5SymbolNotFoundError(f"Failed to select symbol {symbol}")

    def get_symbol_info_tick(self, symbol: str) -> Dict:
        cache_key = f"symbol_tick_{symbol}"
        cached_tick = cache_manager.get(cache_key)
        if cached_tick:
            return cached_tick

        mt5_connector.initialize()
        self.ensure_symbol_selected(symbol)
        tick = mt5.symbol_info_tick(symbol)
        if not tick:
            raise MT5SymbolNotFoundError(f"Tick data for '{symbol}' not found.")

        tick_dict = normalize_mt5_time_fields(tick._asdict(), symbol)
        cache_manager.set(cache_key, tick_dict, ttl=1)  # Tick data changes frequently
        return tick_dict

    def copy_rates_from_pos(self, symbol: str, timeframe: str, start_pos: int, count: int) -> Optional[List[Dict]]:
        mt5_connector.initialize()
        self.ensure_symbol_selected(symbol)
        mt5_timeframe = self.get_timeframe(timeframe)
        rates = mt5.copy_rates_from_pos(symbol, mt5_timeframe, start_pos, count)
        if rates is None: return None
        df = pd.DataFrame(rates)
        return normalize_mt5_records(df.to_dict(orient='records'), symbol)

    def copy_rates_range(self, symbol: str, timeframe: str, start: datetime, end: datetime) -> Optional[List[Dict]]:
        mt5_connector.initialize()
        self.ensure_symbol_selected(symbol)
        mt5_timeframe = self.get_timeframe(timeframe)
        rates = mt5.copy_rates_range(symbol, mt5_timeframe, broker_datetime_from_utc(start, symbol), broker_datetime_from_utc(end, symbol))
        if rates is None: return None
        df = pd.DataFrame(rates)
        return normalize_mt5_records(df.to_dict(orient='records'), symbol)

    def copy_rates_from(self, symbol: str, timeframe: str, date_from: datetime, count: int) -> Optional[List[Dict]]:
        mt5_connector.initialize()
        self.ensure_symbol_selected(symbol)
        mt5_timeframe = self.get_timeframe(timeframe)
        rates = mt5.copy_rates_from(symbol, mt5_timeframe, broker_datetime_from_utc(date_from, symbol), count)
        if rates is None: return None
        df = pd.DataFrame(rates)
        return normalize_mt5_records(df.to_dict(orient='records'), symbol)

    def copy_ticks_from(self, symbol: str, date_from: datetime, count: int, flags: str = 'ALL') -> Optional[List[Dict]]:
        mt5_connector.initialize()
        self.ensure_symbol_selected(symbol)
        flags_map = {
            'ALL': mt5.COPY_TICKS_ALL,
            'INFO': mt5.COPY_TICKS_INFO,
            'TRADE': mt5.COPY_TICKS_TRADE,
        }
        ticks = mt5.copy_ticks_from(symbol, broker_datetime_from_utc(date_from, symbol), count, flags_map.get(flags.upper(), mt5.COPY_TICKS_ALL))
        if ticks is None or len(ticks) == 0: return None
        df = pd.DataFrame(ticks)
        return normalize_mt5_records(df.to_dict(orient='records'), symbol)

    def copy_ticks_range(self, symbol: str, date_from: datetime, date_to: datetime, flags: str = 'ALL') -> Optional[List[Dict]]:
        mt5_connector.initialize()
        self.ensure_symbol_selected(symbol)
        flags_map = {
            'ALL': mt5.COPY_TICKS_ALL,
            'INFO': mt5.COPY_TICKS_INFO,
            'TRADE': mt5.COPY_TICKS_TRADE,
        }
        ticks = mt5.copy_ticks_range(symbol, broker_datetime_from_utc(date_from, symbol), broker_datetime_from_utc(date_to, symbol), flags_map.get(flags.upper(), mt5.COPY_TICKS_ALL))
        if ticks is None or len(ticks) == 0: return None
        df = pd.DataFrame(ticks)
        return normalize_mt5_records(df.to_dict(orient='records'), symbol)

market_data_service = MarketDataService()
