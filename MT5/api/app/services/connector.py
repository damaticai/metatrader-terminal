import logging
import threading

import MetaTrader5 as mt5

from app.utils.exceptions import MT5ConnectionError

logger = logging.getLogger(__name__)

MT5_PATH = "C:\\Metatrader-5\\terminal64.exe"
MT5_BUILD = 5836
MT5_IPC_TIMEOUT = -10005


def _mt5_error_message(action: str, error) -> str:
    try:
        code = int(error[0])
    except (IndexError, TypeError, ValueError):
        code = None
    if code == MT5_IPC_TIMEOUT:
        return (
            f"{action}: MT5 IPC timeout (-10005). The Python API could not "
            f"communicate with terminal64.exe. This image requires the pinned "
            f"MT5 build {MT5_BUILD}; recreate the container from the latest "
            f"published image and check the terminal process if the error persists. "
            f"raw_error={error}"
        )
    return f"{action}: {error}"


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
            success = mt5.initialize(MT5_PATH, portable=True, timeout=5000)
            if not success:
                self._last_error = mt5.last_error()
                raise MT5ConnectionError(
                    _mt5_error_message("MT5 terminal is not ready", self._last_error)
                )
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
                timeout=30000,
                portable=True,
            )
            if not success:
                self._initialized = False
                self._last_error = mt5.last_error()
                raise MT5ConnectionError(
                    _mt5_error_message("MT5 login failed", self._last_error)
                )
            account = mt5.account_info()
            if account is None or int(getattr(account, "login", 0) or 0) != int(login):
                self._last_error = mt5.last_error()
                raise MT5ConnectionError(
                    _mt5_error_message(
                        "MT5 login verification failed",
                        self._last_error,
                    )
                )
            self._initialized = True
            self._last_error = None
            return account

    def status(self) -> dict:
        terminal_info = None
        account_info = None
        error = None
        try:
            self.initialize()
        except MT5ConnectionError as exc:
            error = str(exc)
        if self._initialized:
            try:
                terminal_info = mt5.terminal_info()
                account_info = mt5.account_info()
            except Exception as exc:
                error = str(exc)
        terminal_ready = bool(self._initialized and terminal_info)
        logged_in = bool(account_info and getattr(account_info, "login", None))
        broker_connected = bool(
            terminal_info and getattr(terminal_info, "connected", False)
        )
        trade_allowed = bool(
            getattr(terminal_info, "trade_allowed", False)
        ) if terminal_info else False
        return {
            "api_ready": True,
            "terminal_ready": terminal_ready,
            "logged_in": logged_in,
            "login": getattr(account_info, "login", None) if logged_in else None,
            "server": getattr(account_info, "server", None) if logged_in else None,
            "trade_allowed": trade_allowed,
            "broker_connected": broker_connected,
            "trade_ready": bool(
                terminal_ready
                and logged_in
                and broker_connected
                and trade_allowed
            ),
            "last_error": error or self._last_error,
        }

    def get_terminal_info(self):
        self.initialize()
        return mt5.terminal_info()

    def get_account_info(self):
        self.initialize()
        return mt5.account_info()


mt5_connector = MT5Connector()
