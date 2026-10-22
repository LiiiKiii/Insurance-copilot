"""Synchronize built-in Markdown files into the configured knowledge database."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
import sys

from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PROJECT_ROOT))
load_dotenv(_PROJECT_ROOT / ".env")

from admin.services.builtin_knowledge import sync_builtin_knowledge
from admin.utils import get_workspace


async def _main() -> None:
    result = await sync_builtin_knowledge(get_workspace())
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(_main())
