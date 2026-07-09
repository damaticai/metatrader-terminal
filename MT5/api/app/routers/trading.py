from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select
from typing import List, Optional
from app.db.database import get_session
from app.models.trade import Trade, TradeBase
from app.services.mt5_service import mt5_service
from app.models.trading import MarketOrderRequest, BatchMarketOrderRequest, ModifySLTPRequest
from app.utils.exceptions import MT5SymbolNotFoundError, MT5OrderError
from app.db import crud
from app.utils import helpers
import MetaTrader5 as mt5

router = APIRouter(prefix="/trading", tags=["Trading"])


def _matching_positions(request: MarketOrderRequest):
    if request.magic not in (None, 0):
        return mt5_service.get_positions(magic=request.magic)
    return mt5_service.get_positions(symbol=request.symbol)


def _best_position_for_order(request: MarketOrderRequest, positions: list[dict]):
    expected_type = mt5.ORDER_TYPE_BUY if request.order_type.upper() == "BUY" else mt5.ORDER_TYPE_SELL
    candidates = [
        pos for pos in positions
        if pos.get("symbol") == request.symbol
        and int(pos.get("type", -1)) == expected_type
        and abs(float(pos.get("volume", 0)) - float(request.volume)) < 1e-9
        and (request.magic in (None, 0) or int(pos.get("magic", 0)) == int(request.magic))
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda pos: int(pos.get("time_msc") or pos.get("time") or 0))


@router.get("/", response_model=List[Trade])
def get_trades(
    symbol: Optional[str] = None,
    trade_type: Optional[str] = None,
    is_open: Optional[bool] = None,
    session: Session = Depends(get_session)
):
    statement = select(Trade)
    if symbol:
        statement = statement.where(Trade.symbol == symbol.upper())
    if trade_type:
        statement = statement.where(Trade.type == trade_type.upper())
    if is_open is True:
        statement = statement.where(Trade.close_time == None)
    elif is_open is False:
        statement = statement.where(Trade.close_time != None)
    return session.exec(statement).all()


@router.post("/trades", response_model=Trade, status_code=status.HTTP_201_CREATED)
def create_trade(trade_data: TradeBase, session: Session = Depends(get_session)):
    trade = Trade.from_orm(trade_data)
    session.add(trade)
    session.commit()
    session.refresh(trade)
    return trade


@router.post("/order", status_code=status.HTTP_201_CREATED)
def send_order(
    request: MarketOrderRequest,
    session: Session = Depends(get_session)
):
    response = mt5_service.execute_market_order(request.dict())
    order_result = response.get("order_result") or response.get("result") or {}
    position = response.get("position")
    trade_order_result = dict(order_result)
    info = mt5_service.get_symbol_info(request.symbol)
    contract_size = info.get('trade_contract_size', 100000)
    leverage = 500
    execution_price = (
        trade_order_result.get("price_open")
        or (position or {}).get("price_open")
        or trade_order_result.get("price")
        or 0
    )
    order_size_usd = request.volume * contract_size * float(execution_price or 0)
    capital_used = order_size_usd / leverage
    commission = helpers.calculate_commission(order_size_usd, request.symbol)
    trade = crud.create_trade(
        session=session,
        order_result=trade_order_result,
        symbol=request.symbol,
        capital=capital_used,
        position_size_usd=order_size_usd,
        leverage=leverage,
        commission=commission,
        trade_type=request.order_type,
        broker="MT5",
        market_type="OTHER",
        strategy="MANUAL",
        timeframe="M1",
        volume=request.volume,
        sl=request.sl,
        tp=request.tp
    )
    return {
        **response,
        "trade": trade.to_dict(),
    }


@router.post("/orders/batch", status_code=status.HTTP_201_CREATED)
def send_orders_batch(
    request: BatchMarketOrderRequest,
    session: Session = Depends(get_session)
):
    items = []
    for order in request.orders:
        try:
            response = send_order(order, session)
            items.append({"success": True, "request": order.dict(), **response})
        except Exception as exc:
            if not request.continue_on_error:
                raise
            items.append({"success": False, "request": order.dict(), "error": str(exc)})
    return {"success": all(item.get("success") for item in items), "results": items, "count": len(items)}


@router.post("/modify-sl-tp")
def modify_sl_tp(
    request: ModifySLTPRequest,
    trade_id: int,
    session: Session = Depends(get_session)
):
    trade = session.get(Trade, trade_id)
    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found in database")

    ticket = int(trade.transaction_broker_id)
    result = mt5_service.modify_sl_tp(ticket, request.sl, request.tp)
    if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
        raise MT5OrderError(
            f"Modify SL/TP failed: {getattr(result, 'comment', 'Unknown error')}",
            code=getattr(result, 'retcode', None)
        )

    mutation = crud.mutate_trade(
        session=session,
        trade_id=trade.id,
        mutation_price=mt5_service.get_symbol_info(trade.symbol).get('bid', 0.0),
        new_sl=request.sl,
        new_tp=request.tp
    )
    return {"success": True, "mutation": mutation}


@router.get("/order_check/{symbol}")
def check_order(symbol: str):
    mt5_service.initialize()
    info = mt5.symbol_info(symbol)
    if not info:
        raise MT5SymbolNotFoundError(f"Symbol '{symbol}' not found")
    return info._asdict()
