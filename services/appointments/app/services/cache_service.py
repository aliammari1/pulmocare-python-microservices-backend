import fnmatch
import time
from typing import Any

from services.logger_service import logger_service


class CacheService:
    """
    A simple in-memory cache service with TTL support
    """

    def __init__(self):
        self._cache: dict[str, dict[str, Any]] = {}
        logger_service.info("Cache service initialized")

    def get(self, key: str) -> str | None:
        """
        Get a value from the cache. Returns None if not found or expired.
        """
        if key not in self._cache:
            return None

        cache_item = self._cache[key]

        # Check if item has expired
        if cache_item["expiry"] and cache_item["expiry"] < time.time():
            # Remove expired item
            self.delete(key)
            return None

        logger_service.debug(f"Cache hit for key: {key}")
        return cache_item["value"]

    def set(self, key: str, value: str, ttl: int | None = None) -> None:
        """
        Set a value in the cache with an optional TTL in seconds.
        """
        expiry = None
        if ttl is not None:
            expiry = time.time() + ttl

        self._cache[key] = {"value": value, "expiry": expiry}
        logger_service.debug(f"Cached value for key: {key}, TTL: {ttl}s")

    def delete(self, key: str) -> bool:
        """
        Delete a key from the cache. Returns True if deleted, False if not found.
        """
        if key in self._cache:
            del self._cache[key]
            logger_service.debug(f"Deleted cache key: {key}")
            return True
        return False

    def delete_pattern(self, pattern: str) -> int:
        """
        Delete all keys matching the given pattern.
        Returns the number of keys deleted.
        """
        keys_to_delete = [k for k in self._cache.keys() if fnmatch.fnmatch(k, pattern)]
        count = 0

        for key in keys_to_delete:
            self.delete(key)
            count += 1

        if count > 0:
            logger_service.debug(f"Deleted {count} cache keys matching pattern: {pattern}")

        return count

    def clear(self) -> None:
        """
        Clear all cache entries.
        """
        self._cache.clear()
        logger_service.info("Cache cleared")

    def cleanup_expired(self) -> int:
        """
        Remove all expired items from the cache.
        Returns the number of items removed.
        """
        current_time = time.time()
        expired_keys = [key for key, item in self._cache.items() if item["expiry"] and item["expiry"] < current_time]

        for key in expired_keys:
            self.delete(key)

        if expired_keys:
            logger_service.debug(f"Cleaned up {len(expired_keys)} expired cache entries")

        return len(expired_keys)
