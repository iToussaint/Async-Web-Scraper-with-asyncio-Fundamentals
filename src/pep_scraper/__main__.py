"""Run the scraper with ``python -m pep_scraper``."""

import asyncio
import logging

from .pipeline.scraper import run


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s.%(msecs)03d %(message)s", datefmt="%H:%M:%S")
    # asyncio.run creates the event loop, runs the coroutine to completion and closes the loop.
    asyncio.run(run())


if __name__ == "__main__":
    main()
