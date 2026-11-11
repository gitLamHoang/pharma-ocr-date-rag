import hashlib
from pathlib import Path

import pypdfium2 as pdfium
import pytest
from PIL import Image

from pharma_dates.ingest import IngestError, ingest


def test_pdf_pages_rendered_to_uploads(native_pdf, settings):
    ingested = ingest(native_pdf, settings)
    assert ingested.kind == "pdf"
    assert ingested.page_count == 1
    page = settings.data_dir / "uploads" / ingested.sha256 / "page-1.png"
    assert ingested.page_images == [page]
    with Image.open(page) as img:
        # A4 at 200 DPI is about 1654 x 2339 px.
        assert abs(img.width - 210 / 25.4 * settings.render_dpi) < 3
    assert ingested.source.read_bytes() == native_pdf.read_bytes()


def test_image_ingested_as_one_page(scanned_png, settings):
    ingested = ingest(scanned_png, settings)
    assert ingested.kind == "image"
    assert ingested.page_count == 1
    with Image.open(ingested.page_images[0]) as img:
        assert img.size == (1400, 300)


def test_multi_frame_tiff_is_one_page_per_frame(tmp_path, settings):
    path = tmp_path / "two.tiff"
    frames = [Image.new("RGB", (200, 100), c) for c in ("white", "gray")]
    frames[0].save(path, save_all=True, append_images=frames[1:])
    ingested = ingest(path, settings)
    assert ingested.page_count == 2
    assert [p.name for p in ingested.page_images] == ["page-1.png", "page-2.png"]


def test_sha256_stable(native_pdf, scanned_png, settings):
    first = ingest(native_pdf, settings)
    second = ingest(native_pdf, settings)
    assert first.sha256 == second.sha256 == hashlib.sha256(native_pdf.read_bytes()).hexdigest()
    assert ingest(scanned_png, settings).sha256 != first.sha256


def test_rejects_oversize_and_bad_type(tmp_path, native_pdf, settings):
    text_file = tmp_path / "notes.pdf"
    text_file.write_text("just some text, not a document")
    with pytest.raises(IngestError, match="PDF, PNG, JPG or TIFF"):
        ingest(text_file, settings)

    empty = tmp_path / "empty.png"
    empty.write_bytes(b"")
    with pytest.raises(IngestError, match="PDF, PNG, JPG or TIFF"):
        ingest(empty, settings)

    tiny_limit = settings.model_copy(update={"max_upload_mb": 0})
    with pytest.raises(IngestError, match="larger than 0 MB"):
        ingest(native_pdf, tiny_limit)


def test_encrypted_pdf_raises_ingest_error(encrypted_pdf, settings):
    with pytest.raises(IngestError, match="password"):
        ingest(encrypted_pdf, settings)


def test_corrupt_pdf_raises_ingest_error(corrupt_pdf, settings):
    with pytest.raises(IngestError, match="damaged"):
        ingest(corrupt_pdf, settings)


def test_corrupt_image_raises_ingest_error(tmp_path, settings):
    path = tmp_path / "broken.png"
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 40)
    with pytest.raises(IngestError, match="damaged"):
        ingest(path, settings)


def test_zero_page_pdf_raises(tmp_path, encrypted_pdf, settings):
    path = tmp_path / "zero.pdf"
    pdfium.PdfDocument.new().save(str(path))
    # PDFium leaves its global error code stale for empty documents: a password failure just before
    # must not make the empty PDF look password-protected.
    with pytest.raises(IngestError, match="password"):
        ingest(encrypted_pdf, settings)
    with pytest.raises(IngestError, match="no readable pages"):
        ingest(path, settings)


def test_too_many_pages_raises(tmp_path, settings, make_pdf):
    path = make_pdf(tmp_path / "three.pdf", ["one", "two", "three"])
    limited = settings.model_copy(update={"max_pages": 2})
    with pytest.raises(IngestError, match="3 pages; the limit is 2"):
        ingest(path, limited)
    assert list(settings.data_dir.glob("uploads/*/page-*.png")) == []


def test_missing_file_raises_ingest_error(tmp_path: Path, settings):
    with pytest.raises(IngestError):
        ingest(tmp_path / "nope.pdf", settings)


def test_huge_pixel_image_raises_ingest_error(blank_png, settings, monkeypatch):
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 1000)
    with pytest.raises(IngestError, match="too large"):
        ingest(blank_png, settings)
