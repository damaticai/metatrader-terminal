import logging
import threading

import MetaTrader5 as mt5

from app.utils.exceptions import MT5ConnectionError

logger = logging.getLogger(__name__)

MT5_PATH = "C:\\Metatrader-5\\terminal64.exe"


class MT5Connector:
    """MT5 IPC and account-login manager.

    API health is independent from MT5 login state. initialize() only connects
    Python to a running terminal process; login() switches the account through
    the MT5 API without restarting or recreating the container.
    """

    def __init__(self):
        self._initialized = False
        self._lock = threading.Lock()
        self._last_error = None

    def initialize(self) -> bool:
        if self._initialized:
            return True
        with self._lock:
            if self._initialized:
                return True
            success = mt5.initialize(MT5_PATH, portable=True)
            if not success:
                self._last_error = mt5.last_error()
                raise MT5ConnectionError(f"MT5 terminal is not ready: {self._last_error}")
            self._initialized = True
            self._last_error = None
            return True

    def login(self, login: int, password: str, server: str):
        with self._lock:
            success = mt5.initialize(
                MT5_PATH,
                login=int(login),
                password=password,
                server=server,
                portable=True,
            )
            if not success:
                self._initialized = False
                self._last_error = mt5.last_error()
                raise MT5ConnectionError(f"MT5 login failed: {self._last_error}")
            account = mt5.account_info()
            if account is None or int(getattr(account, "login", 0) or 0) != int(login):
                self._last_error = mt5.last_error()
                raise MT5ConnectionError(f"MT5 login verification failed: {self._last_error}")
            self._initialized = True
            self._last_error = None
            return account

    def status(self) -> dict:
        terminal_info = None
        account_info = None
        error = None
        try:
            self.initialize()
            terminal_info = mt5.terminal_info()
            account_info = mt5.account_info()
        except Exception as exc:
            error = str(exc)
        logged_in = bool(account_info and getattr(account_info, "login", None))
        return {
            "api_ready": True,
            "terminal_ready": bool(self._initialized and terminal_info),
            "logged_in": logged_in,
            "login": getattr(account_info, "login", None) if logged_in else None,
            "server": getattr(account_info, "server", None) if logged_in else None,
            "trade_allowed": bool(getattr(terminal_info, "trade_allowed", False)) if terminal_info else False,
            "last_error": error or self._last_error,
        }

    def get_terminal_info(self):
        self.initialize()
        return mt5.terminal_info()

    def get_account_info(self):
        self.initialize()
        return mt5.account_info()


mt5_connector = MT5Connector()
