import asyncio
import time

import pytest

from pep_scraper.decorators import rate_limit, retry


async def test_retry_returns_after_transient_failures():
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


async def test_retry_reraises_after_last_attempt():
    calls = 0

    @retry(attempts=2, delay=0.01, exceptions=(ConnectionError,))
    async def always_fails() -> None:
        nonlocal calls
        calls += 1
        raise ConnectionError("down")

    with pytest.raises(ConnectionError):
        await always_fails()
    assert calls == 2


async def test_retry_ignores_unlisted_exceptions():
    calls = 0

    @retry(attempts=3, delay=0.01, exceptions=(ConnectionError,))
    async def buggy() -> None:
        nonlocal calls
        calls += 1
        raise ValueError("not retryable")

    with pytest.raises(ValueError):
        await buggy()
    assert calls == 1


async def test_retry_backs_off_exponentially(monkeypatch):
    sleeps: list[float] = []
    real_sleep = asyncio.sleep

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)
        await real_sleep(0)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    @retry(attempts=4, delay=0.5, backoff=2.0, exceptions=(ConnectionError,))
    async def always_fails() -> None:
        raise ConnectionError

    with pytest.raises(ConnectionError):
        await always_fails()
    assert sleeps == [0.5, 1.0, 2.0]


async def test_rate_limit_spaces_out_calls():
    starts: list[float] = []

    @rate_limit(calls=2, period=0.2)
    async def record() -> None:
        starts.append(time.monotonic())

    await asyncio.gather(*(record() for _ in range(6)))

    starts.sort()
    # Any 3 consecutive starts must span at least one period (2 calls allowed per period).
    for first, third in zip(starts, starts[2:]):
        assert third - first >= 0.2 - 0.01
    assert starts[-1] - starts[0] >= 0.4 - 0.01


async def test_rate_limit_does_not_delay_calls_within_budget():
    @rate_limit(calls=5, period=10)
    async def quick() -> int:
        return 1

    started = time.monotonic()
    assert sum(await asyncio.gather(*(quick() for _ in range(5)))) == 5
    assert time.monotonic() - started < 0.1


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
