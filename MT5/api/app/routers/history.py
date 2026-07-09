from fastapi import APIRouter, HTTPException
from app.services.mt5_service import mt5_service
from typing import Optional
from datetime import datetime
import MetaTrader5 as mt5
from app.utils.time_sync import normalize_mt5_records

router = APIRouter(prefix="/history", tags=["History"])


@router.get("/deals")
def get_history_deals(from_date: Optional[datetime] = None, to_date: Optional[datetime] = None, position: Optional[int] = None):
    return mt5_service.get_history_deals(from_date, to_date, position)


@router.get("/orders")
def get_history_orders(from_date: Optional[datetime] = None, to_date: Optional[datetime] = None, ticket: Optional[int] = None):
    return mt5_service.get_history_orders(from_date, to_date, ticket)


@router.get("/order_by_ticket/{ticket}")
def get_order_by_ticket(ticket: int):
    mt5_service.initialize()
    orders = mt5.history_orders_get(ticket=ticket)
    if not orders:
        raise HTTPException(status_code=404, detail=f"Order {ticket} not found")
    return normalize_mt5_records([o._asdict() for o in orders])
