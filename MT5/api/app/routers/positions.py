from fastapi import APIRouter
from app.services.mt5_service import mt5_service
from typing import Optional
from app.utils.exceptions import MT5SymbolNotFoundError

router = APIRouter(prefix="/positions", tags=["Positions"])


@router.get("/")
def get_positions(magic: Optional[int] = None, symbol: Optional[str] = None, ticket: Optional[int] = None):
    return mt5_service.get_positions(magic=magic, symbol=symbol, ticket=ticket)


@router.post("/close")
def close_position(ticket: int, volume: Optional[float] = None, type_filling: str = "FOK"):
    return mt5_service.close_position_details(ticket, volume=volume, type_filling=type_filling)


@router.post("/close_all")
def close_all_positions(order_type: str = "all", magic: Optional[int] = None, type_filling: str = "FOK"):
    return mt5_service.close_all_positions_details(order_type, magic, type_filling=type_filling)


@router.get("/by_symbol/{symbol}")
def get_positions_by_symbol(symbol: str):
    positions = mt5_service.get_positions(symbol=symbol)
    if not positions:
        raise MT5SymbolNotFoundError(f"No positions found for symbol '{symbol}'")
    return positions
