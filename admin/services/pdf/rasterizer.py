"""Rasterize a PDF file to per-page PNG bytes using PyMuPDF.

The rasterizer opens the PDF from a path (not from bytes) so that the
underlying file is memory-mapped, and releases each Pixmap immediately
after capturing its PNG bytes to keep peak memory bounded by one page.
"""
from __future__ import annotations

from pathlib import Path

import fitz

from admin.services.pdf.types import PageImage


class PdfRasterizer:
    def __init__(self, dpi: int = 200, max_side: int = 2048) -> None:
        self._dpi = dpi
        self._max_side = max_side

    def rasterize(self, pdf_path: Path) -> list[PageImage]:
        out: list[PageImage] = []
        with fitz.open(str(pdf_path)) as doc:
            for index, page in enumerate(doc, start=1):
                scale = self._dpi / 72
                rect = page.rect
                long_side = max(rect.width, rect.height) * scale
                if long_side > self._max_side:
                    scale = self._max_side / max(rect.width, rect.height)
                mat = fitz.Matrix(scale, scale)
                pix = page.get_pixmap(matrix=mat, alpha=False)
                out.append(
                    PageImage(
                        page_no=index,
                        png_bytes=pix.tobytes("png"),
                        width=pix.width,
                        height=pix.height,
                    )
                )
                pix = None  # release immediately
        return out
