import shutil

import pypdfium2 as pdfium
import pytest
from fpdf import FPDF
from PIL import Image, ImageDraw, ImageFont, ImageOps

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


@needs_tesseract
def test_unparseable_text_layer_falls_back_to_ocr(native_pdf, settings, monkeypatch):
    ingested = ingest(native_pdf, settings)

    def broken_open(*args, **kwargs):
        raise ValueError("pdfminer could not parse this file")

    monkeypatch.setattr("pharma_dates.layout.pdfplumber.open", broken_open)
    layout = layout_page(ingested, 1, settings)
    assert layout.text_source == "ocr"


def test_cropped_pdf_boxes_are_relative_to_the_visible_area(native_pdf, tmp_path, settings):
    # Crop 20 pt off the left, 100 pt off the bottom and 10 pt off the top (PDF origin is bottom-left).
    doc = pdfium.PdfDocument(native_pdf)
    page_width, page_height = doc[0].get_size()
    uncropped = layout_page(ingest(native_pdf, settings), 1, settings)
    doc[0].set_cropbox(20, 100, page_width, page_height - 10)
    path = tmp_path / "cropped.pdf"
    doc.save(str(path))
    doc.close()

    layout = layout_page(ingest(path, settings), 1, settings)
    assert layout.text_source == "pdf"
    scale = settings.render_dpi / 72
    before, after = _word(uncropped, "31/03/2027").bbox, _word(layout, "31/03/2027").bbox
    assert after.x0 == pytest.approx(before.x0 - 20 * scale, abs=1)
    assert after.y0 == pytest.approx(before.y0 - 10 * scale, abs=1)
    assert after.x1 - after.x0 == pytest.approx(before.x1 - before.x0, abs=1)
    _assert_offsets_consistent(layout)


def test_text_outside_cropbox_is_ignored(tmp_path, settings):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=14)
    pdf.cell(text="Expiry date: 31/03/2027")  # near the top, cropped away below
    pdf.set_xy(10, 200)
    pdf.cell(text="Batch released by QA on 01/02/2026")
    path = tmp_path / "hidden.pdf"
    pdf.output(str(path))
    doc = pdfium.PdfDocument(path)
    page_width, page_height = doc[0].get_size()
    doc[0].set_cropbox(0, 0, page_width, page_height - 100)  # hide the top 100 pt
    cropped = tmp_path / "hidden-cropped.pdf"
    doc.save(str(cropped))
    doc.close()

    layout = layout_page(ingest(cropped, settings), 1, settings)
    assert layout.text_source == "pdf"
    assert "31/03/2027" not in layout.text
    assert "01/02/2026" in layout.text
    _assert_offsets_consistent(layout)


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_word_boxes_match_rendered_ink_on_rotated_cropped_pages(tmp_path, settings, make_pdf, rotation):
    source = make_pdf(tmp_path / "source.pdf", ["Expiry date: 31/03/2027 for batch A1"])
    doc = pdfium.PdfDocument(source)
    page = doc[0]
    width, height = page.get_size()
    page.set_mediabox(-20, 30, width - 20, height + 30)  # MediaBox not at the origin
    page.set_cropbox(0, 70, width - 50, height - 10)
    page.set_rotation(rotation)
    path = tmp_path / f"rotated-{rotation}.pdf"
    doc.save(str(path))
    doc.close()

    ingested = ingest(path, settings)
    layout = layout_page(ingested, 1, settings)
    assert layout.text_source == "pdf"
    with Image.open(ingested.page_images[0]) as img:
        ink = ImageOps.invert(img.convert("L")).getbbox()
    boxes = [w.bbox for w in layout.words]
    words = (
        min(b.x0 for b in boxes),
        min(b.y0 for b in boxes),
        max(b.x1 for b in boxes),
        max(b.y1 for b in boxes),
    )
    # Word boxes span the font's line height, so they reach a few pixels past the glyph ink.
    assert words == pytest.approx(ink, abs=10)


@needs_tesseract
def test_ocr_words_carry_confidence_and_pdf_words_do_not(scanned_png, native_pdf, settings):
    scan = layout_page(ingest(scanned_png, settings), 1, settings)
    assert scan.words and all(0 <= w.confidence <= 1 for w in scan.words)
    native = layout_page(ingest(native_pdf, settings), 1, settings)
    assert all(w.confidence is None for w in native.words)


def _scan_with_stamp(tmp_path, stamp: str, body_lines: int = 0):
    scan = Image.new("RGB", (1654, 2339), "white")  # A4 at 200 DPI
    ImageDraw.Draw(scan).text(
        (150, 600), "Expiry date: 31/03/2027", fill="black", font=ImageFont.load_default(size=56)
    )
    scan.save(tmp_path / "scan-a4.png")
    pdf = FPDF()
    pdf.add_page()
    pdf.image(str(tmp_path / "scan-a4.png"), x=0, y=0, w=pdf.w, h=pdf.h)  # the scanned body, full page
    pdf.set_font("Helvetica", size=8)
    pdf.set_xy(10, 5)
    pdf.cell(text=stamp)  # a DMS header stamped on top of the scan
    for i in range(body_lines):
        pdf.set_xy(10, 20 + i * 6)
        pdf.cell(text=f"Line {i}: native text over a letterhead background image, Expiry date: 31/03/2027")
    path = tmp_path / "stamped.pdf"
    pdf.output(str(path))
    return path


@needs_tesseract
def test_scan_with_a_stamped_text_header_is_still_ocrd(tmp_path, settings):
    path = _scan_with_stamp(tmp_path, "Page 1 of 5   Doc No QA-12345   Printed copy")
    layout = layout_page(ingest(path, settings), 1, settings)
    assert layout.text_source == "ocr"
    assert "31/03/2027" in layout.text


def test_native_text_over_a_background_image_uses_the_text_layer(tmp_path, settings):
    path = _scan_with_stamp(tmp_path, "Letterhead", body_lines=30)
    layout = layout_page(ingest(path, settings), 1, settings)
    assert layout.text_source == "pdf"
