import asyncio

import pytest

from pep_scraper.decorators import rate_limit, retry


async def test_retry_returns_after_transient_failures(retry_waits):
    calls = 0

    @retry(attempts=3, delay=0.01, exceptions=(ConnectionError,))
    async def unstable() -> str:
        nonlocal calls
        calls += 1
        if calls < 3:
            raise ConnectionError("boom")
        return "ok"

    assert await unstable() == "ok"
    assert calls == 3


async def test_retry_reraises_after_last_attempt(retry_waits):
    calls = 0

    @retry(attempts=2, delay=0.01, exceptions=(ConnectionError,))
    async def always_fails() -> None:
        nonlocal calls
        calls += 1
        raise ConnectionError("down")

    with pytest.raises(ConnectionError):
        await always_fails()
    assert calls == 2


async def test_retry_ignores_unlisted_exceptions(retry_waits):
    calls = 0

    @retry(attempts=3, delay=0.01, exceptions=(ConnectionError,))
    async def buggy() -> None:
        nonlocal calls
        calls += 1
        raise ValueError("not retryable")

    with pytest.raises(ValueError):
        await buggy()
    assert calls == 1
    assert retry_waits == []


async def test_retry_backs_off_exponentially(retry_waits):
    @retry(attempts=4, delay=0.5, backoff=2.0, exceptions=(ConnectionError,))
    async def always_fails() -> None:
        raise ConnectionError

    with pytest.raises(ConnectionError):
        await always_fails()
    assert retry_waits == [0.5, 1.0, 2.0]


async def test_retry_does_not_wait_after_success(retry_waits):
    @retry(attempts=3, delay=1.0)
    async def works() -> int:
        return 42

    assert await works() == 42
    assert retry_waits == []


async def test_rate_limit_delays_calls_beyond_budget(retry_waits):
    @rate_limit(calls=2, period=0.2)
    async def call() -> None: ...

    await asyncio.gather(*(call() for _ in range(6)))

    # 2 calls start at once, the next 2 one period later, the last 2 two periods later.
    assert retry_waits == pytest.approx([0.2, 0.2, 0.4, 0.4], abs=0.05)


async def test_rate_limit_does_not_delay_calls_within_budget(retry_waits):
    @rate_limit(calls=5, period=10)
    async def quick() -> int:
        return 1

    assert sum(await asyncio.gather(*(quick() for _ in range(5)))) == 5
    assert retry_waits == []


async def test_rate_limit_reset_restores_full_budget(retry_waits):
    @rate_limit(calls=1, period=10)
    async def call() -> None: ...

    await call()
    call.reset()
    await call()

    assert retry_waits == []


async def test_rate_limit_really_spaces_calls_in_time():
    starts: list[float] = []
    loop = asyncio.get_running_loop()

    @rate_limit(calls=2, period=0.2)
    async def record() -> None:
        starts.append(loop.time())

    await asyncio.gather(*(record() for _ in range(4)))

    assert starts[-1] - starts[0] >= 0.2 - 0.02


def test_reset_survives_stacking_with_retry():
    @retry()
    @rate_limit(calls=1, period=1)
    async def stacked() -> None: ...

    assert callable(stacked.reset)


@pytest.mark.parametrize("decorator", [retry(), rate_limit(calls=1, period=1)])
def test_decorators_reject_sync_functions(decorator):
    def plain() -> None: ...

    with pytest.raises(TypeError, match="async def"):
        decorator(plain)


def test_decorators_preserve_metadata():
    @retry()
    @rate_limit(calls=1, period=1)
    async def documented() -> None:
        """Docstring survives."""

    assert documented.__name__ == "documented"
    assert documented.__doc__ == "Docstring survives."


@pytest.mark.parametrize(
    "factory",
    [lambda: retry(attempts=0), lambda: rate_limit(calls=0, period=1), lambda: rate_limit(calls=1, period=0)],
)
def test_decorators_validate_arguments(factory):
    with pytest.raises(ValueError):
        factory()
