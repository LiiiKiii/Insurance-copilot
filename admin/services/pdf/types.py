"""Frozen data contracts for the PDF ingestion pipeline.

These dataclasses define the boundaries between rasterizer, OCR extractor,
layout recoverer, chunker, and indexer. Each is immutable so that
intermediate values cannot be mutated across pipeline stages.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PageImage:
    page_no: int          # 1-based
    png_bytes: bytes
    width: int
    height: int


@dataclass(frozen=True)
class OcrLine:
    text: str
    bbox: tuple[float, float, float, float]   # (x0, y0, x1, y1)
    confidence: float


@dataclass(frozen=True)
class PageMarkdown:
    page_no: int
    markdown: str
    source: str            # "ocr" | "ocr_empty"


@dataclass(frozen=True)
class Chunk:
    index: int
    content: str
    page_no: int           # starting page
    page_range: tuple[int, int]
    heading_path: list[str]
    token_count: int
    chunk_type: str        # "section" in MVP
