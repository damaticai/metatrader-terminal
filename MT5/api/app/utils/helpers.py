import logging
import traceback
import pandas as pd
from datetime import datetime, timedelta
import pytz
from typing import Tuple, Dict, List, Optional
from app.services.trade import trade_service
from app.services.market_data import market_data_service
from app.utils.constants import METALS, OILS, CURRENCY_PAIRS, CRYPTOCURRENCIES

logger = logging.getLogger(__name__)
TIMEZONE = pytz.UTC
EPSILON = 1e-4

def have_open_positions_in_symbol(symbol: str) -> bool:
    """Check if there are any open positions for a given symbol."""
    try:
        positions = trade_service.get_positions()
        if not positions:
            return False
        
        df = pd.DataFrame(positions)
        if df.empty:
            return False
            
        return symbol in df['symbol'].values
    except Exception as e:
        logger.error(f"Error in have_open_positions_in_symbol: {e}\n{traceback.format_exc()}")
        return False

def is_market_open(symbol: str) -> bool:
    """Check if the market is currently open for a given symbol."""
    if symbol in CRYPTOCURRENCIES:
        return True
    
    info = market_data_service.get_symbol_info(symbol)
    if info:
        tick_time = datetime.fromtimestamp(info['time'], tz=TIMEZONE)
        current_time = datetime.now(TIMEZONE)
        time_difference = current_time - tick_time

        if time_difference > timedelta(minutes=5):
            return False
        return True
    return False

def get_price_at_pnl(desired_pnl: float, entry_price: float, order_size_usd: float, leverage: float, type: str, commission: float) -> Tuple[float, float]:
    """Calculate the target price required to reach a specific PnL."""
    if type == 'BUY':
        price_including_commission = entry_price * (1 + (desired_pnl + commission) / order_size_usd)
        price_excluding_commission = entry_price * (1 + desired_pnl / order_size_usd)
    elif type == 'SELL':
        price_including_commission = entry_price * (1 - (desired_pnl + commission) / order_size_usd)
        price_excluding_commission = entry_price * (1 - desired_pnl / order_size_usd)
    else:
        raise ValueError(f"Unknown trade type: {type}")
    return price_including_commission, price_excluding_commission

def get_pnl_at_price(current_price: float, entry_price: float, order_size_usd: float, leverage: float, type: str, commission: float) -> Tuple[float, float]:
    """Calculate the PnL at a specific price."""
    if type == 'BUY':
        price_change = (current_price - entry_price) / entry_price
    elif type == 'SELL':
        price_change = (entry_price - current_price) / entry_price
    else:
        raise ValueError(f"Unknown trade type: {type}")
    
    pnl_including_commission = order_size_usd * price_change
    pnl_excluding_commission = pnl_including_commission - commission
    return pnl_including_commission, pnl_excluding_commission

def convert_lots_to_usd(symbol: str, lots: float, price_open: float) -> float:
    """Convert volume in lots to equivalent USD value."""
    symbol_info = market_data_service.get_symbol_info(symbol)
    if not symbol_info:
        raise ValueError(f"Symbol {symbol} not found")
    
    contract_size = symbol_info.get('trade_contract_size', 100000)
    return lots * contract_size * price_open

def convert_usd_to_lots(symbol: str, usd_amount: float, order_type: str) -> float:
    """Convert a USD amount into equivalent MetaTrader 5 lots."""
    symbol_info = market_data_service.get_symbol_info(symbol)
    if not symbol_info:
        raise ValueError(f"Symbol {symbol} not found")
    
    price = symbol_info['ask'] if order_type == 'BUY' else symbol_info['bid']
    contract_size = symbol_info.get('trade_contract_size', 100000)
    
    lots = usd_amount / (contract_size * price)
    lot_step = symbol_info.get('volume_step', 0.01)
    lots = round(lots / lot_step) * lot_step
    return lots

def calculate_commission(order_size_usd: float, pair: str) -> float:
    """Calculate the estimated commission for a trade based on its asset class."""
    if pair in CRYPTOCURRENCIES:
        commission_rate = 0.0005
    elif pair in OILS or pair in METALS or pair in CURRENCY_PAIRS:
        commission_rate = 0.00025
    else:
        # Default fallback
        commission_rate = 0.00025
    
    return order_size_usd * commission_rate
