"""Asynchronous HTTP fetching built on aiohttp."""

import asyncio
import logging
import time
from collections.abc import Iterable
from dataclasses import dataclass

import aiohttp

from .. import config
from ..core.decorators import rate_limit, retry

logger = logging.getLogger(__name__)

# Errors worth another attempt: connection problems, timeouts and 5xx answers.
TRANSIENT_ERRORS: tuple[type[BaseException], ...] = (aiohttp.ClientError, TimeoutError)


@dataclass(frozen=True, slots=True)
class FetchResult:
    """Outcome of fetching one URL. ``html`` is ``None`` when the fetch failed."""

    url: str
    status: int | None
    html: str | None
    elapsed: float
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and self.html is not None


def create_session() -> aiohttp.ClientSession:
    """Build a session shared by every request so connections are reused."""
    return aiohttp.ClientSession(headers={"User-Agent": config.USER_AGENT})


@retry(
    attempts=config.MAX_RETRIES,
    delay=config.RETRY_DELAY,
    backoff=config.RETRY_BACKOFF,
    exceptions=TRANSIENT_ERRORS,
)
@rate_limit(calls=config.RATE_LIMIT_CALLS, period=config.RATE_LIMIT_PERIOD)
async def _request(session: aiohttp.ClientSession, url: str, timeout: float) -> tuple[int, str]:
    """Perform one GET request; every retry attempt also passes the rate limiter."""
    logger.info("-> request %s", url)

    async def get() -> tuple[int, str]:
        async with session.get(url) as response:
            if response.status >= 500:
                response.raise_for_status()  # server-side problem: let @retry try again
            return response.status, await response.text()

    # wait_for cancels the request if it exceeds the timeout and raises TimeoutError.
    return await asyncio.wait_for(get(), timeout=timeout)


def _describe_error(exc: Exception, timeout: float) -> tuple[int | None, str]:
    """Map an exception raised by ``_request`` to (status, error message)."""
    if isinstance(exc, TimeoutError):
        return None, f"timed out after {timeout}s"
    if isinstance(exc, aiohttp.ClientResponseError):
        return exc.status, f"HTTP {exc.status}"
    return None, f"{type(exc).__name__}: {exc}"


async def fetch_url(
    session: aiohttp.ClientSession,
    url: str,
    timeout: float = config.REQUEST_TIMEOUT,
) -> FetchResult:
    """Fetch a single URL, converting every failure into a ``FetchResult``.

    Errors are captured instead of raised so one bad URL never cancels the
    other tasks running alongside it in ``asyncio.gather``.
    """
    started = time.perf_counter()
    status: int | None
    html: str | None = None
    try:
        status, page = await _request(session, url, timeout)
    except (aiohttp.ClientError, TimeoutError) as exc:
        status, error = _describe_error(exc, timeout)
    else:
        error = f"HTTP {status}" if status >= 400 else None
        html = None if error else page

    result = FetchResult(url, status, html, time.perf_counter() - started, error)
    logger.info("<- done    %s (%s, %.2fs)", url, result.error or result.status, result.elapsed)
    return result


async def fetch_all(urls: Iterable[str], timeout: float = config.REQUEST_TIMEOUT) -> list[FetchResult]:
    """Fetch every URL concurrently and return results in input order.

    ``asyncio.create_task`` schedules each coroutine on the event loop right
    away; ``asyncio.gather`` then waits for all of them together.
    """
    async with create_session() as session:
        tasks = [asyncio.create_task(fetch_url(session, url, timeout), name=url) for url in urls]
        return await asyncio.gather(*tasks)
