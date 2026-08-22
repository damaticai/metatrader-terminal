import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any
import MetaTrader5 as mt5
from .connector import mt5_connector
from .market_data import market_data_service
from app.utils.exceptions import MT5BaseException, MT5OrderError, MT5SymbolNotFoundError
from app.utils.time_sync import broker_datetime_from_utc, normalize_mt5_records

logger = logging.getLogger(__name__)


# A normal new market order on the Hedging accounts used by this service has
# one opening order and one position. MT5 returns the opening order ticket in
# the synchronous order_send result, while positions_get can lag behind it.
# Other accepted result modes need history confirmation instead.
HISTORY_CONFIRMATION_DELAYS = (0.0, 0.05, 0.10, 0.20, 0.40)

class TradeService:
    @staticmethod
    def _retcode(result) -> int:
        try:
            return int(getattr(result, "retcode", 0) or 0)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _accepted_retcodes() -> set:
        return {
            int(getattr(mt5, "TRADE_RETCODE_PLACED", 10008)),
            int(getattr(mt5, "TRADE_RETCODE_DONE", 10009)),
            int(getattr(mt5, "TRADE_RETCODE_DONE_PARTIAL", 10010)),
        }

    @staticmethod
    def _empty_order_error(action: str) -> MT5OrderError:
        try:
            last_error = mt5.last_error()
        except Exception:
            last_error = None
        try:
            last_code = int(last_error[0])
        except (IndexError, TypeError, ValueError):
            last_code = None
        detail = f"{action}: empty response; last_error={last_error!r}"
        lowered = detail.casefold()
        if last_code == -2 and "comment" in lowered:
            code = -2
        elif "invalid comment" in lowered:
            code = -2
        elif "invalid argument" in lowered or "invalid parameter" in lowered:
            code = 10013
        elif last_code and 10004 <= last_code <= 10046:
            code = last_code
        else:
            code = "EMPTY_RESPONSE"
        return MT5OrderError(
            f"{action}: empty response",
            code=code,
            detail=detail,
        )

    def _decorate_order_result(
        self,
        result,
        *,
        requested_volume: float,
    ) -> Dict[str, Any]:
        value = self._result_to_dict(result)
        retcode = self._retcode(result)
        if retcode == int(getattr(mt5, "TRADE_RETCODE_DONE_PARTIAL", 10010)):
            actual_volume = float(
                value.get("volume")
                or getattr(result, "volume", 0)
                or 0
            )
            value["partial_fill"] = True
            value["requested_volume"] = float(requested_volume)
            value["actual_volume"] = actual_volume
            value["warning"] = "订单部分成交，请检查实际成交手数"
        return value

    def _result_to_dict(self, result) -> Dict:
        if result is None:
            return {}
        if hasattr(result, "_asdict"):
            return result._asdict()
        if isinstance(result, dict):
            return result
        return {}

    def _positions_to_dicts(self, positions) -> List[Dict]:
        if positions is None:
            return []
        raw_positions = [p._asdict() if hasattr(p, "_asdict") else dict(p) for p in positions]
        return normalize_mt5_records(raw_positions)

    def _filter_positions(self, positions: List[Dict], magic: int = None, symbol: str = None, ticket: int = None) -> List[Dict]:
        filtered = positions
        if magic is not None:
            filtered = [p for p in filtered if int(p.get("magic", 0)) == int(magic)]
        if symbol:
            filtered = [p for p in filtered if p.get("symbol") == symbol]
        if ticket is not None:
            filtered = [p for p in filtered if int(p.get("ticket", 0)) == int(ticket)]
        return filtered

    def _position_ticket(self, position: Dict[str, Any]) -> str:
        value = position.get("ticket") or position.get("identifier") or position.get("position") or position.get("order")
        return str(value) if value not in (None, "") else ""

    @staticmethod
    def _order_ticket(order_result: Dict[str, Any]) -> str:
        value = order_result.get("order") or order_result.get("order_ticket")
        try:
            return str(int(value)) if int(value) > 0 else ""
        except (TypeError, ValueError):
            return ""

    def _history_position_for_order(self, order_ticket: str) -> tuple[str, Dict[str, Any]]:
        """Resolve a position ticket from the deals created by one order.

        This is deliberately a fallback. In the normal Hedging-account market
        order path, order_send's ``order`` is the position ticket and avoids a
        cache-dependent confirmation. For partial or otherwise non-standard
        fills, DEAL_POSITION_ID from history is the authoritative mapping.
        """
        if not order_ticket:
            return "", {}
        history_deals_get = getattr(mt5, "history_deals_get", None)
        if not callable(history_deals_get):
            return "", {}
        for delay in HISTORY_CONFIRMATION_DELAYS:
            if delay:
                time.sleep(delay)
            try:
                raw_deals = history_deals_get(ticket=int(order_ticket))
            except Exception as exc:
                logger.debug("history lookup for opening order %s failed: %s", order_ticket, exc)
                continue
            if raw_deals is None:
                continue
            deals = normalize_mt5_records([
                deal._asdict() if hasattr(deal, "_asdict") else dict(deal)
                for deal in raw_deals
            ])
            positions: dict[str, Dict[str, Any]] = {}
            for deal in deals:
                deal_order_ticket = str(deal.get("order") or deal.get("order_ticket") or "")
                position_ticket = str(
                    deal.get("position_id") or deal.get("position_ticket") or deal.get("position") or ""
                )
                if deal_order_ticket != order_ticket or not position_ticket:
                    continue
                entry = self._deal_entry(deal).upper()
                if entry and entry not in {"0", "IN", "ENTRY_IN", "DEAL_ENTRY_IN"}:
                    continue
                positions[position_ticket] = deal
            if len(positions) == 1:
                ticket, deal = next(iter(positions.items()))
                return ticket, deal
            if len(positions) > 1:
                logger.warning(
                    "opening order %s produced multiple position tickets: %s",
                    order_ticket,
                    sorted(positions),
                )
                return "", {}
        return "", {}

    def _positions_for_order(self, symbol: str, magic: int = 0) -> List[Dict]:
        if magic not in (None, 0):
            return self.get_positions(magic=magic)
        return self.get_positions(symbol=symbol)

    def _best_open_position(
        self,
        positions: List[Dict],
        symbol: str,
        volume: float,
        order_type: str,
        magic: int = 0,
        before_tickets: Optional[set] = None,
    ) -> Optional[Dict]:
        expected_type = mt5.ORDER_TYPE_BUY if order_type.upper() == "BUY" else mt5.ORDER_TYPE_SELL
        before_tickets = before_tickets or set()
        candidates = []
        for pos in positions:
            ticket = self._position_ticket(pos)
            if ticket and ticket in before_tickets:
                continue
            if pos.get("symbol") != symbol:
                continue
            if int(pos.get("type", -1)) != expected_type:
                continue
            if abs(float(pos.get("volume", 0)) - float(volume)) > 1e-9:
                continue
            if magic not in (None, 0) and int(pos.get("magic", 0)) != int(magic):
                continue
            candidates.append(pos)
        if not candidates:
            return None
        return max(candidates, key=lambda pos: int(pos.get("time_msc") or pos.get("time") or 0))

    def _history_deals_for_position(self, position_ticket: int, days: int = 3) -> List[Dict]:
        deals = mt5.history_deals_get(position=int(position_ticket))
        if deals is None:
            return []
        return normalize_mt5_records([deal._asdict() for deal in deals])

    def _deal_entry(self, deal: Dict[str, Any]) -> str:
        return str(deal.get("entry") if deal.get("entry") is not None else deal.get("entry_type") or deal.get("entryType") or "").strip()

    def _close_summary(
        self,
        ticket: int,
        close_result: Dict[str, Any],
        closed_position: Dict[str, Any],
        deals: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        exit_deals = [
            deal for deal in deals
            if self._deal_entry(deal) not in ("", "0", "IN", "ENTRY_IN", "DEAL_ENTRY_IN")
        ]
        exit_deals.sort(key=lambda deal: int(deal.get("time_msc") or deal.get("time") or 0))
        last_exit = exit_deals[-1] if exit_deals else {}
        profit = 0.0
        volume = 0.0
        for deal in exit_deals:
            profit += float(deal.get("profit") or 0)
            profit += float(deal.get("swap") or 0)
            profit += float(deal.get("commission") or 0)
            profit += float(deal.get("fee") or 0)
            volume += float(deal.get("volume") or 0)
        return {
            "ticket": str(ticket),
            "symbol": closed_position.get("symbol") or last_exit.get("symbol") or "",
            "side": closed_position.get("type"),
            "volume": volume or close_result.get("volume") or closed_position.get("volume"),
            "open_price": closed_position.get("price_open"),
            "open_time": closed_position.get("time"),
            "open_time_msc": closed_position.get("time_msc"),
            "close_price": last_exit.get("price") or close_result.get("price"),
            "close_time": last_exit.get("time"),
            "close_time_msc": last_exit.get("time_msc"),
            "profit": profit if exit_deals else closed_position.get("profit", 0),
        }

    def execute_market_order(self, order: Dict[str, Any]) -> Dict[str, Any]:
        before_positions = self._positions_for_order(order["symbol"], int(order.get("magic") or 0))
        before_tickets = {self._position_ticket(pos) for pos in before_positions}
        result = self.send_market_order(**order)
        order_result = self._decorate_order_result(
            result,
            requested_volume=float(order["volume"]),
        )
        matched_volume = float(
            order_result.get("actual_volume")
            or order["volume"]
        )
        order_ticket = self._order_ticket(order_result)
        positions_after = self._positions_for_order(order["symbol"], int(order.get("magic") or 0))
        position = self._best_open_position(
            positions_after,
            order["symbol"],
            matched_volume,
            str(order["order_type"]),
            int(order.get("magic") or 0),
            before_tickets,
        )
        position_ticket = ""
        confirmation_source = ""

        # This service only uses this shortcut for a fully completed new
        # market order. In the deployed Hedging-account workflow, MT5's
        # opening order ticket is the position ticket. Crucially, this does
        # not depend on the asynchronous positions_get cache.
        if (
            self._retcode(result) == int(getattr(mt5, "TRADE_RETCODE_DONE", 10009))
            and order_ticket
        ):
            position_ticket = order_ticket
            confirmation_source = "order_ticket"
        elif position:
            position_ticket = self._position_ticket(position)
            confirmation_source = "position_snapshot"
        elif order_ticket:
            position_ticket, history_deal = self._history_position_for_order(order_ticket)
            if position_ticket:
                confirmation_source = "history_deal"
                position = {
                    "ticket": position_ticket,
                    "identifier": position_ticket,
                    "symbol": history_deal.get("symbol") or order.get("symbol"),
                    "magic": history_deal.get("magic") or order.get("magic"),
                    "volume": history_deal.get("volume") or matched_volume,
                    "price_open": history_deal.get("price") or order_result.get("price"),
                    "time": history_deal.get("time") or order_result.get("time"),
                    "time_msc": history_deal.get("time_msc") or order_result.get("time_msc"),
                }
        if position and position.get("ticket"):
            position_ticket = position_ticket or self._position_ticket(position)
            order_result["price_open"] = position.get("price_open")
            order_result["time"] = position.get("time")
            order_result["time_msc"] = position.get("time_msc")
        if position_ticket:
            order_result["position"] = position_ticket
            order_result["ticket"] = position_ticket
        response = {
            "success": True,
            "request": dict(order),
            "result": order_result,
            "order_result": order_result,
            "position": position,
            "position_ticket": position_ticket,
            "order_ticket": order_ticket,
            "confirmation_source": confirmation_source,
            "positions_before": before_positions,
            "positions_after": positions_after,
            "summary": {
                "ticket": position_ticket,
                "position_ticket": position_ticket,
                "order_ticket": order_ticket,
                "symbol": order.get("symbol"),
                "side": order.get("order_type"),
                "volume": order_result.get("actual_volume") or order.get("volume"),
                "open_price": position.get("price_open") if position else order_result.get("price"),
                "open_time": position.get("time") if position else order_result.get("time"),
                "open_time_msc": position.get("time_msc") if position else order_result.get("time_msc"),
            },
        }
        if order_result.get("partial_fill"):
            response["partial_fill"] = True
            response["warning"] = order_result["warning"]
            response["requested_volume"] = order_result.get("requested_volume")
            response["actual_volume"] = order_result.get("actual_volume")
        return response

    def close_position_details(self, ticket: int, volume: float = None, deviation: int = 20,
                               comment: str = '', type_filling: str = 'FOK') -> Dict[str, Any]:
        before_positions = self.get_positions(ticket=int(ticket))
        if not before_positions:
            return {
                "success": True,
                "idempotent": True,
                "verified": True,
                "request": {
                    "ticket": ticket,
                    "volume": volume,
                    "deviation": deviation,
                    "comment": comment,
                    "type_filling": type_filling,
                },
                "result": {
                    "ticket": str(ticket),
                    "position": str(ticket),
                    "idempotent": True,
                },
                "summary": {"ticket": str(ticket), "position_ticket": str(ticket)},
                "positions_before": [],
                "positions_after": self.get_positions(),
            }
        closed_position = before_positions[0] if before_positions else {}
        result = self.close_position(ticket, volume=volume, deviation=deviation, comment=comment, type_filling=type_filling)
        close_result = self._decorate_order_result(
            result,
            requested_volume=float(
                volume if volume is not None else closed_position.get("volume") or 0
            ),
        )
        deals = self._history_deals_for_position(int(ticket))
        positions_after = self.get_positions(magic=closed_position.get("magic")) if closed_position else self.get_positions()
        response = {
            "success": True,
            "request": {"ticket": ticket, "volume": volume, "deviation": deviation, "comment": comment, "type_filling": type_filling},
            "result": close_result,
            "close_result": close_result,
            "closed_position": closed_position,
            "deals": deals,
            "close_deals": deals,
            "summary": self._close_summary(int(ticket), close_result, closed_position, deals),
            "positions_before": before_positions,
            "positions_after": positions_after,
        }
        if close_result.get("partial_fill"):
            response["partial_fill"] = True
            response["warning"] = close_result["warning"]
            response["actual_volume"] = close_result.get("actual_volume")
        return response

    def send_market_order(self, symbol: str, volume: float, order_type: str, sl: float, tp: float = None,
                          deviation: int = 20, comment: str = '', magic: int = 0, type_filling: str = 'FOK'):
        mt5_connector.initialize()

        order_type_map = {
            'BUY': mt5.ORDER_TYPE_BUY,
            'SELL': mt5.ORDER_TYPE_SELL
        }

        filling_map = {
            'IOC': mt5.ORDER_FILLING_IOC,
            'FOK': mt5.ORDER_FILLING_FOK,
            'RETURN': mt5.ORDER_FILLING_RETURN
        }

        market_data_service.ensure_symbol_selected(symbol)
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            raise MT5SymbolNotFoundError(f"Failed to get tick for {symbol}")
            
        # Correctly mapping price for long/short
        price = tick.ask if order_type.upper() == 'BUY' else tick.bid
        
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": float(volume),
            "type": order_type_map.get(order_type.upper()),
            "price": price,
            "deviation": int(deviation),
            "magic": int(magic),
            "comment": comment,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": filling_map.get(type_filling.upper(), mt5.ORDER_FILLING_FOK),
        }
        
        if sl is not None and float(sl) != 0:
            request["sl"] = float(sl)
        if tp is not None:
            request["tp"] = float(tp)
            
        result = mt5.order_send(request)
        if result is None:
            raise self._empty_order_error("Order failed")
        if self._retcode(result) not in self._accepted_retcodes():
            raise MT5OrderError(f"Order failed: {result.comment}", code=result.retcode)
        return result

    def send_pending_order(self, symbol: str, volume: float, order_type: str, price: float,
                          sl: float = None, tp: float = None, deviation: int = 20,
                          comment: str = '', magic: int = 0, type_filling: str = 'FOK',
                          type_time: str = 'GTC', expiration: datetime = None):
        mt5_connector.initialize()

        order_type_map = {
            'BUY_LIMIT': mt5.ORDER_TYPE_BUY_LIMIT,
            'SELL_LIMIT': mt5.ORDER_TYPE_SELL_LIMIT,
            'BUY_STOP': mt5.ORDER_TYPE_BUY_STOP,
            'SELL_STOP': mt5.ORDER_TYPE_SELL_STOP,
            'BUY_STOP_LIMIT': mt5.ORDER_TYPE_BUY_STOP_LIMIT,
            'SELL_STOP_LIMIT': mt5.ORDER_TYPE_SELL_STOP_LIMIT,
        }

        filling_map = {
            'IOC': mt5.ORDER_FILLING_IOC,
            'FOK': mt5.ORDER_FILLING_FOK,
            'RETURN': mt5.ORDER_FILLING_RETURN,
        }

        time_map = {
            'GTC': mt5.ORDER_TIME_GTC,
            'DAY': mt5.ORDER_TIME_DAY,
            'SPECIFIED': mt5.ORDER_TIME_SPECIFIED,
            'SPECIFIED_DAY': mt5.ORDER_TIME_SPECIFIED_DAY,
        }

        mt5_type = order_type_map.get(order_type.upper())
        if mt5_type is None:
            raise MT5OrderError(f"Invalid pending order type: {order_type}")

        market_data_service.ensure_symbol_selected(symbol)

        request = {
            "action": mt5.TRADE_ACTION_PENDING,
            "symbol": symbol,
            "volume": float(volume),
            "type": mt5_type,
            "price": float(price),
            "deviation": int(deviation),
            "magic": int(magic),
            "comment": comment,
            "type_time": time_map.get(type_time.upper(), mt5.ORDER_TIME_GTC),
            "type_filling": filling_map.get(type_filling.upper(), mt5.ORDER_FILLING_FOK),
        }

        if sl is not None:
            request["sl"] = float(sl)
        if tp is not None:
            request["tp"] = float(tp)
        if expiration is not None:
            request["expiration"] = int(expiration.timestamp())

        result = mt5.order_send(request)
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            raise MT5OrderError(f"Pending order failed: {result.comment}", code=result.retcode)
        return result

    def modify_pending_order(self, ticket: int, price: float, sl: float = None, tp: float = None,
                            type_time: str = None, expiration: datetime = None):
        mt5_connector.initialize()

        orders = mt5.orders_get(ticket=ticket)
        if not orders:
            raise MT5OrderError(f"Pending order {ticket} not found")

        order = orders[0]

        time_map = {
            'GTC': mt5.ORDER_TIME_GTC,
            'DAY': mt5.ORDER_TIME_DAY,
            'SPECIFIED': mt5.ORDER_TIME_SPECIFIED,
            'SPECIFIED_DAY': mt5.ORDER_TIME_SPECIFIED_DAY,
        }

        request = {
            "action": mt5.TRADE_ACTION_MODIFY,
            "order": ticket,
            "symbol": order.symbol,
            "price": float(price),
            "type_time": time_map.get(type_time.upper(), order.type_time) if type_time else order.type_time,
        }

        if sl is not None:
            request["sl"] = float(sl)
        else:
            request["sl"] = float(order.sl)
        if tp is not None:
            request["tp"] = float(tp)
        else:
            request["tp"] = float(order.tp)
        if expiration is not None:
            request["expiration"] = int(expiration.timestamp())

        result = mt5.order_send(request)
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            raise MT5OrderError(f"Modify pending order failed: {result.comment}", code=result.retcode)
        return result

    def cancel_order(self, ticket: int):
        mt5_connector.initialize()

        request = {
            "action": mt5.TRADE_ACTION_REMOVE,
            "order": ticket,
        }

        result = mt5.order_send(request)
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            raise MT5OrderError(f"Cancel order failed: {result.comment}", code=result.retcode)
        return result

    def modify_sl_tp(self, ticket: int, sl: float, tp: float = None):
        mt5_connector.initialize()
        
        position = mt5.positions_get(ticket=ticket)
        if not position:
            raise MT5OrderError(f"Position {ticket} not found")
            
        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "symbol": position[0].symbol,
            "position": ticket,
            "sl": float(sl),
        }
        
        if tp is not None:
            request["tp"] = float(tp)
        else:
            request["tp"] = float(position[0].tp)
            
        result = mt5.order_send(request)
        return result

    def close_position(self, ticket: int, volume: float = None, deviation: int = 20,
                       comment: str = '', type_filling: str = 'FOK'):
        mt5_connector.initialize()

        positions = mt5.positions_get(ticket=ticket)
        if not positions:
            raise MT5OrderError(f"Position {ticket} not found", code=10036)

        pos = positions[0]
        close_volume = float(volume) if volume is not None else pos.volume
        order_type = mt5.ORDER_TYPE_SELL if pos.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
        market_data_service.ensure_symbol_selected(pos.symbol)
        tick = mt5.symbol_info_tick(pos.symbol)
        if tick is None:
            raise MT5SymbolNotFoundError(
                f"Failed to get tick for {pos.symbol}",
                code="MT5_SYMBOL_NOT_FOUND",
            )
        price = tick.bid if pos.type == mt5.ORDER_TYPE_BUY else tick.ask

        filling_map = {
            'IOC': mt5.ORDER_FILLING_IOC,
            'FOK': mt5.ORDER_FILLING_FOK,
            'RETURN': mt5.ORDER_FILLING_RETURN
        }

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "position": ticket,
            "symbol": pos.symbol,
            "volume": close_volume,
            "type": order_type,
            "price": price,
            "deviation": deviation,
            "magic": pos.magic,
            "comment": comment,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": filling_map.get(type_filling.upper(), mt5.ORDER_FILLING_FOK),
        }

        result = mt5.order_send(request)
        if result is None:
            raise self._empty_order_error("Close failed")
        if self._retcode(result) not in self._accepted_retcodes():
            raise MT5OrderError(f"Close failed: {result.comment}", code=result.retcode)
        return result

    def get_positions(self, magic: int = None, symbol: str = None, ticket: int = None) -> List[Dict]:
        mt5_connector.initialize()
        if ticket is not None:
            positions = mt5.positions_get(ticket=int(ticket))
        elif symbol:
            positions = mt5.positions_get(symbol=symbol)
        else:
            positions = mt5.positions_get()
        return self._filter_positions(self._positions_to_dicts(positions), magic=magic, symbol=symbol, ticket=ticket)

    def close_all_positions(self, order_type: str = "all", magic: Optional[int] = None, type_filling: str = 'FOK') -> List:
        mt5_connector.initialize()
        positions = self.get_positions(magic)
        results = []
        if not positions: return []

        for pos in positions:
            if order_type.upper() == 'BUY' and pos['type'] != mt5.ORDER_TYPE_BUY: continue
            if order_type.upper() == 'SELL' and pos['type'] != mt5.ORDER_TYPE_SELL: continue

            try:
                res = self.close_position(pos['ticket'], type_filling=type_filling)
                if res: results.append(res)
            except MT5OrderError as e:
                logger.error(f"Failed to close position {pos['ticket']}: {e}")
        return results

    def close_all_positions_details(self, order_type: str = "all", magic: Optional[int] = None, type_filling: str = 'FOK') -> Dict[str, Any]:
        mt5_connector.initialize()
        before_positions = self.get_positions(magic)
        closed = []
        errors = []
        for pos in before_positions:
            if order_type.upper() == 'BUY' and pos['type'] != mt5.ORDER_TYPE_BUY:
                continue
            if order_type.upper() == 'SELL' and pos['type'] != mt5.ORDER_TYPE_SELL:
                continue
            ticket = pos.get("ticket")
            try:
                closed.append(self.close_position_details(int(ticket), type_filling=type_filling))
            except MT5BaseException as e:
                logger.error(f"Failed to close position {ticket}: {e}")
                errors.append({
                    "ticket": ticket,
                    "retcode": str(e.code),
                    "error_code": str(e.code),
                    "exception_type": type(e).__name__,
                    "error": str(e),
                    "raw_message": str(e),
                    "diagnostic_detail": str(getattr(e, "detail", "") or e),
                })
        after_positions = self.get_positions(magic)
        return {
            "success": not errors,
            "message": f"Closed {len(closed)} positions",
            "closed": closed,
            "results": [item.get("result", {}) for item in closed],
            "errors": errors,
            "positions_before": before_positions,
            "positions_after": after_positions,
            "closed_count": len(closed),
            "failed_count": len(errors),
            "partial_fill": any(item.get("partial_fill") for item in closed),
            "warnings": [
                item.get("warning")
                for item in closed
                if item.get("warning")
            ],
        }

    def get_orders(self, symbol: str = None, ticket: int = None) -> List[Dict]:
        mt5_connector.initialize()
        if ticket:
            orders = mt5.orders_get(ticket=ticket)
        elif symbol:
            orders = mt5.orders_get(symbol=symbol)
        else:
            orders = mt5.orders_get()
        if orders is None: return []
        return [o._asdict() for o in orders]

    def get_orders_total(self) -> int:
        mt5_connector.initialize()
        return mt5.orders_total()

    def order_calc_margin(self, action: str, symbol: str, volume: float, price: float) -> Optional[float]:
        mt5_connector.initialize()
        action_map = {
            'BUY': mt5.ORDER_TYPE_BUY,
            'SELL': mt5.ORDER_TYPE_SELL,
        }
        market_data_service.ensure_symbol_selected(symbol)
        result = mt5.order_calc_margin(action_map.get(action.upper(), mt5.ORDER_TYPE_BUY), symbol, volume, price)
        return result

    def order_calc_profit(self, action: str, symbol: str, volume: float, price_open: float, price_close: float) -> Optional[float]:
        mt5_connector.initialize()
        action_map = {
            'BUY': mt5.ORDER_TYPE_BUY,
            'SELL': mt5.ORDER_TYPE_SELL,
        }
        market_data_service.ensure_symbol_selected(symbol)
        result = mt5.order_calc_profit(action_map.get(action.upper(), mt5.ORDER_TYPE_BUY), symbol, volume, price_open, price_close)
        return result

trade_service = TradeService()
