import inspect

from pep_scraper.fetching.async_fetcher import FetchResult, create_session
from pep_scraper.processing.streams import generate_pep_urls, parse_stream, stream_pages


def test_generate_pep_urls_is_lazy_and_zero_padded():
    urls = generate_pep_urls([8, 3107], base_url="https://example.org")

    assert inspect.isgenerator(urls)
    assert next(urls) == "https://example.org/pep-0008/"
    assert list(urls) == ["https://example.org/pep-3107/"]


def test_pipeline_stages_are_async_generators():
    assert inspect.isasyncgenfunction(stream_pages)
    assert inspect.isasyncgenfunction(parse_stream)


async def test_stream_pages_yields_in_completion_order(pep_server):
    # /missing answers instantly while PEP pages are delayed, so it must arrive first.
    urls = [pep_server("/pep-0001/"), pep_server("/missing")]

    async with create_session() as session:
        results = [result async for result in stream_pages(session, urls)]

    assert [r.url for r in results] == [urls[1], urls[0]]


async def test_parse_stream_pairs_results_with_records():
    async def fake_results():
        yield FetchResult("u1", 200, "<title>PEP 20 – The Zen of Python | peps.python.org</title>", 0.1)
        yield FetchResult("u2", 404, None, 0.1, "HTTP 404")
        yield FetchResult("u3", 200, "<title>Not a PEP</title>", 0.1)

    pairs = [pair async for pair in parse_stream(fake_results())]

    records = [record for _, record in pairs]
    assert records[0]["number"] == 20
    assert records[0]["title"] == "The Zen of Python"
    assert records[1:] == [None, None]
