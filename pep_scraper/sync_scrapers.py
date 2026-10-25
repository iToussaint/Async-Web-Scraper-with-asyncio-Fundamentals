"""Blocking counterparts of the async fetcher, used for the performance comparison."""

import time
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from . import config
from .fetcher import FetchResult


def fetch_url_sync(url: str, timeout: float = config.REQUEST_TIMEOUT) -> FetchResult:
    """Fetch one URL with the standard library, blocking the calling thread."""
    started = time.perf_counter()
    request = Request(url, headers={"User-Agent": config.USER_AGENT})
    try:
        with urlopen(request, timeout=timeout) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            html = response.read().decode(charset)
            return FetchResult(url, response.status, html, time.perf_counter() - started)
    except HTTPError as exc:
        return FetchResult(url, exc.code, None, time.perf_counter() - started, f"HTTP {exc.code}")
    except (URLError, TimeoutError) as exc:
        return FetchResult(url, None, None, time.perf_counter() - started, f"{type(exc).__name__}: {exc}")


def fetch_all_sequential(urls: Iterable[str], timeout: float = config.REQUEST_TIMEOUT) -> list[FetchResult]:
    """Fetch URLs one after another: each request waits for the previous one."""
    return [fetch_url_sync(url, timeout) for url in urls]


def fetch_all_threaded(
    urls: Iterable[str],
    timeout: float = config.REQUEST_TIMEOUT,
    workers: int = config.THREAD_WORKERS,
) -> list[FetchResult]:
    """Fetch URLs on a thread pool; results keep the input order."""
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(partial(fetch_url_sync, timeout=timeout), urls))
