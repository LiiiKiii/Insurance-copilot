"""Tests for OcrExtractor with a fake RapidOCR engine."""
import asyncio

import pytest

from admin.services.pdf.ocr_extractor import OcrExtractor
from admin.services.pdf.types import PageImage


class FakeEngine:
    def __init__(self, scripted: list[list[list]] | None = None):
        # `scripted` is a list of pages; each page is a list of [bbox4pts, text, score]
        self._scripted = scripted or []
        self.calls = 0

    def __call__(self, _png_bytes):
        result = self._scripted[self.calls] if self.calls < len(self._scripted) else None
        self.calls += 1
        return (result, 0.0)


@pytest.fixture
def make_image():
    def _mk(no: int) -> PageImage:
        return PageImage(page_no=no, png_bytes=b"\x89PNG", width=10, height=10)
    return _mk


def test_normalize_bbox_handles_4_point_polygon():
    bbox = OcrExtractor._normalize_bbox(
        [(10, 20), (30, 22), (32, 50), (8, 48)]
    )
    assert bbox == (8, 20, 32, 50)


def test_extract_pages_returns_one_list_per_page(make_image):
    fake = FakeEngine(scripted=[
        [[[(0, 0), (10, 0), (10, 5), (0, 5)], "hello", 0.95]],
        [[[(0, 0), (10, 0), (10, 5), (0, 5)], "world", 0.90]],
    ])
    extractor = OcrExtractor.__new__(OcrExtractor)
    extractor._engine = fake
    extractor._sem = asyncio.Semaphore(2)

    pages = [make_image(1), make_image(2)]
    out = asyncio.run(extractor.extract_pages(pages))

    assert len(out) == 2
    assert out[0][0].text == "hello"
    assert out[1][0].text == "world"
    assert out[0][0].confidence == pytest.approx(0.95)


def test_extract_pages_handles_empty_result(make_image):
    fake = FakeEngine(scripted=[None])  # RapidOCR returns None for blank pages
    extractor = OcrExtractor.__new__(OcrExtractor)
    extractor._engine = fake
    extractor._sem = asyncio.Semaphore(2)

    out = asyncio.run(extractor.extract_pages([make_image(1)]))
    assert out == [[]]
