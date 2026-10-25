import json
import sys
import time

from conftest import make_pep_html
from pep_scraper import benchmark
from pep_scraper.fetcher import FetchResult


def fake_fetch(delay: float):
    def fetch() -> list[FetchResult]:
        time.sleep(delay)
        return [
            FetchResult("u1", 200, make_pep_html(1), delay),
            FetchResult("u2", 404, None, delay, "HTTP 404"),
        ]

    return fetch


def test_parse_results_skips_failures():
    records = benchmark.parse_results(fake_fetch(0)())

    assert [r["number"] for r in records] == [1]


def fake_approaches(urls):
    return {"sequential": fake_fetch(0.2), "threaded": fake_fetch(0.05), "async": fake_fetch(0.05)}


def test_run_benchmark_reports_speedups(monkeypatch):
    monkeypatch.setattr(benchmark, "build_approaches", fake_approaches)

    report = benchmark.run_benchmark(["u1", "u2"], rounds=2)

    results = report["results"]
    assert report["url_count"] == 2
    assert report["rounds"] == 2
    assert len(results["async"]["runs_seconds"]) == 2
    assert results["sequential"]["speedup_vs_sequential"] == 1.0
    assert results["async"]["speedup_vs_sequential"] > 2
    assert results["threaded"]["pages_parsed"] == 1


def test_format_table_lists_every_approach():
    report = {
        "results": {
            name: {"mean_seconds": 1.0, "best_seconds": 0.9, "pages_parsed": 25, "speedup_vs_sequential": 1.0}
            for name in ("sequential", "threaded", "async")
        }
    }

    table = benchmark.format_table(report)

    assert table.splitlines()[0].startswith("Approach")
    assert all(name in table for name in ("sequential", "threaded", "async"))


def test_main_prints_table_and_saves_report(monkeypatch, tmp_path, capsys):
    real_save_json = benchmark.save_json
    monkeypatch.setattr(benchmark, "build_approaches", fake_approaches)
    monkeypatch.setattr(benchmark, "save_json", lambda data, filename: real_save_json(data, filename, tmp_path))
    monkeypatch.setattr(sys, "argv", ["benchmark", "--rounds", "1"])

    benchmark.main()

    output = capsys.readouterr().out
    assert "round 1/1  async" in output
    assert "Speedup" in output
    report = json.loads((tmp_path / "benchmark_report.json").read_text(encoding="utf-8"))
    assert report["rounds"] == 1
    assert set(report["results"]) == {"sequential", "threaded", "async"}
