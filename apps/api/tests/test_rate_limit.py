import asyncio
import heapq
import math

import pytest


def _limiter(**kwargs: object):
    from app.core.rate_limit import FixedWindowRateLimiter

    return FixedWindowRateLimiter(**kwargs)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"limit": 0, "window_seconds": 1},
        {"limit": True, "window_seconds": 1},
        {"limit": 1.5, "window_seconds": 1},
        {"limit": 1, "window_seconds": 0},
        {"limit": 1, "window_seconds": True},
        {"limit": 1, "window_seconds": math.nan},
        {"limit": 1, "window_seconds": math.inf},
        {"limit": 1, "window_seconds": "1"},
        {"limit": 1, "window_seconds": 1, "max_keys": 0},
        {"limit": 1, "window_seconds": 1, "max_keys": True},
        {"limit": 1, "window_seconds": 1, "max_keys": 1.5},
    ],
)
def test_constructor_rejects_non_positive_values(kwargs: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        _limiter(**kwargs)


@pytest.mark.asyncio
async def test_exact_limit_and_reset_boundary() -> None:
    limiter = _limiter(limit=2, window_seconds=10, max_keys=10)
    assert await limiter.allow("key", now=4)
    assert await limiter.allow("key", now=5)
    assert not await limiter.allow("key", now=13.999)
    assert await limiter.allow("key", now=14)


@pytest.mark.asyncio
async def test_concurrent_calls_cannot_exceed_limit() -> None:
    limiter = _limiter(limit=7, window_seconds=10, max_keys=10)
    results = await asyncio.gather(*(limiter.allow("same", now=0) for _ in range(50)))
    assert sum(results) == 7


@pytest.mark.asyncio
async def test_capacity_prunes_expired_entry_before_admitting_new_key() -> None:
    limiter = _limiter(limit=1, window_seconds=10, max_keys=2)
    await limiter.allow("first", now=0)
    await limiter.allow("second", now=1)
    assert await limiter.allow("third", now=10)
    assert len(limiter._entries) == 2
    assert set(limiter._entries) == {"second", "third"}


@pytest.mark.asyncio
async def test_capacity_evicts_oldest_active_window_and_remains_bounded() -> None:
    limiter = _limiter(limit=1, window_seconds=10, max_keys=2)
    await limiter.allow("first", now=0)
    await limiter.allow("second", now=1)
    assert await limiter.allow("third", now=2)
    assert len(limiter._entries) == 2
    assert set(limiter._entries) == {"second", "third"}


@pytest.mark.asyncio
async def test_equal_reset_windows_evict_lexicographically_first_key() -> None:
    limiter = _limiter(limit=1, window_seconds=10, max_keys=2)
    await limiter.allow("zeta", now=0)
    await limiter.allow("alpha", now=0)
    assert await limiter.allow("new", now=1)
    assert set(limiter._entries) == {"zeta", "new"}


@pytest.mark.asyncio
async def test_stale_heap_node_does_not_delete_newer_window_for_same_key() -> None:
    limiter = _limiter(limit=1, window_seconds=10, max_keys=2)
    await limiter.allow("key", now=0)
    heapq.heappush(limiter._expiries, (5, "key"))
    assert await limiter.allow("other", now=5)
    assert set(limiter._entries) == {"key", "other"}
    assert not await limiter.allow("key", now=9)


@pytest.mark.asyncio
@pytest.mark.parametrize("now", [True, math.nan, math.inf, -math.inf, "1", object()])
async def test_allow_rejects_invalid_explicit_time(now: object) -> None:
    limiter = _limiter(limit=1, window_seconds=10)
    with pytest.raises((TypeError, ValueError)):
        await limiter.allow("key", now=now)


@pytest.mark.asyncio
async def test_default_limiters_are_isolated_per_fastapi_app() -> None:
    from app.main import create_app

    first = create_app().state.message_rate_limiter
    second = create_app().state.message_rate_limiter
    assert first is not second
    for _ in range(30):
        assert await first.allow("user:conversation", now=0)
    assert not await first.allow("user:conversation", now=0)
    assert await second.allow("user:conversation", now=0)
