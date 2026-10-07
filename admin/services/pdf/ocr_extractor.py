"""Wrap RapidOCR with an async-friendly interface.

RapidOCR is synchronous and CPU-bound, so we run each call in the default
thread pool via `loop.run_in_executor`. The engine itself is loaded once at
class scope so the ~1-2s ONNX init only happens on the first instantiation
in a process.
"""
from __future__ import annotations

import asyncio
from collections.abc import Sequence

from admin.services.pdf.types import OcrLine, PageImage


class OcrExtractor:
    _engine = None  # class-level singleton

    def __init__(self) -> None:
        if OcrExtractor._engine is None:
            from rapidocr_onnxruntime import RapidOCR
            OcrExtractor._engine = RapidOCR()
        self._engine = OcrExtractor._engine
        self._sem = asyncio.Semaphore(2)

    async def extract_pages(
        self, pages: Sequence[PageImage]
    ) -> list[list[OcrLine]]:
        loop = asyncio.get_running_loop()

        async def one(p: PageImage) -> list[OcrLine]:
            async with self._sem:
                return await loop.run_in_executor(None, self._sync_ocr, p)

        return list(await asyncio.gather(*(one(p) for p in pages)))

    def _sync_ocr(self, page: PageImage) -> list[OcrLine]:
        result, _ = self._engine(page.png_bytes)
        if not result:
            return []
        return [
            OcrLine(
                text=str(item[1]),
                bbox=self._normalize_bbox(item[0]),
                confidence=float(item[2]),
            )
            for item in result
        ]

    @staticmethod
    def _normalize_bbox(
        four_points: Sequence[Sequence[float]],
    ) -> tuple[float, float, float, float]:
        xs = [float(p[0]) for p in four_points]
        ys = [float(p[1]) for p in four_points]
        return (min(xs), min(ys), max(xs), max(ys))
