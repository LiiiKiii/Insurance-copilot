"""Per-turn retrieval mode selection for knowledge-search tool calls."""
from __future__ import annotations

from typing import Any

_KNOWLEDGE_SEARCH_TOOLS = {
    "search_knowledge_base",
    "search_sales_scripts",
    "search_best_practice",
    "search_competition_rules",
}


def apply_retrieval_mode(tool_calls: list[Any], retrieval_mode: str | None) -> None:
    if retrieval_mode not in {"keyword", "vector"}:
        return
    for tool_call in tool_calls:
        if getattr(tool_call, "name", None) not in _KNOWLEDGE_SEARCH_TOOLS:
            continue
        arguments = getattr(tool_call, "arguments", None)
        if isinstance(arguments, dict):
            arguments["search_mode"] = retrieval_mode
