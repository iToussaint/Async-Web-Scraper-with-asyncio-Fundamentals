import asyncio
import http.client

from pep_scraper.fetching import sync_fetcher
from pep_scraper.fetching.sync_fetcher import ConnectionPool, fetch_all_sequential, fetch_all_threaded, fetch_url_sync

# The local server runs on the test's event loop, so the blocking functions
# are called through asyncio.to_thread to keep that loop free to answer.


async def test_fetch_url_sync_returns_page(pep_server):
    result = await asyncio.to_thread(fetch_url_sync, pep_server("/pep-0008/"))

    assert result.ok
    assert result.status == 200
    assert "PEP 8" in result.html


async def test_fetch_url_sync_decodes_gzip_responses(pep_server):
    result = await asyncio.to_thread(fetch_url_sync, pep_server("/compressed"))

    assert result.ok
    assert "PEP 20" in result.html


async def test_fetch_url_sync_reports_http_errors(pep_server):
    result = await asyncio.to_thread(fetch_url_sync, pep_server("/missing"))

    assert result.status == 404
    assert result.error == "HTTP 404"


async def test_fetch_url_sync_reports_timeouts(pep_server):
    result = await asyncio.to_thread(fetch_url_sync, pep_server("/slow"), 0.1)

    assert not result.ok
    assert result.error == "timed out after 0.1s"


def test_fetch_url_sync_reports_connection_errors():
    result = fetch_url_sync("http://127.0.0.1:9/", timeout=2)

    assert not result.ok
    assert result.status is None
    assert result.error


async def test_sequential_sends_one_request_at_a_time_on_one_connection(pep_server):
    urls = [pep_server(f"/pep-{n:04d}/") for n in range(1, 5)]

    results = await asyncio.to_thread(fetch_all_sequential, urls)

    assert all(r.ok for r in results)
    assert pep_server.max_in_flight == 1
    assert len(pep_server.client_ports) == 1  # the kept-alive connection was reused


async def test_threaded_overlaps_requests_up_to_pool_size(pep_server):
    urls = [pep_server(f"/pep-{n:04d}/") for n in range(1, 9)]

    results = await asyncio.to_thread(fetch_all_threaded, urls, 10, 4)

    assert [r.url for r in results] == urls
    assert all(r.ok for r in results)
    assert 1 < pep_server.max_in_flight <= 4
    assert len(pep_server.client_ports) <= 4  # at most one connection per worker thread


def test_get_reconnects_once_when_kept_alive_socket_is_stale(monkeypatch):
    connections = []

    def fake_send(connection, target):
        connections.append(connection)
        if len(connections) == 1:
            raise http.client.RemoteDisconnected("server closed idle connection")
        return 200, "<html></html>"

    monkeypatch.setattr(sync_fetcher, "_send", fake_send)

    with ConnectionPool() as pool:
        assert sync_fetcher._get(pool, "http://example.org/pep-0008/") == (200, "<html></html>")
    assert connections[0] is not connections[1]


def test_fetch_url_sync_gives_up_after_second_stale_connection(monkeypatch):
    def always_stale(connection, target):
        raise http.client.RemoteDisconnected("closed")

    monkeypatch.setattr(sync_fetcher, "_send", always_stale)

    result = fetch_url_sync("http://example.org/pep-0008/")

    assert not result.ok
    assert result.error.startswith("RemoteDisconnected")
