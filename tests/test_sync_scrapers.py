import asyncio
import time

from conftest import PAGE_DELAY
from pep_scraper.sync_scrapers import fetch_all_sequential, fetch_all_threaded, fetch_url_sync

# The local server runs on the test's event loop, so the blocking functions
# are called through asyncio.to_thread to keep that loop free to answer.


async def test_fetch_url_sync_returns_page(pep_server):
    result = await asyncio.to_thread(fetch_url_sync, pep_server("/pep-0008/"))

    assert result.ok
    assert "PEP 8" in result.html


async def test_fetch_url_sync_reports_http_errors(pep_server):
    result = await asyncio.to_thread(fetch_url_sync, pep_server("/missing"))

    assert result.status == 404
    assert result.error == "HTTP 404"


async def test_fetch_url_sync_reports_timeouts(pep_server):
    result = await asyncio.to_thread(fetch_url_sync, pep_server("/slow"), 0.1)

    assert not result.ok
    assert "timed out" in result.error


async def test_sequential_takes_the_sum_of_delays(pep_server):
    urls = [pep_server(f"/pep-{n:04d}/") for n in range(1, 5)]

    started = time.perf_counter()
    results = await asyncio.to_thread(fetch_all_sequential, urls)

    assert all(r.ok for r in results)
    assert time.perf_counter() - started >= len(urls) * PAGE_DELAY - 0.05


async def test_threaded_overlaps_requests_and_keeps_order(pep_server):
    urls = [pep_server(f"/pep-{n:04d}/") for n in range(1, 9)]

    started = time.perf_counter()
    results = await asyncio.to_thread(fetch_all_threaded, urls, 10, 8)

    assert [r.url for r in results] == urls
    assert all(r.ok for r in results)
    assert time.perf_counter() - started < len(urls) * PAGE_DELAY / 2
