from sqlmodel import Session, select
from app.models.trade import Trade, TradeClosePricesMutation
from datetime import datetime, timezone
from typing import Optional

from app.utils import helpers
from app.utils.time_sync import utc_datetime_from_epoch

def create_trade(session: Session, order_result: dict, symbol: str, capital: float, position_size_usd: float, 
                 leverage: float, commission: float, trade_type: str, broker: str, market_type: str, 
                 strategy: str, timeframe: str, volume: float, sl: Optional[float], tp: Optional[float]):
    entry_price = order_result.get('price_open') or order_result.get('open_price') or order_result.get('price', 0.0)
    
    # Calculate BE and Liq prices
    be_price, _ = helpers.get_price_at_pnl(0, entry_price, position_size_usd, leverage, trade_type.upper(), commission)
    liq_price, _ = helpers.get_price_at_pnl(-capital, entry_price, position_size_usd, leverage, trade_type.upper(), commission)

    entry_time = (
        utc_datetime_from_epoch(order_result.get("time_msc"))
        or utc_datetime_from_epoch(order_result.get("time"))
        or datetime.now(timezone.utc)
    )

    trade = Trade(
        transaction_broker_id=str(order_result.get('order', order_result.get('ticket', ''))),
        symbol=symbol,
        entry_time=entry_time,
        entry_price=entry_price,
        type=trade_type.upper(),
        position_size_usd=position_size_usd,
        capital=capital,
        leverage=leverage,
        order_volume=volume,
        liquidity_price=liq_price,
        break_even_price=be_price,
        order_commission=commission,
        strategy=strategy,
        broker=broker,
        market_type=market_type,
        timeframe=timeframe
    )
    session.add(trade)
    session.commit()
    session.refresh(trade)

    # Initial mutation
    mutate_trade(
        session=session,
        trade_id=trade.id,
        mutation_price=entry_price,
        new_sl=sl,
        new_tp=tp
    )

    return trade

def get_trade_by_ticket(session: Session, ticket: str) -> Optional[Trade]:
    statement = select(Trade).where(Trade.transaction_broker_id == ticket)
    return session.exec(statement).first()

def mutate_trade(session: Session, trade_id: int, mutation_price: float, new_sl: Optional[float], new_tp: Optional[float]):
    mutation = TradeClosePricesMutation(
        trade_id=trade_id,
        mutation_time=datetime.now(timezone.utc),
        mutation_price=mutation_price,
        new_sl_price=new_sl,
        new_tp_price=new_tp
    )
    session.add(mutation)
    session.commit()
    session.refresh(mutation)
    return mutation

def close_trade(session: Session, ticket: int, close_time: datetime, close_price: float, pnl: float, 
                pnl_excluding_commission: float, closing_reason: str, closed_deal: dict):
    statement = select(Trade).where(Trade.transaction_broker_id == str(ticket))
    trade = session.exec(statement).first()
    if not trade:
        return None
    
    trade.close_time = close_time
    trade.close_price = close_price
    trade.pnl = pnl
    trade.pnl_excluding_commission = pnl_excluding_commission
    trade.closing_reason = closing_reason
    # ... any other fields from closed_deal if needed
    
    session.add(trade)
    session.commit()
    session.refresh(trade)
    return trade
