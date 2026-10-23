import time

from conftest import PAGE_DELAY
from pep_scraper.fetcher import create_session, fetch_all, fetch_url


async def test_fetch_url_returns_page(pep_server):
    async with create_session() as session:
        result = await fetch_url(session, pep_server("/pep-0008/"))

    assert result.ok
    assert result.status == 200
    assert "PEP 8" in result.html
    assert result.elapsed >= PAGE_DELAY - 0.05


async def test_fetch_url_reports_client_errors_without_raising(pep_server):
    async with create_session() as session:
        result = await fetch_url(session, pep_server("/missing"))

    assert not result.ok
    assert result.status == 404
    assert result.error == "HTTP 404"


async def test_fetch_url_retries_server_errors(pep_server):
    async with create_session() as session:
        result = await fetch_url(session, pep_server("/flaky"))

    assert result.ok  # two 503 answers, then success on the third attempt


async def test_fetch_url_times_out(pep_server):
    async with create_session() as session:
        result = await fetch_url(session, pep_server("/slow"), timeout=0.1)

    assert not result.ok
    assert result.error == "timed out after 0.1s"


async def test_fetch_url_reports_connection_errors():
    async with create_session() as session:
        # Port 9 (discard) is essentially never listening locally.
        result = await fetch_url(session, "http://127.0.0.1:9/", timeout=2)

    assert not result.ok
    assert result.status is None
    assert result.error


async def test_fetch_all_runs_requests_concurrently(pep_server):
    urls = [pep_server(f"/pep-{n:04d}/") for n in range(1, 11)]

    started = time.perf_counter()
    results = await fetch_all(urls)
    elapsed = time.perf_counter() - started

    assert [r.url for r in results] == urls  # gather keeps input order
    assert all(r.ok for r in results)
    # Sequentially this would take 10 * PAGE_DELAY = 3s.
    assert elapsed < len(urls) * PAGE_DELAY / 2


async def test_fetch_all_isolates_failures(pep_server):
    urls = [pep_server("/pep-0001/"), pep_server("/missing"), pep_server("/pep-0002/")]

    results = await fetch_all(urls)

    assert [r.ok for r in results] == [True, False, True]
