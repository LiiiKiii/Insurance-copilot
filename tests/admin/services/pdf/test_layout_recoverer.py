"""Tests for LayoutRecoverer using hand-built OcrLine inputs."""
from admin.services.pdf.layout_recoverer import LayoutRecoverer
from admin.services.pdf.types import OcrLine


def line(text: str, x0: float, y0: float, x1: float, y1: float) -> OcrLine:
    return OcrLine(text=text, bbox=(x0, y0, x1, y1), confidence=0.9)


def test_empty_page_returns_empty_marker():
    rec = LayoutRecoverer()
    out = rec.recover_pages([[]], [1])
    assert out[0].markdown == "[EMPTY PAGE]"
    assert out[0].source == "ocr_empty"
    assert out[0].page_no == 1


def test_reading_order_sorts_by_row_then_column():
    rec = LayoutRecoverer()
    lines = [
        line("right", 100, 0, 200, 10),
        line("left", 0, 0, 80, 10),
        line("next", 0, 30, 80, 40),
    ]
    out = rec.recover_pages([lines], [1])
    md = out[0].markdown
    assert md.index("left") < md.index("right") < md.index("next")


def test_heading_levels_chapter_article_paren_number():
    rec = LayoutRecoverer()
    lines = [
        line("第一章 总则", 0, 0, 200, 10),
        line("第三条 本合同的相关概念", 0, 30, 200, 40),
        line("（一）投保人", 0, 60, 200, 70),
        line("1. 定义", 0, 90, 200, 100),
        line("正文段落", 0, 120, 200, 130),
    ]
    out = rec.recover_pages([lines], [1])
    md = out[0].markdown
    assert "# 第一章 总则" in md
    assert "## 第三条 本合同的相关概念" in md
    assert "### （一）投保人" in md
    assert "#### 1. 定义" in md
    assert "正文段落" in md
    assert md.index("正文段落") > md.index("#### 1. 定义")


def test_paragraph_break_on_large_gap():
    rec = LayoutRecoverer()
    lines = [
        line("第一段第一行", 0, 0, 200, 10),
        line("第一段第二行", 0, 12, 200, 22),
        # large gap (>1.5x line height)
        line("第二段第一行", 0, 60, 200, 70),
    ]
    out = rec.recover_pages([lines], [1])
    paragraphs = [p for p in out[0].markdown.split("\n\n") if p.strip()]
    assert len(paragraphs) == 2


def test_paragraph_break_on_sentence_terminator():
    rec = LayoutRecoverer()
    lines = [
        line("这是第一句话。", 0, 0, 200, 10),
        line("这是第二段。", 0, 12, 200, 22),
    ]
    out = rec.recover_pages([lines], [1])
    paragraphs = [p for p in out[0].markdown.split("\n\n") if p.strip()]
    assert len(paragraphs) == 2
