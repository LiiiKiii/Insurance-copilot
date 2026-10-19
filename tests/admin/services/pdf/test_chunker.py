"""Tests for MarkdownChunker with synthetic PageMarkdown inputs."""
from admin.services.pdf.chunker import MarkdownChunker
from admin.services.pdf.types import PageMarkdown


def page(no: int, md: str) -> PageMarkdown:
    return PageMarkdown(page_no=no, markdown=md, source="ocr")


def test_empty_input_returns_empty_list():
    assert MarkdownChunker().chunk([]) == []


def test_heading_path_tracks_chapter_then_article():
    chunker = MarkdownChunker(target_tokens=10000, min_tokens=1)
    pages = [
        page(1, "# 第一章 总则\n\n本章规定基本术语。\n\n## 第一条 投保人\n\n投保人是指与本公司签订合同的人。"),
    ]
    chunks = chunker.chunk(pages)
    assert len(chunks) == 1
    assert chunks[0].heading_path == ["第一章 总则", "第一条 投保人"]
    assert chunks[0].page_no == 1


def test_chunks_respect_token_budget():
    chunker = MarkdownChunker(target_tokens=20, min_tokens=5)
    paragraphs = "\n\n".join(["第一句话。第二句话。第三句话。"] * 10)
    pages = [page(1, "# 第一章\n\n" + paragraphs)]
    chunks = chunker.chunk(pages)
    assert len(chunks) >= 2
    for c in chunks:
        assert c.token_count > 0


def test_page_range_spans_pages():
    chunker = MarkdownChunker(target_tokens=10000, min_tokens=1)
    pages = [
        page(5, "# 第一章\n\n短段一。"),
        page(6, "短段二。"),
        page(7, "短段三。"),
    ]
    chunks = chunker.chunk(pages)
    assert len(chunks) == 1
    assert chunks[0].page_no == 5
    assert chunks[0].page_range == (5, 7)


def test_heading_pop_on_same_or_higher_level():
    chunker = MarkdownChunker(target_tokens=10000, min_tokens=1)
    pages = [
        page(1, "# 第一章\n\n## 第一条\n\n## 第二条\n\n第二条的正文。"),
    ]
    chunks = chunker.chunk(pages)
    assert chunks[0].heading_path == ["第一章", "第二条"]
