import MetaTrader5 as mt5
from typing import Optional, List, Dict
from datetime import datetime, timedelta, timezone
from .connector import mt5_connector
from app.utils.time_sync import broker_datetime_from_utc, normalize_mt5_records

class HistoryService:
    def get_history_deals(self, from_date: Optional[datetime] = None, to_date: Optional[datetime] = None, position: Optional[int] = None) -> Optional[List[Dict]]:
        mt5_connector.initialize()
        if position and from_date is None and to_date is None:
            deals = mt5.history_deals_get(position=position)
        else:
            date_from = broker_datetime_from_utc(from_date) if from_date else datetime.now(timezone.utc) - timedelta(days=30)
            date_to = broker_datetime_from_utc(to_date) if to_date else datetime.now(timezone.utc)
            deals = mt5.history_deals_get(date_from, date_to)
        if deals is None: return []
        records = normalize_mt5_records([d._asdict() for d in deals])
        if position:
            records = [
                item for item in records
                if int(item.get("position_id") or item.get("position") or 0) == int(position)
            ]
        return records

    def get_history_orders(self, from_date: Optional[datetime] = None, to_date: Optional[datetime] = None, ticket: Optional[int] = None) -> Optional[List[Dict]]:
        mt5_connector.initialize()
        if ticket:
            orders = mt5.history_orders_get(ticket=ticket)
        else:
            date_from = broker_datetime_from_utc(from_date) if from_date else datetime.now(timezone.utc) - timedelta(days=30)
            date_to = broker_datetime_from_utc(to_date) if to_date else datetime.now(timezone.utc)
            orders = mt5.history_orders_get(date_from, date_to)
        if orders is None: return []
        return normalize_mt5_records([o._asdict() for o in orders])

history_service = HistoryService()
