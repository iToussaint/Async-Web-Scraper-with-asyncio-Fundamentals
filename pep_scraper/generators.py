"""Sync and async generators that feed the scraping pipeline."""

import asyncio
from collections.abc import AsyncIterator, Iterable, Iterator

import aiohttp

from . import config
from .fetcher import FetchResult, fetch_url
from .parser import PepRecord, parse_pep


def generate_pep_urls(numbers: Iterable[int], base_url: str = config.BASE_URL) -> Iterator[str]:
    """Lazily build PEP URLs, e.g. 8 -> https://peps.python.org/pep-0008/."""
    for number in numbers:
        yield f"{base_url}/pep-{number:04d}/"


async def stream_pages(
    session: aiohttp.ClientSession,
    urls: Iterable[str],
    timeout: float = config.REQUEST_TIMEOUT,
) -> AsyncIterator[FetchResult]:
    """Fetch all URLs concurrently and yield each result as soon as it arrives.

    Unlike ``gather``, results come back in completion order, so fast pages
    can be processed while slow ones are still downloading.
    """
    tasks = [asyncio.create_task(fetch_url(session, url, timeout)) for url in urls]
    try:
        for next_done in asyncio.as_completed(tasks):
            yield await next_done
    finally:
        # If the consumer stops early, don't leave orphaned requests running.
        for task in tasks:
            task.cancel()


async def parse_stream(results: AsyncIterator[FetchResult]) -> AsyncIterator[tuple[FetchResult, PepRecord | None]]:
    """Pair every fetched page with its parsed record (``None`` if unusable)."""
    async for result in results:
        record = parse_pep(result.html, result.url) if result.ok else None
        yield result, record
