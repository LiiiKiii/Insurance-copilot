"""Structure-aware chunking for the repository's built-in Markdown corpus."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass

import tiktoken

from admin.services.pdf.types import Chunk

_HEADING_RE = re.compile(r"^(#{1,6})\s+(\S.*?)\s*$")
_PAGE_RE = re.compile(r"^\s*(?:第\s*(\d+)\s*頁|頁\s*(\d+)\s*/\s*\d+)\s*$")


@dataclass(frozen=True)
class StructuredMarkdownChunk:
    chunk: Chunk
    section_title: str
    chunk_strategy: str


@dataclass(frozen=True)
class _Section:
    title: str
    heading_path: list[str]
    body: str
    page_no: int = 1


class StructuredMarkdownChunker:
    def __init__(self, target_tokens: int = 512) -> None:
        if target_tokens <= 0:
            raise ValueError("target_tokens must be greater than zero")
        self._target = target_tokens
        self._enc = tiktoken.get_encoding("cl100k_base")

    @property
    def target_tokens(self) -> int:
        return self._target

    @classmethod
    def from_env(cls) -> "StructuredMarkdownChunker":
        raw = os.environ.get("RAG_CHUNK_SIZE", "512")
        try:
            return cls(target_tokens=int(raw))
        except ValueError as exc:
            raise ValueError("RAG_CHUNK_SIZE must be an integer") from exc

    def chunk(self, markdown: str) -> list[StructuredMarkdownChunk]:
        sections = self._sections(markdown)
        pieces: list[StructuredMarkdownChunk] = []
        for section in sections:
            prefix = "\n\n".join(
                f"{'#' * min(index + 1, 6)} {title}"
                for index, title in enumerate(section.heading_path)
            )
            paragraphs = [
                value.strip()
                for value in re.split(r"\n\s*\n", section.body)
                if value.strip()
            ]
            if not paragraphs:
                paragraphs = [section.body.strip()] if section.body.strip() else []
            current: list[str] = []
            rendered: list[str] = []
            for paragraph in paragraphs:
                candidate = self._compose(prefix, [*current, paragraph])
                if current and self._tokens(candidate) > self._target:
                    rendered.append(self._compose(prefix, current))
                    current = []
                if self._tokens(self._compose(prefix, [paragraph])) > self._target:
                    rendered.extend(self._split_oversized(prefix, paragraph))
                else:
                    current.append(paragraph)
            if current:
                rendered.append(self._compose(prefix, current))
            for content in rendered:
                chunk = Chunk(
                    index=len(pieces),
                    content=content,
                    page_no=section.page_no,
                    page_range=(section.page_no, section.page_no),
                    heading_path=section.heading_path,
                    token_count=self._tokens(content),
                    chunk_type="markdown_section",
                    chunk_size=self._target,
                    chunk_overlap=0,
                    overlap_from_previous_tokens=0,
                )
                pieces.append(
                    StructuredMarkdownChunk(
                        chunk=chunk,
                        section_title=section.title,
                        chunk_strategy="markdown_heading_section",
                    )
                )
        return pieces

    def _sections(self, markdown: str) -> list[_Section]:
        lines = markdown.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        heading_stack: list[tuple[int, str]] = []
        sections: list[_Section] = []
        body: list[str] = []
        title = "Knowledge document"
        page_no = 1

        def flush() -> None:
            nonlocal body
            content = "\n".join(body).strip()
            if content or heading_stack:
                path = [item[1] for item in heading_stack] or [title]
                sections.append(_Section(path[-1], path, content, page_no))
            body = []

        for line in lines:
            heading = _HEADING_RE.match(line)
            page = _PAGE_RE.match(line)
            if heading:
                flush()
                level = len(heading.group(1))
                value = heading.group(2).strip()
                while heading_stack and heading_stack[-1][0] >= level:
                    heading_stack.pop()
                heading_stack.append((level, value))
                if level == 1:
                    title = value
            elif page:
                flush()
                page_no = int(page.group(1) or page.group(2) or 1)
                body.append(line)
            else:
                body.append(line)
        flush()
        return sections

    def _split_oversized(self, prefix: str, text: str) -> list[str]:
        fragments: list[str] = []
        start = 0
        while start < len(text):
            low, high, best = start + 1, len(text), start + 1
            while low <= high:
                middle = (low + high) // 2
                if self._tokens(self._compose(prefix, [text[start:middle]])) <= self._target:
                    best = middle
                    low = middle + 1
                else:
                    high = middle - 1
            fragments.append(self._compose(prefix, [text[start:best]]))
            start = best
        return fragments

    @staticmethod
    def _compose(prefix: str, paragraphs: list[str]) -> str:
        body = "\n\n".join(part.strip() for part in paragraphs if part.strip())
        return f"{prefix}\n\n{body}".strip()

    def _tokens(self, text: str) -> int:
        return len(self._enc.encode(text))
