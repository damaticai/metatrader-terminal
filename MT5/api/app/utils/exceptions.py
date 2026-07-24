class MT5BaseException(Exception):
    """Base exception for all MT5 errors."""
    status_code: int = 500
    default_code = "MT5_ERROR"

    def __init__(self, message: str, code=None, detail: str = ""):
        self.message = message
        self.code = code if code not in (None, "") else self.default_code
        self.detail = detail or message
        super().__init__(self.message)

class MT5ConnectionError(MT5BaseException):
    """MT5 terminal is not connected or IPC failed."""
    status_code = 503
    default_code = "MT5_CONNECTION_ERROR"

class MT5OrderError(MT5BaseException):
    """Order placement, modification, or cancellation failed."""
    status_code = 400
    default_code = "MT5_ORDER_ERROR"

class MT5SymbolNotFoundError(MT5BaseException):
    """Requested symbol does not exist or has no data."""
    status_code = 404
    default_code = "MT5_SYMBOL_NOT_FOUND"

class MT5RateLimitError(MT5BaseException):
    """Too many requests to MT5 terminal."""
    status_code = 429
    default_code = "MT5_RATE_LIMIT"
