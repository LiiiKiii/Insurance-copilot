"""Sanity tests for PDF service dataclasses."""
import dataclasses

import pytest

from admin.services.pdf.types import Chunk, OcrLine, PageImage, PageMarkdown


def test_page_image_is_frozen():
    img = PageImage(page_no=1, png_bytes=b"\x89PNG", width=100, height=200)
    with pytest.raises(dataclasses.FrozenInstanceError):
        img.page_no = 2  # type: ignore[misc]


def test_ocr_line_normalized_bbox_order():
    line = OcrLine(text="hello", bbox=(0.0, 1.0, 2.0, 3.0), confidence=0.9)
    assert line.text == "hello"
    assert line.bbox == (0.0, 1.0, 2.0, 3.0)


def test_page_markdown_source_values():
    pm = PageMarkdown(page_no=1, markdown="# h", source="ocr")
    assert pm.source == "ocr"


def test_chunk_basic_fields():
    c = Chunk(
        index=0,
        content="body",
        page_no=1,
        page_range=(1, 2),
        heading_path=["第二章"],
        token_count=10,
        chunk_type="section",
    )
    assert c.page_range == (1, 2)
    assert c.heading_path == ["第二章"]
