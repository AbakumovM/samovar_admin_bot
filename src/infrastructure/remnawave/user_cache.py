import time
from typing import Any


class UserLookupCache:
    """In-process TTL cache for GET /users/{id} lookups.

    Antifraud resolves only currently-online candidates (tens, not
    thousands) per scan, so a per-process dict is enough — no need for
    Redis/shared state, unlike remnawave-limiter's multi-instance design.
    """

    def __init__(self, ttl_seconds: float) -> None:
        self._ttl = ttl_seconds
        self._store: dict[int, tuple[dict[str, Any], float]] = {}

    def get(self, user_id: int) -> dict[str, Any] | None:
        entry = self._store.get(user_id)
        if entry is None:
            return None
        record, expires_at = entry
        if time.monotonic() > expires_at:
            del self._store[user_id]
            return None
        return record

    def set(self, user_id: int, record: dict[str, Any]) -> None:
        self._store[user_id] = (record, time.monotonic() + self._ttl)
