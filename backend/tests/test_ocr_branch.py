# ============================================================
# parse_pdf OCR 分支测试：扫描页识别 / 文本页不触发 / OCR 禁用降级
# ============================================================

import fitz  # PyMuPDF

from app.rag.ingestion import DocumentParser


def _make_pdf(path, with_text: bool):
    """生成单页 PDF：with_text=True 有文本层，False 为纯图片页（无文本层）。

    注意：PyMuPDF 默认 Helvetica 字体不含中文字形，插入中文无法提取文本，
    测试文本层场景一律用 ASCII。
    """
    doc = fitz.open()
    page = doc.new_page()
    if with_text:
        page.insert_text((72, 72), "ESP32 Getting Started Guide")
    else:
        # 纯图片页：插入像素图，页面没有文本层
        pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 120, 60))
        pix.clear_with(255)
        page.insert_image(page.rect, pixmap=pix)
    doc.save(str(path))
    doc.close()


class TestParsePdfOcrBranch:
    def test_scanned_page_uses_ocr(self, tmp_path, monkeypatch):
        pdf = tmp_path / "scanned.pdf"
        _make_pdf(pdf, with_text=False)

        calls = []

        def fake_ocr(pixmap_bytes, width, height):
            calls.append((len(pixmap_bytes), width, height))
            return "OCR 识别出的扫描件文本"

        monkeypatch.setattr("app.rag.ocr.ocr_page_image", fake_ocr)
        full_text, page_count = DocumentParser.parse_pdf(str(pdf))
        assert page_count == 1
        assert "[第1页]" in full_text
        assert "OCR 识别出的扫描件文本" in full_text
        assert len(calls) == 1

    def test_text_page_skips_ocr(self, tmp_path, monkeypatch):
        pdf = tmp_path / "text.pdf"
        _make_pdf(pdf, with_text=True)

        def fake_ocr(*args, **kwargs):
            raise AssertionError("有文本层的页面不应触发 OCR")

        monkeypatch.setattr("app.rag.ocr.ocr_page_image", fake_ocr)
        full_text, _ = DocumentParser.parse_pdf(str(pdf))
        assert "[第1页]" in full_text
        assert "ESP32 Getting Started Guide" in full_text

    def test_ocr_disabled_returns_empty_for_scanned(self, tmp_path, monkeypatch):
        pdf = tmp_path / "scanned2.pdf"
        _make_pdf(pdf, with_text=False)

        monkeypatch.setattr("app.rag.ocr.ocr_page_image",
                            lambda *a, **k: "不应被调用")
        from app.core.config import settings

        monkeypatch.setattr(settings, "OCR_ENABLED", False)
        full_text, _ = DocumentParser.parse_pdf(str(pdf))
        assert full_text.strip() == ""  # 扫描页无 OCR 时返回空（走既有空文档异常路径）

    def test_ocr_failure_degrades_to_empty(self, tmp_path, monkeypatch):
        pdf = tmp_path / "scanned3.pdf"
        _make_pdf(pdf, with_text=False)

        monkeypatch.setattr("app.rag.ocr.ocr_page_image",
                            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("OCR 崩了")))
        full_text, page_count = DocumentParser.parse_pdf(str(pdf))
        assert page_count == 1
        assert full_text.strip() == ""


class TestOcrLineGrouping:
    def test_group_lines_sorts_by_position(self):
        from app.rag.ocr import _group_lines

        result = [
            ([[0, 20], [100, 20], [100, 30], [0, 30]], "第二行", 0.9),
            ([[0, 0], [100, 0], [100, 10], [0, 10]], "第一行", 0.9),
            ([[0, 10], [50, 10], [50, 20], [0, 20]], "同行后段", 0.8),
        ]
        lines = _group_lines(result)
        assert lines[0].startswith("第一行")
        assert lines[-1] == "第二行"
