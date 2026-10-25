"""Blocking counterparts of the async fetcher, used for the performance comparison.

Like aiohttp's ``ClientSession``, these versions keep one persistent HTTP
connection per host (per thread) and accept gzip-compressed responses, so
the benchmark compares concurrency models rather than connection set-up
costs or download sizes.
"""

import gzip
import http.client
import threading
import time
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from types import TracebackType
from urllib.parse import urlsplit

from .. import config
from .async_fetcher import FetchResult

# A kept-alive connection may have been closed by the server between requests;
# these errors mean "reconnect and send the request again".
STALE_CONNECTION_ERRORS = (ConnectionResetError, BrokenPipeError, http.client.RemoteDisconnected)


class ConnectionPool:
    """Keep one reusable connection per (scheme, host) for each thread.

    ``http.client`` connections are not thread-safe, so every thread gets
    its own set through ``threading.local``.
    """

    def __init__(self, timeout: float = config.REQUEST_TIMEOUT) -> None:
        self.timeout = timeout
        self._local = threading.local()
        self._opened: list[http.client.HTTPConnection] = []
        self._lock = threading.Lock()

    def _connections(self) -> dict[tuple[str, str], http.client.HTTPConnection]:
        return self._local.__dict__.setdefault("connections", {})

    def get(self, scheme: str, host: str) -> http.client.HTTPConnection:
        connections = self._connections()
        if (scheme, host) not in connections:
            factory = http.client.HTTPSConnection if scheme == "https" else http.client.HTTPConnection
            connection = factory(host, timeout=self.timeout)
            connections[scheme, host] = connection
            with self._lock:
                self._opened.append(connection)
        return connections[scheme, host]

    def discard(self, scheme: str, host: str) -> None:
        """Drop a broken connection; the next ``get`` opens a fresh one."""
        if connection := self._connections().pop((scheme, host), None):
            connection.close()

    def close(self) -> None:
        with self._lock:
            for connection in self._opened:
                connection.close()
            self._opened.clear()

    def __enter__(self) -> "ConnectionPool":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()


def _send(connection: http.client.HTTPConnection, target: str) -> tuple[int, str]:
    connection.request("GET", target, headers={"User-Agent": config.USER_AGENT, "Accept-Encoding": "gzip"})
    response = connection.getresponse()
    body = response.read()  # the body must be fully read before the connection is reused
    if response.getheader("Content-Encoding") == "gzip":
        body = gzip.decompress(body)
    return response.status, body.decode(response.headers.get_content_charset() or "utf-8")


def _get(pool: ConnectionPool, url: str) -> tuple[int, str]:
    """Send one GET request, reconnecting once if a kept-alive socket went stale."""
    parts = urlsplit(url)
    target = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
    try:
        try:
            return _send(pool.get(parts.scheme, parts.netloc), target)
        except STALE_CONNECTION_ERRORS:
            pool.discard(parts.scheme, parts.netloc)
            return _send(pool.get(parts.scheme, parts.netloc), target)
    except (OSError, http.client.HTTPException):
        pool.discard(parts.scheme, parts.netloc)  # never reuse a connection in an unknown state
        raise


def fetch_url_sync(
    url: str,
    timeout: float = config.REQUEST_TIMEOUT,
    pool: ConnectionPool | None = None,
) -> FetchResult:
    """Fetch one URL, blocking the calling thread until the page arrives."""
    if pool is None:
        with ConnectionPool(timeout) as own_pool:
            return fetch_url_sync(url, timeout, own_pool)

    started = time.perf_counter()
    try:
        status, html = _get(pool, url)
    except TimeoutError:
        return FetchResult(url, None, None, time.perf_counter() - started, f"timed out after {timeout}s")
    except (OSError, http.client.HTTPException) as exc:
        return FetchResult(url, None, None, time.perf_counter() - started, f"{type(exc).__name__}: {exc}")

    elapsed = time.perf_counter() - started
    if status >= 400:
        return FetchResult(url, status, None, elapsed, f"HTTP {status}")
    return FetchResult(url, status, html, elapsed)


def fetch_all_sequential(urls: Iterable[str], timeout: float = config.REQUEST_TIMEOUT) -> list[FetchResult]:
    """Fetch URLs one after another: each request waits for the previous one."""
    with ConnectionPool(timeout) as pool:
        return [fetch_url_sync(url, timeout, pool) for url in urls]


def fetch_all_threaded(
    urls: Iterable[str],
    timeout: float = config.REQUEST_TIMEOUT,
    workers: int = config.THREAD_WORKERS,
) -> list[FetchResult]:
    """Fetch URLs on a thread pool; results keep the input order."""
    with ConnectionPool(timeout) as pool, ThreadPoolExecutor(max_workers=workers) as executor:
        return list(executor.map(partial(fetch_url_sync, timeout=timeout, pool=pool), urls))
