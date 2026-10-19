"""Tests for PdfRasterizer using a synthesized in-memory PDF."""
from pathlib import Path

import fitz
import pytest

from admin.services.pdf.rasterizer import PdfRasterizer


@pytest.fixture
def two_page_pdf(tmp_path: Path) -> Path:
    """Create a real 2-page PDF with PyMuPDF; no fixture binary needed."""
    doc = fitz.open()
    page1 = doc.new_page(width=595, height=842)   # A4
    page1.insert_text((72, 72), "Hello page 1")
    page2 = doc.new_page(width=595, height=842)
    page2.insert_text((72, 72), "Hello page 2")
    out = tmp_path / "sample.pdf"
    doc.save(str(out))
    doc.close()
    return out


def test_rasterize_returns_one_image_per_page(two_page_pdf: Path) -> None:
    raster = PdfRasterizer(dpi=100)   # smaller DPI for faster tests
    pages = raster.rasterize(two_page_pdf)
    assert len(pages) == 2
    assert [p.page_no for p in pages] == [1, 2]


def test_rasterize_png_bytes_are_nonempty(two_page_pdf: Path) -> None:
    raster = PdfRasterizer(dpi=100)
    pages = raster.rasterize(two_page_pdf)
    for p in pages:
        assert p.png_bytes.startswith(b"\x89PNG")
        assert p.width > 0 and p.height > 0


def test_rasterize_respects_max_side(two_page_pdf: Path) -> None:
    # max_side=200 forces aggressive downscale of A4 at any reasonable dpi
    raster = PdfRasterizer(dpi=300, max_side=200)
    pages = raster.rasterize(two_page_pdf)
    for p in pages:
        assert max(p.width, p.height) <= 200
