"""Writing results to disk with pathlib and non-blocking file I/O."""

import asyncio
import json
from pathlib import Path
from typing import Any

from .. import config


def _write_json(path: Path, data: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


async def save_json(data: Any, filename: str, output_dir: Path = config.OUTPUT_DIR) -> Path:
    """Serialise ``data`` to ``output_dir/filename`` without blocking the event loop.

    File writes are blocking system calls, so ``asyncio.to_thread`` runs them
    in a worker thread while the loop stays free for other tasks.
    """
    return await asyncio.to_thread(_write_json, output_dir / filename, data)
