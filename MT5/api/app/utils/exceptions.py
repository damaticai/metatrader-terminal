class MT5BaseException(Exception):
    """Base exception for all MT5 errors."""
    status_code: int = 500

    def __init__(self, message: str, code: int = None):
        self.message = message
        self.code = code
        super().__init__(self.message)

class MT5ConnectionError(MT5BaseException):
    """MT5 terminal is not connected or IPC failed."""
    status_code = 503

class MT5OrderError(MT5BaseException):
    """Order placement, modification, or cancellation failed."""
    status_code = 400

class MT5SymbolNotFoundError(MT5BaseException):
    """Requested symbol does not exist or has no data."""
    status_code = 404

class MT5RateLimitError(MT5BaseException):
    """Too many requests to MT5 terminal."""
    status_code = 429
