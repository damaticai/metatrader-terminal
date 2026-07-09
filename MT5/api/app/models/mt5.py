from typing import Optional, List, Dict, Any
from pydantic import BaseModel
from app.utils.constants import RETCODE_DESCRIPTIONS
from datetime import datetime

class SymbolInfo(BaseModel):
    name: str
    path: str
    description: str
    volume_min: float
    volume_max: float
    volume_step: float
    digits: int
    spread: int
    trade_mode: int

class SymbolTick(BaseModel):
    time: int
    bid: float
    ask: float
    last: float
    volume: int
    time_msc: int
    flags: int

class Rate(BaseModel):
    time: datetime
    open: float
    high: float
    low: float
    close: float
    tick_volume: int
    spread: int
    real_volume: int

class MT5AccountInfo(BaseModel):
    login: int
    trade_mode: int
    leverage: int
    limit_orders: int
    margin_so_mode: int
    trade_allowed: bool
    trade_expert: bool
    margin_free: float
    margin_level: float
    balance: float
    equity: float
    profit: float
    margin: float
    currency: str
    company: str
    server: str

class MT5SymbolInfo(BaseModel):
    name: str
    digits: int
    spread: int
    trade_contract_size: float
    trade_tick_value: float
    trade_tick_size: float
    volume_min: float
    volume_max: float
    volume_step: float
    point: float
    bid: float
    ask: float
