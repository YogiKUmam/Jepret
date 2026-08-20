import asyncio
import heapq
import math
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class Window:
    count: int
    reset_at: float


class FixedWindowRateLimiter:
    def __init__(self, *, limit: int, window_seconds: float, max_keys: int = 10_000) -> None:
        if type(limit) is not int or limit <= 0:
            raise ValueError("limit must be a positive integer")
        if (
            isinstance(window_seconds, bool)
            or not isinstance(window_seconds, (int, float))
            or not math.isfinite(window_seconds)
            or window_seconds <= 0
        ):
            raise ValueError("window_seconds must be a positive finite number")
        if type(max_keys) is not int or max_keys <= 0:
            raise ValueError("limit, window_seconds, and max_keys must be positive")
        self.limit = limit
        self.window_seconds = window_seconds
        self.max_keys = max_keys
        self._entries: dict[str, Window] = {}
        self._expiries: list[tuple[float, str]] = []
        self._lock = asyncio.Lock()

    async def allow(self, key: str, now: float | None = None) -> bool:
        resolved_now = time.monotonic() if now is None else now
        if (
            isinstance(resolved_now, bool)
            or not isinstance(resolved_now, (int, float))
            or not math.isfinite(resolved_now)
        ):
            raise ValueError("now must be a finite number")
        async with self._lock:
            while self._expiries and self._expiries[0][0] <= resolved_now:
                reset_at, expired_key = heapq.heappop(self._expiries)
                current = self._entries.get(expired_key)
                if current is not None and current.reset_at == reset_at:
                    del self._entries[expired_key]
            window = self._entries.get(key)
            if window is None:
                if len(self._entries) >= self.max_keys:
                    while self._expiries:
                        reset_at, oldest_key = heapq.heappop(self._expiries)
                        oldest = self._entries.get(oldest_key)
                        if oldest is not None and oldest.reset_at == reset_at:
                            del self._entries[oldest_key]
                            break
                reset_at = resolved_now + self.window_seconds
                self._entries[key] = Window(1, reset_at)
                heapq.heappush(self._expiries, (reset_at, key))
                return True
            if window.count >= self.limit:
                return False
            self._entries[key] = Window(window.count + 1, window.reset_at)
            return True
