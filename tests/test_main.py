from pathlib import Path

from pep_scraper import __main__ as entry_point


def test_main_runs_the_pipeline_on_an_event_loop(monkeypatch):
    calls = []

    async def fake_run() -> Path:
        calls.append("run")
        return Path("output/peps.json")

    monkeypatch.setattr(entry_point, "run", fake_run)

    entry_point.main()

    assert calls == ["run"]
