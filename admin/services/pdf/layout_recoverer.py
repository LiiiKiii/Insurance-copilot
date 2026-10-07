"""Recover Markdown from a list of OCR lines using minimal heuristics.

MVP scope (deliberately small):
- Reading order = sort by Y center, group rows, sort each row by X.
- Headings = regex match against four common Chinese-policy patterns.
- Paragraphs = break on (a) large vertical gap or (b) sentence terminator.

Out of scope: two-column detection, table reconstruction, font-size headings.
"""
from __future__ import annotations

import re
from collections.abc import Sequence

from admin.services.pdf.types import OcrLine, PageMarkdown

HEADING_PATTERNS: list[tuple[re.Pattern[str], int]] = [
    (re.compile(r"^第[一二三四五六七八九十百零\d]+章"), 1),
    (re.compile(r"^第[一二三四五六七八九十百零\d]+条"), 2),
    (re.compile(r"^[（(][一二三四五六七八九十\d]+[）)]"), 3),
    (re.compile(r"^\d+[\.、]\s"), 4),
]

SENTENCE_TERMINATORS = ("。", "！", "？", ".", "!", "?")


class LayoutRecoverer:
    def recover_pages(
        self,
        all_pages_lines: Sequence[Sequence[OcrLine]],
        page_nos: Sequence[int],
    ) -> list[PageMarkdown]:
        return [
            self._recover_one(list(lines), page_no)
            for lines, page_no in zip(all_pages_lines, page_nos)
        ]

    def _recover_one(self, lines: list[OcrLine], page_no: int) -> PageMarkdown:
        if not lines:
            return PageMarkdown(
                page_no=page_no, markdown="[EMPTY PAGE]", source="ocr_empty"
            )
        sorted_lines = self._sort_reading_order(lines)
        paragraphs = self._merge_paragraphs(sorted_lines)
        md_parts = [self._format_with_headings(p) for p in paragraphs]
        return PageMarkdown(
            page_no=page_no, markdown="\n\n".join(md_parts), source="ocr"
        )

    def _sort_reading_order(self, lines: list[OcrLine]) -> list[OcrLine]:
        if not lines:
            return []
        avg_h = sum((ln.bbox[3] - ln.bbox[1]) for ln in lines) / len(lines)
        threshold = max(avg_h * 0.7, 1.0)
        sorted_y = sorted(lines, key=self._y_center)
        rows: list[list[OcrLine]] = []
        for line in sorted_y:
            if rows and abs(self._y_center(line) - self._y_center(rows[-1][0])) < threshold:
                rows[-1].append(line)
            else:
                rows.append([line])
        return [ln for row in rows for ln in sorted(row, key=lambda ln: ln.bbox[0])]

    def _merge_paragraphs(self, lines: list[OcrLine]) -> list[str]:
        paragraphs: list[str] = []
        buf: list[str] = []
        prev: OcrLine | None = None
        for line in lines:
            if prev is not None and self._is_new_paragraph(prev, line):
                if buf:
                    paragraphs.append("".join(buf))
                buf = []
            buf.append(line.text)
            prev = line
        if buf:
            paragraphs.append("".join(buf))
        return paragraphs

    @staticmethod
    def _format_with_headings(paragraph: str) -> str:
        text = paragraph.strip()
        for pat, level in HEADING_PATTERNS:
            if pat.match(text):
                return "#" * level + " " + text
        return text

    @staticmethod
    def _y_center(line: OcrLine) -> float:
        return (line.bbox[1] + line.bbox[3]) / 2

    @staticmethod
    def _is_new_paragraph(prev: OcrLine, cur: OcrLine) -> bool:
        line_height = max(prev.bbox[3] - prev.bbox[1], 1.0)
        gap = cur.bbox[1] - prev.bbox[3]
        if gap > line_height * 1.5:
            return True
        if prev.text.rstrip().endswith(SENTENCE_TERMINATORS):
            return True
        return False
