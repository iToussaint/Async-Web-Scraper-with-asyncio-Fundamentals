"""asyncio fundamentals: coroutine vs function, and running an event loop by hand.

Run with ``python -m pep_scraper.basics``. The rest of the project uses
``asyncio.run()``, which performs the same steps as ``run_on_new_loop``.
"""

import asyncio
import inspect
from collections.abc import Coroutine
from typing import Any, TypeVar

from . import config
from .fetcher import FetchResult, create_session, fetch_url
from .generators import generate_pep_urls
from .parser import parse_pep

T = TypeVar("T")


def pep_url(number: int, base_url: str = config.BASE_URL) -> str:
    """A regular function: calling it runs the body and returns the value."""
    return next(generate_pep_urls([number], base_url))


async def fetch_single_pep(number: int, base_url: str = config.BASE_URL) -> FetchResult:
    """A coroutine function: calling it only creates a coroutine object."""
    async with create_session() as session:
        return await fetch_url(session, pep_url(number, base_url))


def compare_function_and_coroutine(number: int = 8) -> dict[str, Any]:
    """Show that a function returns its result while a coroutine function returns a coroutine."""
    value = pep_url(number)              # body has already run
    coroutine = fetch_single_pep(number)  # body has NOT run: no request was sent
    try:
        return {
            "function_result": value,
            "coroutine_result_type": type(coroutine).__name__,
            "is_coroutine": inspect.iscoroutine(coroutine),
        }
    finally:
        coroutine.close()  # never awaited, so close it to avoid a "never awaited" warning


def run_on_new_loop(coroutine: Coroutine[Any, Any, T]) -> T:
    """Create an event loop, run one coroutine to completion and close the loop."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coroutine)
    finally:
        loop.close()


def main() -> None:
    comparison = compare_function_and_coroutine()
    print(f"pep_url(8)          -> {comparison['function_result']!r} (already executed)")
    print(f"fetch_single_pep(8) -> <{comparison['coroutine_result_type']} object> (nothing ran yet)\n")

    print("Running fetch_single_pep(8) on a new event loop...")
    result = run_on_new_loop(fetch_single_pep(8))
    record = parse_pep(result.html, result.url) if result.ok else None
    if record:
        print(f"PEP {record['number']}: {record['title']} ({result.elapsed:.2f}s)")
    else:
        print(f"Failed: {result.error}")


if __name__ == "__main__":
    main()
