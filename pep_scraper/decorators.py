"""Decorators that add resilience and politeness to async functions."""

import asyncio
import functools
import inspect
import logging
import time
from collections import deque
from collections.abc import Awaitable, Callable
from typing import ParamSpec, TypeVar

logger = logging.getLogger(__name__)

P = ParamSpec("P")
R = TypeVar("R")

AsyncFunc = Callable[P, Awaitable[R]]


def _ensure_coroutine_function(func: Callable) -> None:
    """Reject plain functions: awaiting their result would fail at call time."""
    if not inspect.iscoroutinefunction(func):
        raise TypeError(f"{func.__qualname__} must be defined with 'async def'")


def retry(
    attempts: int = 3,
    delay: float = 0.5,
    backoff: float = 2.0,
    exceptions: tuple[type[BaseException], ...] = (Exception,),
) -> Callable[[AsyncFunc], AsyncFunc]:
    """Retry an async function with exponential back-off.

    Args:
        attempts: Total number of tries, including the first one.
        delay: Seconds to wait after the first failure.
        backoff: Factor the delay is multiplied by after every failure.
        exceptions: Only these exception types trigger a retry; anything
            else propagates immediately.
    """
    if attempts < 1:
        raise ValueError("attempts must be at least 1")

    def decorator(func: AsyncFunc) -> AsyncFunc:
        _ensure_coroutine_function(func)

        @functools.wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            wait = delay
            for attempt in range(1, attempts + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as exc:
                    if attempt == attempts:
                        raise
                    logger.warning(
                        "%s failed (attempt %d/%d): %r - retrying in %.2fs",
                        func.__name__, attempt, attempts, exc, wait,
                    )
                    # Yield to the event loop while waiting so other tasks keep running.
                    await asyncio.sleep(wait)
                    wait *= backoff
            raise AssertionError("unreachable")  # loop always returns or raises

        return wrapper

    return decorator


def rate_limit(calls: int, period: float) -> Callable[[AsyncFunc], AsyncFunc]:
    """Allow at most ``calls`` invocations to start within any ``period`` seconds.

    Each call reserves a start slot before awaiting anything. Because the
    event loop is single-threaded, reading and updating the slot history
    happens atomically, so no lock is needed.
    """
    if calls < 1 or period <= 0:
        raise ValueError("calls must be >= 1 and period must be > 0")

    def decorator(func: AsyncFunc) -> AsyncFunc:
        _ensure_coroutine_function(func)
        # Start times of the most recent `calls` invocations.
        slots: deque[float] = deque(maxlen=calls)

        @functools.wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            now = time.monotonic()
            start = now
            if len(slots) == calls:
                # The oldest slot in the window decides when the next call may start.
                start = max(now, slots[0] + period)
            slots.append(start)

            if (wait := start - now) > 0:
                await asyncio.sleep(wait)
            return await func(*args, **kwargs)

        return wrapper

    return decorator
