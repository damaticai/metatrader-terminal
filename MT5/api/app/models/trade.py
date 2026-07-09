from datetime import datetime
from typing import Optional, List
from sqlmodel import SQLModel, Field, Relationship

class TradeBase(SQLModel):
    transaction_broker_id: str
    symbol: str
    entry_time: datetime
    entry_price: float
    type: str  # BUY, SELL
    position_size_usd: float
    capital: float
    leverage: float = 500.0
    order_volume: Optional[float] = None
    liquidity_price: float
    break_even_price: float
    order_commission: float
    close_time: Optional[datetime] = None
    close_price: Optional[float] = None
    pnl: Optional[float] = None
    pnl_excluding_commission: Optional[float] = None
    max_drawdown: Optional[float] = None
    max_profit: Optional[float] = None
    closing_reason: Optional[str] = Field(default=None)
    strategy: str
    broker: str
    market_type: str
    timeframe: str

    def to_dict(self):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}

class Trade(TradeBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    
    close_prices_mutations: List["TradeClosePricesMutation"] = Relationship(back_populates="trade")

class TradeClosePricesMutationBase(SQLModel):
    trade_id: int = Field(foreign_key="trade.id")
    mutation_time: datetime = Field(default_factory=datetime.utcnow)
    mutation_price: Optional[float] = None
    new_tp_price: Optional[float] = None
    new_sl_price: Optional[float] = None
    pnl_at_new_tp_price: Optional[float] = None
    pnl_at_new_sl_price: Optional[float] = None

class TradeClosePricesMutation(TradeClosePricesMutationBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    
    trade: Trade = Relationship(back_populates="close_prices_mutations")
