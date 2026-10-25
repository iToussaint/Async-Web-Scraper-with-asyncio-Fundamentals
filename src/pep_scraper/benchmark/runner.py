"""Benchmark async vs threaded vs sequential scraping (``python -m pep_scraper.benchmark``)."""

import argparse
import asyncio
import platform
import statistics
import time
from collections.abc import Callable, Iterable
from datetime import datetime, timezone
from operator import attrgetter
from typing import Any

from .. import config
from ..fetching.async_fetcher import FetchResult, fetch_all
from ..fetching.sync_fetcher import fetch_all_sequential, fetch_all_threaded
from ..processing.parser import PepRecord, parse_pep
from ..processing.streams import generate_pep_urls
from ..storage.json_storage import save_json


def parse_results(results: Iterable[FetchResult]) -> list[PepRecord]:
    """Parse every successful page, dropping anything that is not a PEP."""
    successful = filter(attrgetter("ok"), results)
    return list(filter(None, map(lambda result: parse_pep(result.html, result.url), successful)))


def build_approaches(urls: list[str]) -> dict[str, Callable[[], list[FetchResult]]]:
    return {
        "sequential": lambda: fetch_all_sequential(urls),
        "threaded": lambda: fetch_all_threaded(urls),
        "async": lambda: asyncio.run(fetch_all(urls)),
    }


def time_run(fetch: Callable[[], list[FetchResult]]) -> tuple[float, int]:
    """Time one full fetch + parse run; return (seconds, pages parsed)."""
    started = time.perf_counter()
    records = parse_results(fetch())
    return time.perf_counter() - started, len(records)


def run_benchmark(urls: list[str], rounds: int = 3) -> dict[str, Any]:
    approaches = build_approaches(urls)
    timings: dict[str, list[float]] = {name: [] for name in approaches}
    parsed: dict[str, int] = {}

    # Interleave approaches each round so network noise affects them all equally.
    for round_number in range(1, rounds + 1):
        for name, fetch in approaches.items():
            seconds, parsed[name] = time_run(fetch)
            timings[name].append(seconds)
            print(f"round {round_number}/{rounds}  {name:<10} {seconds:6.2f}s  ({parsed[name]} pages)")

    baseline = statistics.mean(timings["sequential"])
    results = {
        name: {
            "runs_seconds": [round(t, 3) for t in runs],
            "mean_seconds": round(statistics.mean(runs), 3),
            "best_seconds": round(min(runs), 3),
            "pages_parsed": parsed[name],
            "speedup_vs_sequential": round(baseline / statistics.mean(runs), 2),
        }
        for name, runs in timings.items()
    }
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "python_version": platform.python_version(),
        "url_count": len(urls),
        "rounds": rounds,
        "thread_workers": config.THREAD_WORKERS,
        "rate_limit": f"{config.RATE_LIMIT_CALLS} requests / {config.RATE_LIMIT_PERIOD}s",
        "results": results,
    }


def format_table(report: dict[str, Any]) -> str:
    header = f"{'Approach':<12}{'Mean (s)':>10}{'Best (s)':>10}{'Pages':>8}{'Speedup':>10}"
    rows = [
        f"{name:<12}{r['mean_seconds']:>10.2f}{r['best_seconds']:>10.2f}"
        f"{r['pages_parsed']:>8}{r['speedup_vs_sequential']:>9.2f}x"
        for name, r in report["results"].items()
    ]
    return "\n".join([header, "-" * len(header), *rows])


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark async vs threaded vs sequential scraping.")
    parser.add_argument("--rounds", type=int, default=3, help="number of runs per approach (default: 3)")
    args = parser.parse_args()

    urls = list(generate_pep_urls(config.PEP_NUMBERS))
    print(f"Benchmarking {len(urls)} URLs x {args.rounds} round(s)\n")
    report = run_benchmark(urls, args.rounds)
    path = asyncio.run(save_json(report, config.BENCHMARK_FILENAME))
    print(f"\n{format_table(report)}\n\nReport saved to {path}")


if __name__ == "__main__":
    main()
