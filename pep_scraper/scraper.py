"""End-to-end async pipeline: generate URLs -> fetch -> parse -> save."""

import logging
import time
from collections.abc import Iterable
from datetime import datetime, timezone
from operator import itemgetter
from pathlib import Path
from typing import Any

from . import config
from .fetcher import FetchResult, create_session
from .generators import generate_pep_urls, parse_stream, stream_pages
from .parser import PepRecord, sort_records
from .storage import save_json

logger = logging.getLogger(__name__)

Pair = tuple[FetchResult, PepRecord | None]

record_of = itemgetter(1)


def describe_failure(pair: Pair) -> dict[str, str]:
    result, _ = pair
    return {"url": result.url, "error": result.error or "page is not a PEP document"}


async def scrape(
    numbers: Iterable[int] = config.PEP_NUMBERS,
    timeout: float = config.REQUEST_TIMEOUT,
    base_url: str = config.BASE_URL,
) -> dict[str, Any]:
    """Scrape the given PEPs concurrently and build the JSON-ready report."""
    urls = list(generate_pep_urls(numbers, base_url))
    started = time.perf_counter()

    async with create_session() as session:
        pairs: list[Pair] = [pair async for pair in parse_stream(stream_pages(session, urls, timeout))]

    elapsed = time.perf_counter() - started
    records = sort_records(filter(None, map(record_of, pairs)))
    failures = list(map(describe_failure, filter(lambda pair: record_of(pair) is None, pairs)))

    return {
        "source": base_url,
        "scraped_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "elapsed_seconds": round(elapsed, 3),
        "total_urls": len(urls),
        "succeeded": len(records),
        "failed": failures,
        "peps": records,
    }


async def run(output_dir: Path = config.OUTPUT_DIR) -> Path:
    """Scrape the configured PEPs and write the report to disk."""
    report = await scrape()
    path = await save_json(report, config.RESULTS_FILENAME, output_dir)
    logger.info(
        "Scraped %d/%d PEPs in %.2fs -> %s",
        report["succeeded"], report["total_urls"], report["elapsed_seconds"], path,
    )
    return path
