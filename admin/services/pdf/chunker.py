"""Heading-aware Markdown chunker using a token budget.

Replaces the previous ``text_content.split()`` chunker which was broken for
Chinese text (Chinese has no whitespace, so ``split()`` returned a single
mega-"word"). This implementation walks paragraph-by-paragraph, maintains a
heading stack to attach a ``heading_path`` to every chunk, and respects a
target token budget measured with tiktoken ``cl100k_base``.
"""
from __future__ import annotations

import re
from collections.abc import Sequence

import tiktoken

from admin.services.pdf.types import Chunk, PageMarkdown

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")


class MarkdownChunker:
    def __init__(self, target_tokens: int = 512, min_tokens: int = 100) -> None:
        self._target = target_tokens
        self._min = min_tokens
        self._enc = tiktoken.get_encoding("cl100k_base")

    def chunk(self, pages: Sequence[PageMarkdown]) -> list[Chunk]:
        if not pages:
            return []

        chunks: list[Chunk] = []
        heading_stack: list[tuple[int, str]] = []
        buf: list[str] = []
        buf_tokens = 0
        buf_start_page = pages[0].page_no
        cur_page = buf_start_page

        def flush() -> None:
            nonlocal buf, buf_tokens, buf_start_page
            if buf and buf_tokens >= self._min:
                chunks.append(
                    Chunk(
                        index=len(chunks),
                        content="\n\n".join(buf),
                        page_no=buf_start_page,
                        page_range=(buf_start_page, cur_page),
                        heading_path=[h for _, h in heading_stack],
                        token_count=buf_tokens,
                        chunk_type="section",
                    )
                )
            buf = []
            buf_tokens = 0
            buf_start_page = cur_page

        for page in pages:
            cur_page = page.page_no
            if not buf:
                buf_start_page = cur_page
            for paragraph in self._split_paragraphs(page.markdown):
                heading = _HEADING_RE.match(paragraph)
                if heading is not None:
                    level = len(heading.group(1))
                    text = heading.group(2).strip()
                    while heading_stack and heading_stack[-1][0] >= level:
                        heading_stack.pop()
                    heading_stack.append((level, text))

                p_tokens = len(self._enc.encode(paragraph))
                if buf_tokens + p_tokens > self._target and buf_tokens >= self._min:
                    flush()
                    if not buf:
                        buf_start_page = cur_page
                buf.append(paragraph)
                buf_tokens += p_tokens

        # Final flush relaxes the min_tokens guard so trailing content is not lost.
        if buf:
            chunks.append(
                Chunk(
                    index=len(chunks),
                    content="\n\n".join(buf),
                    page_no=buf_start_page,
                    page_range=(buf_start_page, cur_page),
                    heading_path=[h for _, h in heading_stack],
                    token_count=buf_tokens,
                    chunk_type="section",
                )
            )
        return chunks

    @staticmethod
    def _split_paragraphs(markdown: str) -> list[str]:
        return [p.strip() for p in markdown.split("\n\n") if p.strip()]
