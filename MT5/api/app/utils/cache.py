import time
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

class CacheManager:
    """
    Simple TTL (Time-To-Live) cache manager to reduce MT5 API calls 
    for frequently accessed data like symbol info and ticks.
    """
    def __init__(self, default_ttl: int = 5):
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._default_ttl = default_ttl

    def get(self, key: str) -> Optional[Any]:
        """Retrieve a value from the cache if it hasn't expired."""
        if key in self._cache:
            entry = self._cache[key]
            if time.time() < entry['expiry']:
                return entry['value']
            else:
                del self._cache[key]
        return None

    def set(self, key: str, value: Any, ttl: Optional[int] = None):
        """Store a value in the cache with a specific TTL."""
        expiry = time.time() + (ttl if ttl is not None else self._default_ttl)
        self._cache[key] = {
            'value': value,
            'expiry': expiry
        }

    def clear(self):
        """Wipe all cached data."""
        self._cache.clear()

# Global cache instance
cache_manager = CacheManager(default_ttl=2)  # Short TTL for live trading data
