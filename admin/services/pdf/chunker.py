"""Heading-aware Markdown chunker using overlapping token windows."""
from __future__ import annotations

import os
import re
from collections.abc import Sequence

import tiktoken

from admin.services.pdf.types import Chunk, PageMarkdown

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")


class MarkdownChunker:
    def __init__(
        self,
        target_tokens: int = 512,
        min_tokens: int = 100,
        overlap_tokens: int = 0,
    ) -> None:
        if target_tokens <= 0:
            raise ValueError("target_tokens must be greater than zero")
        if min_tokens <= 0:
            raise ValueError("min_tokens must be greater than zero")
        if overlap_tokens < 0 or overlap_tokens >= target_tokens:
            raise ValueError("overlap_tokens must satisfy 0 <= overlap < target_tokens")
        self._target = target_tokens
        self._min = min_tokens
        self._overlap = overlap_tokens
        self._enc = tiktoken.get_encoding("cl100k_base")

    @classmethod
    def from_env(cls) -> "MarkdownChunker":
        target = cls._env_int("RAG_CHUNK_SIZE", 512)
        overlap = cls._env_int("RAG_CHUNK_OVERLAP", 50)
        return cls(target_tokens=target, overlap_tokens=overlap)

    def chunk(self, pages: Sequence[PageMarkdown]) -> list[Chunk]:
        if not pages:
            return []

        chunks: list[Chunk] = []
        heading_stack: list[tuple[int, str]] = []
        text_parts: list[str] = []
        char_pages: list[int] = []
        char_headings: list[list[str]] = []

        for page in pages:
            for paragraph in self._split_paragraphs(page.markdown):
                heading = _HEADING_RE.match(paragraph)
                if heading is not None:
                    level = len(heading.group(1))
                    heading_text = heading.group(2).strip()
                    while heading_stack and heading_stack[-1][0] >= level:
                        heading_stack.pop()
                    heading_stack.append((level, heading_text))
                if text_parts:
                    text_parts.append("\n\n")
                    char_pages.extend([page.page_no] * 2)
                    char_headings.extend([[h for _, h in heading_stack]] * 2)
                text_parts.append(paragraph)
                char_pages.extend([page.page_no] * len(paragraph))
                char_headings.extend([[h for _, h in heading_stack]] * len(paragraph))

        source = "".join(text_parts)
        if not source:
            return []

        start = 0
        overlap_from_previous = 0
        while start < len(source):
            end = self._max_end_for_budget(source, start, self._target)
            content = source[start:end]
            token_count = len(self._enc.encode(content))
            window_pages = char_pages[start:end]
            chunks.append(
                Chunk(
                    index=len(chunks),
                    content=content,
                    page_no=window_pages[0],
                    page_range=(min(window_pages), max(window_pages)),
                    heading_path=char_headings[end - 1],
                    token_count=token_count,
                    chunk_type="section",
                    chunk_size=self._target,
                    chunk_overlap=self._overlap,
                    overlap_from_previous_tokens=overlap_from_previous,
                )
            )
            if end == len(source):
                break
            next_start = self._overlap_start(source, start, end)
            overlap_from_previous = len(self._enc.encode(source[next_start:end]))
            start = next_start
        return chunks

    @staticmethod
    def _split_paragraphs(markdown: str) -> list[str]:
        return [part.strip() for part in markdown.split("\n\n") if part.strip()]

    @staticmethod
    def _env_int(name: str, default: int) -> int:
        raw = os.environ.get(name)
        try:
            return default if raw is None else int(raw)
        except ValueError as exc:
            raise ValueError(f"{name} must be an integer") from exc

    def _max_end_for_budget(self, text: str, start: int, budget: int) -> int:
        low, high, best = start + 1, len(text), start + 1
        while low <= high:
            middle = (low + high) // 2
            if len(self._enc.encode(text[start:middle])) <= budget:
                best = middle
                low = middle + 1
            else:
                high = middle - 1
        return best

    def _overlap_start(self, text: str, chunk_start: int, chunk_end: int) -> int:
        if self._overlap == 0:
            return chunk_end
        low, high, best = chunk_start + 1, chunk_end, chunk_end
        while low <= high:
            middle = (low + high) // 2
            if len(self._enc.encode(text[middle:chunk_end])) <= self._overlap:
                best = middle
                high = middle - 1
            else:
                low = middle + 1
        while best > chunk_start + 1:
            candidate = best - 1
            if len(self._enc.encode(text[candidate:chunk_end])) > self._overlap:
                break
            best = candidate
        while best < chunk_end and len(self._enc.encode(text[best:chunk_end])) > self._overlap:
            best += 1
        return best
