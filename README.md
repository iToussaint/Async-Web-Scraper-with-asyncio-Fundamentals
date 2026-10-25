# Async Web Scraper with asyncio Fundamentals

An asynchronous web scraper that collects metadata from **Python Enhancement Proposals (PEPs)** on
[peps.python.org](https://peps.python.org). It fetches 25 PEP pages concurrently with `aiohttp`,
streams the responses through async generators, extracts each PEP's header with regular
expressions, and writes the results to JSON. The same workload is also implemented sequentially
and with threads so the three approaches can be benchmarked against each other.

For every PEP the scraper extracts:

| Field            | Example                          |
|------------------|----------------------------------|
| `number`         | `492`                            |
| `title`          | `Coroutines with async and await syntax` |
| `authors`        | `["Yury Selivanov"]` (emails removed) |
| `status`         | `Final`                          |
| `type`           | `Standards Track`                |
| `created`        | `09-Apr-2015`                    |
| `python_version` | `3.5` (or `null` if not set)     |
| `url`            | `https://peps.python.org/pep-0492/` |

---

## Setup

Requirements: **Python 3.11+**

```bash
git clone https://github.com/iToussaint/Async-Web-Scraper-with-asyncio-Fundamentals.git
cd Async-Web-Scraper-with-asyncio-Fundamentals

python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

## Usage

```bash
# Scrape all configured PEPs -> output/peps.json
python -m pep_scraper

# Benchmark sequential vs threaded vs async -> output/benchmark_report.json
python -m pep_scraper.benchmark --rounds 3

# Run the test suite
pytest
```

While scraping, every request logs when it starts and finishes. All 25 `start` lines appear
together before the first `done`, which shows that the requests run at the same time:

```text
15:02:46.593 -> start  https://peps.python.org/pep-0001/
15:02:46.593 -> start  https://peps.python.org/pep-0008/
...
15:02:46.600 -> start  https://peps.python.org/pep-3333/
15:02:47.556 <- done   https://peps.python.org/pep-0634/ (200, 0.96s)
15:02:47.564 <- done   https://peps.python.org/pep-0020/ (200, 0.97s)
...
15:02:48.396 <- done   https://peps.python.org/pep-3333/ (200, 1.80s)
15:02:48.410 Scraped 25/25 PEPs in 1.81s -> output/peps.json
```

The PEP list, timeouts, retry policy, rate limit and output location are all set in
[`pep_scraper/config.py`](pep_scraper/config.py).

---

## Project Structure

```text
pep_scraper/
├── __main__.py        # entry point: asyncio.run(...)
├── config.py          # PEP numbers, timeouts, retry / rate-limit settings, paths
├── decorators.py      # @retry and @rate_limit for async functions
├── fetcher.py         # aiohttp requests, asyncio.wait_for, create_task + gather
├── generators.py      # URL generator and async generators (stream_pages, parse_stream)
├── parser.py          # regex extraction, map / filter transformations
├── storage.py         # pathlib + asyncio.to_thread JSON writer
├── scraper.py         # end-to-end async pipeline
├── sync_scrapers.py   # sequential and threaded versions (urllib)
└── benchmark.py       # performance comparison and report
tests/                 # pytest + pytest-asyncio suite against a local aiohttp server
```

### Pipeline

```text
generate_pep_urls()  ──►  stream_pages()  ──►  parse_stream()  ──►  map / filter  ──►  save_json()
   sync generator         async generator      async generator      functional        to_thread
                          create_task +                             processing        + pathlib
                          as_completed
                              │
                              ▼
                    fetch_url() ─► @retry ─► @rate_limit ─► asyncio.wait_for(session.get)
```

---

## How asyncio Works

### Coroutines vs functions

A normal function runs from start to finish as soon as you call it. A function defined with
`async def` is a **coroutine function**: calling it does *not* run the body, it returns a
**coroutine object** that describes the work.

```python
def add(a, b):            # regular function
    return a + b

async def fetch(url):     # coroutine function
    ...

add(1, 2)        # -> 3, already executed
fetch("x")       # -> <coroutine object fetch>, nothing has run yet
await fetch("x") # runs it (only allowed inside another coroutine)
```

### The event loop

The **event loop** runs coroutines. It executes one coroutine until that coroutine reaches an
`await` on something that isn't ready yet, such as a network response. The coroutine then
*suspends* and the loop switches to another coroutine that can make progress. When the response
arrives, the suspended coroutine resumes where it left off.

All of this happens on **one thread**. Concurrency comes from overlapping the *waiting*, not from
running Python code in parallel, which is why asyncio is a great fit for I/O-bound work like
web scraping, where almost all of the time is spent waiting for the network.

`asyncio.run(main())` (in [`__main__.py`](pep_scraper/__main__.py)) creates the event loop,
runs `main()` until it finishes and then closes the loop.

### asyncio tools used in this project

| Tool | Where | Purpose |
|------|-------|---------|
| `asyncio.run()` | `__main__.py`, `benchmark.py` | Create the event loop and run the top-level coroutine |
| `async def` / `await` | everywhere | Define coroutines and suspend while waiting on I/O |
| `asyncio.create_task()` | `fetcher.fetch_all`, `generators.stream_pages` | Schedule each request on the loop immediately |
| `asyncio.gather()` | `fetcher.fetch_all` | Wait for all tasks and return results in input order |
| `asyncio.as_completed()` | `generators.stream_pages` | Yield results in the order they finish |
| `asyncio.wait_for()` | `fetcher._request` | Cancel a request that exceeds the timeout |
| `asyncio.sleep()` | `decorators` | Non-blocking waits for retry back-off and rate limiting |
| `asyncio.to_thread()` | `storage.save_json` | Run the blocking file write without stalling the loop |
| async generators + `async for` | `generators.py`, `scraper.py` | Process pages one by one as they arrive |

### Decorators for async functions

- **`@retry(attempts, delay, backoff, exceptions)`** re-runs the coroutine when one of the listed
  exceptions is raised (connection errors, timeouts, 5xx responses), waiting
  `0.5s → 1s → …` between attempts with `await asyncio.sleep`, so other requests keep running
  during the back-off. Client errors such as 404 are not retried.
- **`@rate_limit(calls, period)`** allows at most `calls` requests to *start* within any
  `period` seconds (20 per second by default) so the scraper stays polite to the server.
  Every call reserves a start slot before it awaits anything. Because the event loop runs one
  coroutine at a time, that reservation can't be interrupted, so no lock is needed.

Both decorators use `functools.wraps` and raise `TypeError` if they're applied to a function
that isn't `async def`. They are stacked as `@retry` → `@rate_limit`, so every retry attempt
also passes through the rate limiter.

---

## Performance Comparison: async vs threading vs sequential

All three versions do the same job: download the 25 PEP pages and parse them with the same
regex parser.

| Approach | Implementation | How it waits on the network |
|----------|----------------|-----------------------------|
| **Sequential** | `urllib` in a list comprehension | One request at a time; each request blocks until the previous one finishes |
| **Threaded** | `urllib` + `ThreadPoolExecutor` (10 workers) | Up to 10 blocking requests at once, one OS thread each |
| **Async** | `aiohttp` + `create_task` + `gather` | All requests in flight on a single thread; the event loop switches between them while they wait |

### Benchmark results

`python -m pep_scraper.benchmark --rounds 3`. Python 3.11.9, Windows 11, 25 URLs, rate limit
20 req/s for the async version:

| Approach   | Mean (s) | Best (s) | Pages parsed | Speedup vs sequential |
|------------|---------:|---------:|-------------:|----------------------:|
| sequential |    29.65 |    27.64 |           25 |                 1.00× |
| threaded   |     3.84 |     3.40 |           25 |                 7.72× |
| **async**  | **1.36** | **1.33** |       **25** |            **21.75×** |

### Analysis

- **Sequential is slowest** because its total time is the *sum* of every request's latency
  (about 1.2s per page here). The CPU sits idle almost the entire time, waiting on the network.
- **Threading** overlaps the waiting across 10 OS threads, so the total time is roughly
  `25 / 10 × latency`. It is limited by the pool size, and every thread costs memory and context
  switches. Each `urllib` call also opens a new TLS connection.
- **Async** has all 25 requests in flight at once on a single thread, so the total time is close
  to the *slowest single request*. Its floor is the rate limiter (20 starts per second ⇒ at least
  ~1.0s for 25 URLs). `aiohttp` also reuses connections through the shared `ClientSession`,
  which avoids repeating the TLS handshake. That accounts for part of its lead over the threaded
  `urllib` version.
- **When to use which:** asyncio scales best for many I/O-bound tasks (hundreds of URLs cost
  little extra). Threads are a good fit when you have to call blocking libraries. Neither helps
  CPU-bound work in CPython; that needs `multiprocessing`.

Network conditions vary, so expect different absolute numbers on your machine. The ranking
stays the same.

---

## Sample JSON Output

`output/peps.json` (shortened to two of the 25 records):

```json
{
  "source": "https://peps.python.org",
  "scraped_at": "2026-10-25T12:58:12+00:00",
  "elapsed_seconds": 2.113,
  "total_urls": 25,
  "succeeded": 25,
  "failed": [],
  "peps": [
    {
      "number": 8,
      "title": "Style Guide for Python Code",
      "authors": [
        "Guido van Rossum",
        "Barry Warsaw",
        "Alyssa Coghlan"
      ],
      "status": "Active",
      "type": "Process",
      "created": "05-Jul-2001",
      "python_version": null,
      "url": "https://peps.python.org/pep-0008/"
    },
    {
      "number": 492,
      "title": "Coroutines with async and await syntax",
      "authors": [
        "Yury Selivanov"
      ],
      "status": "Final",
      "type": "Standards Track",
      "created": "09-Apr-2015",
      "python_version": "3.5",
      "url": "https://peps.python.org/pep-0492/"
    }
  ]
}
```

Failed URLs are listed in `failed` with their reason (for example
`{"url": ".../pep-9999/", "error": "HTTP 404"}`) and never stop the rest of the scrape.

---

## Testing

```bash
pytest
```

The suite (44 tests, `pytest` + `pytest-asyncio`) runs against a **local aiohttp test server**,
so it needs no internet access and gives the same results every run. It covers:

- **Decorators:** retry succeeds after transient failures, gives up after the last attempt,
  ignores unlisted exceptions, backs off exponentially. Rate limiting spaces out calls and
  doesn't delay calls within budget. Both decorators reject sync functions and preserve
  function metadata.
- **Fetcher:** 200 / 404 / 503-then-200 (retry) / timeout / connection-refused handling.
  Concurrent fetching of 10 delayed pages finishes in under half the sequential time, and one
  failure does not affect the other requests.
- **Generators:** URL generator laziness, `stream_pages` yields in completion order,
  `parse_stream` pairs results with records.
- **Parser:** full field extraction, missing optional fields, non-PEP pages, HTML entities,
  author email removal, sorting.
- **Storage, pipeline, sync versions and benchmark:** directory creation, UTF-8 output,
  failure reporting, sequential vs threaded timing, speedup calculation.
