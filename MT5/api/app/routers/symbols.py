from fastapi import APIRouter, HTTPException, Query
from app.services.mt5_service import mt5_service
from app.utils.exceptions import MT5SymbolNotFoundError
from typing import List
from datetime import datetime
import MetaTrader5 as mt5

router = APIRouter(prefix="/symbols", tags=["Symbols"])


@router.get("/", response_model=List[str])
def get_all_symbols():
    return mt5_service.get_symbols()


@router.get("/info")
def get_symbol_info_query(symbol: str = Query(...)):
    return mt5_service.get_symbol_info(symbol)


@router.get("/info/{symbol}")
def get_symbol_info_path(symbol: str):
    return mt5_service.get_symbol_info(symbol)


@router.post("/select/{symbol}")
def select_symbol(symbol: str):
    selected = mt5_service.select_symbol(symbol)
    if not selected:
        raise MT5SymbolNotFoundError(f"Failed to select symbol '{symbol}'")
    return {"symbol": symbol, "selected": True}


@router.get("/ticks/{symbol}")
def get_symbol_tick(symbol: str):
    return mt5_service.get_symbol_info_tick(symbol)


@router.get("/{symbol}")
def get_symbol(symbol: str):
    return mt5_service.get_symbol_info(symbol)


@router.get("/rates/from")
def fetch_data_from(symbol: str, timeframe: str, date_from: datetime, count: int = 100):
    data = mt5_service.copy_rates_from(symbol, timeframe, date_from, count)
    if data is None:
        raise HTTPException(status_code=404, detail="No rate data found")
    return data


@router.get("/rates/pos")
def fetch_data_pos(symbol: str, timeframe: str = "M1", num_bars: int = 100):
    data = mt5_service.copy_rates_from_pos(symbol, timeframe, 0, num_bars)
    if data is None:
        raise HTTPException(status_code=404, detail="No rate data found")
    return data


@router.get("/rates/range")
def fetch_data_range(symbol: str, timeframe: str, start: datetime, end: datetime):
    data = mt5_service.copy_rates_range(symbol, timeframe, start, end)
    if data is None:
        raise HTTPException(status_code=404, detail="No rate data found")
    return data


@router.get("/ticks/{symbol}/from")
def get_ticks_from(symbol: str, date_from: datetime, count: int = 1000, flags: str = "ALL"):
    data = mt5_service.copy_ticks_from(symbol, date_from, count, flags)
    if data is None:
        raise HTTPException(status_code=404, detail="No tick data found")
    return data


@router.get("/ticks/{symbol}/range")
def get_ticks_range(symbol: str, date_from: datetime, date_to: datetime, flags: str = "ALL"):
    data = mt5_service.copy_ticks_range(symbol, date_from, date_to, flags)
    if data is None:
        raise HTTPException(status_code=404, detail="No tick data found")
    return data


@router.post("/book/{symbol}/subscribe")
def subscribe_book(symbol: str):
    mt5_service.initialize()
    mt5_service.select_symbol(symbol)
    result = mt5.market_book_add(symbol)
    if not result:
        raise MT5SymbolNotFoundError(f"Failed to subscribe to book for '{symbol}'")
    return {"symbol": symbol, "subscribed": True}


@router.post("/book/{symbol}/unsubscribe")
def unsubscribe_book(symbol: str):
    mt5_service.initialize()
    result = mt5.market_book_release(symbol)
    if not result:
        raise MT5SymbolNotFoundError(f"Failed to unsubscribe from book for '{symbol}'")
    return {"symbol": symbol, "subscribed": False}


@router.get("/book/{symbol}")
def get_book(symbol: str):
    mt5_service.initialize()
    book = mt5.market_book_get(symbol)
    if book is None:
        raise HTTPException(status_code=404, detail="No book data")
    return [b._asdict() for b in book]


@router.get("/check/{symbol}")
def check_symbol(symbol: str):
    mt5_service.initialize()
    info = mt5.symbol_info(symbol)
    if not info:
        raise MT5SymbolNotFoundError(f"Symbol '{symbol}' not found")
    return {"visible": info.visible, "select": info.select, "name": info.name}
