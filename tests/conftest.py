"""Shared fixtures: sample PEP markup and a local aiohttp server to scrape.

Tests never touch the real internet; the local server reproduces the
responses the scraper has to handle (good pages, 404s, 5xx, slow pages)
and records how many requests it was serving at the same time.
"""

import asyncio

import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

from pep_scraper import decorators
from pep_scraper.fetcher import _request

PAGE_DELAY = 0.3  # seconds every /pep-XXXX/ page takes to answer


def make_pep_html(number: int, title: str = "Sample Proposal", python_version: str | None = "3.11") -> str:
    """Build markup shaped like a real peps.python.org page header."""
    version_field = (
        '<dt class="field-odd">Python-Version<span class="colon">:</span></dt>\n'
        f'<dd class="field-odd">{python_version}</dd>\n'
        if python_version
        else ""
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head><title>PEP {number} – {title} | peps.python.org</title></head>
<body>
<dl class="rfc2822 field-list simple">
<dt class="field-odd">Author<span class="colon">:</span></dt>
<dd class="field-odd">Guido van Rossum &lt;guido at python.org&gt;,
Łukasz Langa &lt;lukasz at python.org&gt;</dd>
<dt class="field-even">Status<span class="colon">:</span></dt>
<dd class="field-even"><abbr title="Accepted and implementation complete">Final</abbr></dd>
<dt class="field-odd">Type<span class="colon">:</span></dt>
<dd class="field-odd"><abbr title="Normative PEP">Standards Track</abbr></dd>
<dt class="field-even">Created<span class="colon">:</span></dt>
<dd class="field-even">01-Jan-2020</dd>
{version_field}</dl>
</body>
</html>"""


class LocalServer:
    """URL builder for the test server plus statistics about the requests it served."""

    def __init__(self) -> None:
        self.base_url = ""
        self.in_flight = 0
        self.max_in_flight = 0
        self.client_ports: set[int] = set()

    def __call__(self, path: str) -> str:
        return f"{self.base_url}{path}"


@pytest.fixture(autouse=True)
def fresh_rate_limiter():
    """Start every test with an empty rate-limit window so tests can't slow each other down."""
    _request.reset()


@pytest.fixture
def retry_waits(monkeypatch) -> list[float]:
    """Make decorator waits instant and record how long they would have been."""
    waits: list[float] = []

    async def record_wait(seconds: float) -> None:
        waits.append(seconds)

    monkeypatch.setattr(decorators, "sleep", record_wait)
    return waits


@pytest.fixture
def pep_html() -> str:
    return make_pep_html(8, "Style Guide for Python Code")


@pytest.fixture
async def pep_server():
    """Start a local HTTP server and yield a ``LocalServer`` for building URLs."""
    stats = LocalServer()
    flaky_calls = 0

    async def pep_page(request: web.Request) -> web.Response:
        stats.client_ports.add(request.transport.get_extra_info("peername")[1])
        stats.in_flight += 1
        stats.max_in_flight = max(stats.max_in_flight, stats.in_flight)
        try:
            await asyncio.sleep(PAGE_DELAY)
        finally:
            stats.in_flight -= 1
        number = int(request.match_info["number"])
        return web.Response(text=make_pep_html(number), content_type="text/html")

    async def slow(request: web.Request) -> web.Response:
        await asyncio.sleep(2)
        return web.Response(text="too late")

    async def missing(request: web.Request) -> web.Response:
        raise web.HTTPNotFound()

    async def flaky(request: web.Request) -> web.Response:
        # Fails twice with 503, then succeeds: exercises the @retry decorator.
        nonlocal flaky_calls
        flaky_calls += 1
        if flaky_calls < 3:
            raise web.HTTPServiceUnavailable()
        return web.Response(text=make_pep_html(1), content_type="text/html")

    async def compressed(request: web.Request) -> web.Response:
        response = web.Response(text=make_pep_html(20), content_type="text/html")
        response.enable_compression()  # gzip, if the client says it accepts it
        return response

    async def not_a_pep(request: web.Request) -> web.Response:
        return web.Response(text="<html><title>Home</title></html>", content_type="text/html")

    app = web.Application()
    app.router.add_get(r"/pep-{number:\d+}/", pep_page)
    app.router.add_get("/slow", slow)
    app.router.add_get("/missing", missing)
    app.router.add_get("/flaky", flaky)
    app.router.add_get("/compressed", compressed)
    app.router.add_get("/not-a-pep", not_a_pep)

    server = TestServer(app)
    await server.start_server()
    stats.base_url = str(server.make_url("")).rstrip("/")
    try:
        yield stats
    finally:
        await server.close()
