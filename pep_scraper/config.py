"""Central configuration for the PEP scraper.

All tunable values live here so the fetching, benchmarking and storage
modules stay free of magic numbers.
"""

from pathlib import Path

BASE_URL = "https://peps.python.org"

# 25 well-known PEPs: enough to exercise real concurrency (the brief asks for 20+ URLs).
PEP_NUMBERS: tuple[int, ...] = (
    1, 8, 20, 257, 343, 380, 448, 484, 492, 498,
    525, 526, 557, 572, 584, 585, 604, 618, 634, 654,
    673, 695, 701, 3107, 3333,
)

# Network behaviour
REQUEST_TIMEOUT = 10.0          # seconds allowed per request (asyncio.wait_for)
MAX_RETRIES = 3                 # total attempts made by the @retry decorator
RETRY_DELAY = 0.5               # first back-off delay in seconds
RETRY_BACKOFF = 2.0             # multiplier applied to the delay after each failure
RATE_LIMIT_CALLS = 20           # max requests started ...
RATE_LIMIT_PERIOD = 1.0         # ... per this many seconds
THREAD_WORKERS = 10             # pool size for the threaded comparison
USER_AGENT = "pep-async-scraper/1.0 (+educational asyncio lab)"

# Output
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output"
RESULTS_FILENAME = "peps.json"
BENCHMARK_FILENAME = "benchmark_report.json"
