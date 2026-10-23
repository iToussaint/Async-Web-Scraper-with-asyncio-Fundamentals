"""Shared fixtures: sample PEP markup and a local aiohttp server to scrape.

Tests never touch the real internet; the local server reproduces the
responses the scraper has to handle (good pages, 404s, 5xx, slow pages).
"""

import asyncio

import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

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


@pytest.fixture
def pep_html() -> str:
    return make_pep_html(8, "Style Guide for Python Code")


@pytest.fixture
async def pep_server():
    """Start a local HTTP server; yields a function mapping a path to a full URL."""
    flaky_calls = 0

    async def pep_page(request: web.Request) -> web.Response:
        await asyncio.sleep(PAGE_DELAY)
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

    async def not_a_pep(request: web.Request) -> web.Response:
        return web.Response(text="<html><title>Home</title></html>", content_type="text/html")

    app = web.Application()
    app.router.add_get(r"/pep-{number:\d+}/", pep_page)
    app.router.add_get("/slow", slow)
    app.router.add_get("/missing", missing)
    app.router.add_get("/flaky", flaky)
    app.router.add_get("/not-a-pep", not_a_pep)

    server = TestServer(app)
    await server.start_server()
    try:
        yield lambda path: str(server.make_url(path))
    finally:
        await server.close()
