# Async Web Scraper with asyncio Fundamentals

> **Demo video (Loom):** _add your Loom link here_

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

`requirements.txt` installs the pinned dependencies and the project itself in editable mode
(`-e .`, defined in [`pyproject.toml`](pyproject.toml)), so the `pep_scraper` package can be
imported from anywhere while you edit the code in `src/`.

## Usage

```bash
# asyncio basics: coroutine vs function, explicit event loop, fetch a single PEP
python -m pep_scraper.core.basics

# Scrape all configured PEPs -> output/peps.json
python -m pep_scraper

# Benchmark sequential vs threaded vs async -> output/benchmark_report.json
python -m pep_scraper.benchmark --rounds 3

# Run the test suite
pytest
```

While scraping, every request logs when it is actually sent (`-> request`, after the rate
limiter lets it through) and when it finishes (`<- done`). The log shows concurrency and rate
limiting at work. The first 20 requests (the 20 req/s budget) are all sent within 2 ms, before any
response arrives. The remaining 5 go out one second later while earlier responses are still coming
back:

```text
16:31:25.076 -> request https://peps.python.org/pep-0001/
16:31:25.076 -> request https://peps.python.org/pep-0008/
...
16:31:25.078 -> request https://peps.python.org/pep-0654/        <- 20th request, 2 ms after the 1st
16:31:25.835 <- done    https://peps.python.org/pep-0525/ (200, 0.76s)
16:31:25.903 <- done    https://peps.python.org/pep-0380/ (200, 0.83s)
...
16:31:26.068 -> request https://peps.python.org/pep-3107/        <- rate limit: next batch 1 s later
16:31:26.068 -> request https://peps.python.org/pep-0701/
16:31:26.070 <- done    https://peps.python.org/pep-0498/ (200, 0.99s)
...
16:31:26.399 Scraped 25/25 PEPs in 1.32s -> output/peps.json
```

The PEP list, timeouts, retry policy, rate limit and output location are all set in
[`src/pep_scraper/config.py`](src/pep_scraper/config.py). Output files are written to
`output/` in the directory you run the command from.

---

## Project Structure

The project uses the standard **src layout**. The package lives in `src/pep_scraper/` and is
split into subpackages by responsibility. The tests mirror the same structure.

```text
.
├── src/pep_scraper/
│   ├── __init__.py
│   ├── __main__.py            # python -m pep_scraper: asyncio.run(...) on the pipeline
│   ├── config.py              # PEP numbers, timeouts, retry / rate-limit settings, paths
│   ├── core/                  # asyncio building blocks
│   │   ├── decorators.py      #   @retry and @rate_limit for async functions
│   │   └── basics.py          #   coroutine vs function, explicit event loop, single-URL fetch
│   ├── fetching/              # getting pages over HTTP
│   │   ├── async_fetcher.py   #   aiohttp, asyncio.wait_for, create_task + gather
│   │   └── sync_fetcher.py    #   sequential and threaded versions (http.client, keep-alive)
│   ├── processing/            # turning pages into data
│   │   ├── streams.py         #   URL generator and async generators (stream_pages, parse_stream)
│   │   └── parser.py          #   regex extraction, map / filter transformations
│   ├── storage/
│   │   └── json_storage.py    # pathlib + asyncio.to_thread JSON writer
│   ├── pipeline/
│   │   └── scraper.py         # end-to-end async pipeline
│   └── benchmark/
│       ├── __main__.py        # python -m pep_scraper.benchmark
│       └── runner.py          # performance comparison and report
├── tests/                     # pytest + pytest-asyncio, mirrors src/pep_scraper/
│   ├── conftest.py            # shared fixtures: sample pages, local aiohttp test server
│   ├── core/  fetching/  processing/  storage/  pipeline/  benchmark/
│   └── test_main.py
├── pyproject.toml             # package metadata and pytest configuration
├── requirements.txt           # pinned dependencies + editable install of the project
└── README.md
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

`asyncio.run(main())` (in [`__main__.py`](src/pep_scraper/__main__.py)) creates the event loop,
runs `main()` until it finishes and then closes the loop.
[`core/basics.py`](src/pep_scraper/core/basics.py) does the same steps by hand
(`asyncio.new_event_loop()` → `loop.run_until_complete()` → `loop.close()`). It also shows that
calling a coroutine function sends no request until the coroutine is run on the loop:

```text
$ python -m pep_scraper.core.basics
pep_url(8)          -> 'https://peps.python.org/pep-0008/' (already executed)
fetch_single_pep(8) -> <coroutine object> (nothing ran yet)

Running fetch_single_pep(8) on a new event loop...
PEP 8: Style Guide for Python Code (1.41s)
```

### asyncio tools used in this project

| Tool | Where | Purpose |
|------|-------|---------|
| `asyncio.run()` | `__main__.py`, `benchmark/runner.py` | Create the event loop and run the top-level coroutine |
| `new_event_loop()` / `run_until_complete()` | `core/basics.py` | The same, done explicitly step by step |
| `async def` / `await` | everywhere | Define coroutines and suspend while waiting on I/O |
| `asyncio.create_task()` | `async_fetcher.fetch_all`, `streams.stream_pages` | Schedule each request on the loop immediately |
| `asyncio.gather()` | `async_fetcher.fetch_all` | Wait for all tasks and return results in input order |
| `asyncio.as_completed()` | `streams.stream_pages` | Yield results in the order they finish |
| `asyncio.wait_for()` | `async_fetcher._request` | Cancel a request that exceeds the timeout |
| `asyncio.sleep()` | `core/decorators.py` | Non-blocking waits for retry back-off and rate limiting |
| `asyncio.to_thread()` | `json_storage.save_json` | Run the blocking file write without stalling the loop |
| async generators + `async for` | `processing/streams.py`, `pipeline/scraper.py` | Process pages one by one as they arrive |

### Decorators for async functions

- **`@retry(attempts, delay, backoff, exceptions)`** re-runs the coroutine when one of the listed
  exceptions is raised (connection errors, timeouts, 5xx responses), waiting
  `0.5s → 1s → …` between attempts with `await asyncio.sleep`, so other requests keep running
  during the back-off. Client errors such as 404 are not retried.
- **`@rate_limit(calls, period)`** allows at most `calls` requests to *start* within any
  `period` seconds (20 per second by default) so the scraper stays polite to the server.
  Every call reserves a start slot before it awaits anything. Because the event loop runs one
  coroutine at a time, that reservation can't be interrupted, so no lock is needed.
  `reset()` clears the history so a new run starts with a full budget.

Both decorators use `functools.wraps` and raise `TypeError` if they're applied to a function
that isn't `async def`. They are stacked as `@retry` → `@rate_limit`, so every retry attempt
also passes through the rate limiter.

---

## Performance Comparison: async vs threading vs sequential

All three versions do the same job: download the 25 PEP pages and parse them with the same
regex parser. To make the comparison fair, all three reuse connections (keep-alive) and request
gzip-compressed pages, so they send the same requests and download the same bytes. The only
difference is how they wait on the network.

| Approach | Implementation | How it waits on the network |
|----------|----------------|-----------------------------|
| **Sequential** | `http.client`, one kept-alive connection | One request at a time; each request blocks until the previous one finishes |
| **Threaded** | `http.client` + `ThreadPoolExecutor` (10 workers), one connection per thread | Up to 10 blocking requests at once, one OS thread each |
| **Async** | `aiohttp` + `create_task` + `gather`, one shared `ClientSession` | All requests in flight on a single thread; the event loop switches between them while they wait |

The async version also has a handicap the others don't: the `@rate_limit` decorator lets at
most 20 requests start per second, so its 25 URLs can never finish in under ~1 s.

### Benchmark results

`python -m pep_scraper.benchmark --rounds 5`. Python 3.11.9, Windows 11, home internet
connection, 25 URLs:

| Approach   | Mean (s) | Best (s) | Pages parsed (last round) | Speedup (mean) | Speedup (best) |
|------------|---------:|---------:|--------------------------:|---------------:|---------------:|
| sequential |    14.26 |     9.20 |                        25 |          1.00× |          1.00× |
| threaded   |     5.98 |     1.99 |                        23 |          2.38× |          4.63× |
| **async**  | **4.88** | **1.36** |                    **25** |      **2.92×** |      **6.78×** |

Individual rounds (seconds):

| Round | Sequential | Threaded | Async |
|------:|-----------:|---------:|------:|
| 1 | 15.65 | 9.75 | 1.36 |
| 2 | 9.41 | 1.99 | 1.93 |
| 3 | 9.20 | 2.12 | 2.69 |
| 4 | 9.21 | 2.42 | 5.84 |
| 5 | 27.82 | 13.62 | 12.58 |

### Analysis

- **Sequential is slowest** because its total time is the *sum* of every request's latency
  (about 0.37 s per page on a good round). The CPU sits idle almost the entire time, waiting on
  the network.
- **Threading** overlaps the waiting across 10 OS threads, so a round takes roughly
  `25 / 10 × latency`. It is limited by the pool size, and every thread costs memory and a
  context switch.
- **Async** has all requests in flight at once on one thread, so a round takes about as long as
  the *slowest single request*, plus the rate limiter's ~1 s floor. Its best round (1.36 s) was
  the fastest of all three approaches, despite the rate limit.
- **The network matters as much as the code.** Round 5 hit a slowdown on the connection that
  slowed every approach 2-3×, and in round 1 a few slow pages held the threaded version back.
  When the bottleneck is bandwidth or a slow server, no concurrency model can beat it, so async
  and threading end up close. That is why both the mean and the best time are reported.
- **Reliability:** in round 5 the threaded version lost 2 pages to the 10 s timeout. The async
  version recovered from the same conditions because `@retry` re-sends failed requests. (The sync
  versions only exist for the comparison, so they have no retry.)
- **When to use which:** asyncio scales best for many I/O-bound tasks; hundreds of URLs cost
  little extra and need no extra threads. Threads are a good fit when you must call blocking
  libraries. Neither helps CPU-bound work in CPython; that needs `multiprocessing`.

Absolute numbers depend on your connection, so expect different values on your machine.

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

The suite (58 tests, `pytest` + `pytest-asyncio`) runs against a **local aiohttp test server**,
so it needs no internet access. It passes on Python 3.11.9 and 3.14.8.

To keep the tests stable, concurrency is not checked with timings. Instead, the test server
counts how many requests it is handling at the same moment, which gives an exact answer:
async = all requests in flight at once, threaded = at most the pool size, sequential = exactly 1.
Retry back-off and rate-limit delays are recorded instead of actually slept, and every test starts
with an empty rate-limit window.

What is covered:

- **asyncio basics:** a function runs immediately while a coroutine does not; the explicit
  event loop runs to completion and is closed; single-URL fetch; the demo output.
- **Decorators:** retry succeeds after transient failures, gives up after the last attempt,
  ignores unlisted exceptions, backs off exponentially (`0.5 → 1 → 2`) and doesn't wait after
  success. Rate limiting delays calls beyond the budget, doesn't delay calls within it, and
  `reset()` works even when stacked under `@retry`. Both decorators reject sync functions,
  preserve metadata and validate their arguments.
- **Fetcher:** 200 / 404 (not retried) / 503-then-200 (retried with the configured back-off,
  3 requests logged) / timeout / connection refused. `fetch_all` runs every request at once,
  keeps input order and isolates failures.
- **Generators:** URL generator laziness, `stream_pages` yields in completion order,
  `parse_stream` pairs results with records.
- **Parser:** full field extraction, missing optional fields, non-PEP pages, HTML entities,
  author email removal, sorting.
- **Sync versions:** pages, gzip decoding, HTTP errors, timeouts, connection errors, reuse of
  kept-alive connections, reconnecting once after a stale connection.
- **Storage, pipeline and entry points:** directory creation, UTF-8 output, failure reporting,
  `python -m pep_scraper`, `python -m pep_scraper.core.basics` and `python -m pep_scraper.benchmark`
  (table printed, report saved).
