"""A small in-memory cache with expiry, for the countries list (choices-from-web). FastAPI has no cache of
its own. It lives in this process: with several processes or servers, use a shared cache (Redis,
Memcached, or a table) so they don't each call restcountries.com."""

import time
from typing import Annotated, Any

from fastapi import Depends
from starlette.requests import HTTPConnection


class TtlCache:
    def __init__(self) -> None:
        self._entries: dict[str, tuple[Any, float]] = {}

    def get(self, key: str) -> Any:
        """The value, or None when it is missing or expired."""
        value, expires = self._entries.get(key, (None, 0.0))
        if expires > time.monotonic():
            return value
        self._entries.pop(key, None)
        return None

    def has(self, key: str) -> bool:
        return self.get(key) is not None

    def set(self, key: str, value: Any, ttl_seconds: float) -> None:
        self._entries[key] = (value, time.monotonic() + ttl_seconds)

    def clear(self) -> None:
        self._entries.clear()


def get_cache(conn: HTTPConnection) -> TtlCache:
    return conn.app.state.cache


Cache = Annotated[TtlCache, Depends(get_cache)]
"""The app's cache, one per process, created in app/main.py."""
