import asyncio

from conftest import make_pep_html
from pep_scraper import basics
from pep_scraper.fetcher import FetchResult


def test_function_runs_immediately_but_coroutine_does_not():
    comparison = basics.compare_function_and_coroutine(8)

    assert comparison["function_result"] == "https://peps.python.org/pep-0008/"
    assert comparison["is_coroutine"] is True
    assert comparison["coroutine_result_type"] == "coroutine"


def test_run_on_new_loop_returns_result_and_closes_loop():
    seen = {}

    async def work() -> str:
        seen["loop"] = asyncio.get_running_loop()
        await asyncio.sleep(0)
        return "done"

    assert basics.run_on_new_loop(work()) == "done"
    assert seen["loop"].is_closed()


async def test_fetch_single_pep_from_local_server(pep_server):
    result = await basics.fetch_single_pep(8, base_url=pep_server.base_url)

    assert result.ok
    assert result.url == pep_server("/pep-0008/")


def test_main_prints_demo(monkeypatch, capsys):
    async def fake_fetch(number: int, base_url: str = "") -> FetchResult:
        return FetchResult(f"u{number}", 200, make_pep_html(number, "Style Guide"), 0.25)

    monkeypatch.setattr(basics, "fetch_single_pep", fake_fetch)

    basics.main()

    output = capsys.readouterr().out
    assert "(already executed)" in output
    assert "<coroutine object> (nothing ran yet)" in output
    assert "PEP 8: Style Guide (0.25s)" in output
