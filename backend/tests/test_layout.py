import shutil

import pytest
from fpdf import FPDF

from pharma_dates.ingest import ingest
from pharma_dates.layout import layout_page

needs_tesseract = pytest.mark.skipif(shutil.which("tesseract") is None, reason="tesseract not installed")


def _word(layout, text):
    return next(w for w in layout.words if w.text == text)


def _assert_offsets_consistent(layout):
    for w in layout.words:
        assert layout.text[w.char_start : w.char_end] == w.text
        assert 0 <= w.bbox.x0 < w.bbox.x1 <= layout.width
        assert 0 <= w.bbox.y0 < w.bbox.y1 <= layout.height


def test_native_pdf_uses_text_layer(native_pdf, settings):
    layout = layout_page(ingest(native_pdf, settings), 1, settings)
    assert layout.n == 1
    assert layout.text_source == "pdf"
    assert "31/03/2027" in layout.text
    box = _word(layout, "31/03/2027").bbox
    assert 0 <= box.x0 < box.x1 <= layout.width
    assert 0 <= box.y0 < box.y1 <= layout.height
    # fpdf2 places the first cell at the 10 mm top-left margin: about 79 px at 200 DPI.
    assert box.y0 == pytest.approx(10 / 25.4 * settings.render_dpi, abs=30)
    _assert_offsets_consistent(layout)


def test_pdf_lines_joined_with_newlines(tmp_path, settings):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=14)
    pdf.cell(text="Manufacturing date: 01/02/2026", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(text="Expiry date: 31/03/2027")
    path = tmp_path / "two-lines.pdf"
    pdf.output(str(path))

    layout = layout_page(ingest(path, settings), 1, settings)
    assert layout.text == "Manufacturing date: 01/02/2026\nExpiry date: 31/03/2027"
    assert _word(layout, "01/02/2026").bbox.y1 <= _word(layout, "31/03/2027").bbox.y0
    _assert_offsets_consistent(layout)


@needs_tesseract
def test_pdf_with_thin_text_layer_falls_back_to_ocr(tmp_path, settings, make_pdf):
    path = make_pdf(tmp_path / "short.pdf", ["EXP 03/2027"])  # 10 non-space chars < 20
    layout = layout_page(ingest(path, settings), 1, settings)
    assert layout.text_source == "ocr"


@needs_tesseract
def test_scan_uses_ocr(scanned_png, settings):
    layout = layout_page(ingest(scanned_png, settings), 1, settings)
    assert layout.text_source == "ocr"
    assert (layout.width, layout.height) == (1400, 300)
    assert "31/03/2027" in layout.text
    box = _word(layout, "31/03/2027").bbox
    assert _word(layout, "date:").bbox.x1 < box.x0  # to the right of the label on the same line
    assert 100 <= box.y0 < box.y1 <= 200  # the text was drawn at y=110 with a 56 px font
    _assert_offsets_consistent(layout)


@needs_tesseract
def test_blank_scan_has_no_words(blank_png, settings):
    layout = layout_page(ingest(blank_png, settings), 1, settings)
    assert layout.text_source == "ocr"
    assert layout.text == ""
    assert layout.words == []


def test_page_number_out_of_range(native_pdf, settings):
    ingested = ingest(native_pdf, settings)
    with pytest.raises(IndexError):
        layout_page(ingested, 2, settings)
