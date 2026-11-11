"""Step 1: check an uploaded file, hash it and render every page to a PNG.

Files and page images live under `<data_dir>/uploads/<sha256>/`.
"""

import hashlib
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import pypdfium2 as pdfium
from pdfminer.pdfdocument import PDFDocument, PDFPasswordIncorrect
from pdfminer.pdfpage import PDFPage
from pdfminer.pdfparser import PDFParser
from PIL import Image, ImageSequence, UnidentifiedImageError

from .config import Settings

UNSUPPORTED = "This file type is not supported. Upload a PDF, PNG, JPG or TIFF file."
DAMAGED = "This file is damaged or incomplete and cannot be read."
NO_PAGES = "This document has no readable pages."
TOO_LARGE = "This document has a page too large to process (too many pixels)."

# Leading bytes -> (kind, stored file suffix).
_SIGNATURES: list[tuple[bytes, Literal["pdf", "image"], str]] = [
    (b"%PDF-", "pdf", ".pdf"),
    (b"\x89PNG\r\n\x1a\n", "image", ".png"),
    (b"\xff\xd8\xff", "image", ".jpg"),
    (b"II*\x00", "image", ".tiff"),
    (b"MM\x00*", "image", ".tiff"),
]


class IngestError(Exception):
    """A file cannot be processed; the message is safe to show to the user."""


@dataclass(frozen=True)
class IngestedFile:
    sha256: str
    kind: Literal["pdf", "image"]
    page_images: list[Path]
    page_count: int
    source: Path  # stored copy of the uploaded file, read again by layout


def ingest(path: Path, settings: Settings) -> IngestedFile:
    path = Path(path)
    try:
        size = path.stat().st_size
        with path.open("rb") as f:
            head = f.read(16)
    except OSError as exc:
        raise IngestError("The uploaded file could not be read.") from exc

    if size > settings.max_upload_mb * 1024 * 1024:
        raise IngestError(f"This file is larger than {settings.max_upload_mb} MB.")
    match = file_kind(head)
    if match is None:
        raise IngestError(UNSUPPORTED)
    kind, suffix = match

    sha256 = sha256_of(path)
    out_dir = settings.data_dir / "uploads" / sha256
    if kind == "pdf":
        pages = _render_pdf(path, out_dir, settings)
    else:
        pages = _save_image_frames(path, out_dir, settings)

    source = out_dir / f"original{suffix}"
    if path.resolve() != source.resolve():
        shutil.copyfile(path, source)
    return IngestedFile(sha256=sha256, kind=kind, page_images=pages, page_count=len(pages), source=source)


def file_kind(head: bytes) -> tuple[Literal["pdf", "image"], str] | None:
    """(kind, stored file suffix) from a file's first bytes, or None for an unsupported type."""
    match = next((s for s in _SIGNATURES if head.startswith(s[0])), None)
    return (match[1], match[2]) if match else None


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _check_page_count(count: int, settings: Settings) -> None:
    if count == 0:
        raise IngestError(NO_PAGES)
    if count > settings.max_pages:
        raise IngestError(f"This document has {count} pages; the limit is {settings.max_pages}.")


def _check_pixels(width: int, height: int) -> None:
    """Refuse pages bigger than Pillow's decompression-bomb limit before they are decoded or rendered."""
    limit = Image.MAX_IMAGE_PIXELS
    if limit is not None and width * height > limit:
        raise IngestError(TOO_LARGE)


def _render_pdf(path: Path, out_dir: Path, settings: Settings) -> list[Path]:
    try:
        doc = pdfium.PdfDocument(path)
    except pdfium.PdfiumError as exc:
        raise IngestError(_pdf_failure_reason(path)) from exc
    try:
        _check_page_count(len(doc), settings)
        scale = settings.render_dpi / 72
        try:
            for i in range(len(doc)):
                width, height = doc[i].get_size()
                _check_pixels(round(width * scale), round(height * scale))
        except pdfium.PdfiumError as exc:
            raise IngestError(DAMAGED) from exc
        out_dir.mkdir(parents=True, exist_ok=True)
        pages = []
        for i in range(len(doc)):
            target = out_dir / f"page-{i + 1}.png"
            try:
                doc[i].render(scale=scale).to_pil().save(target)
            except pdfium.PdfiumError as exc:
                raise IngestError(DAMAGED) from exc
            pages.append(target)
        return pages
    finally:
        doc.close()


def _pdf_failure_reason(path: Path) -> str:
    """Explain why PDFium rejected a file.

    PDFium's error code is process-global and is left stale when it rejects a document with no pages,
    so a second parser (pdfminer, bundled with pdfplumber) tells the cases apart.
    """
    try:
        with path.open("rb") as f:
            doc = PDFDocument(PDFParser(f))
            has_pages = next(PDFPage.create_pages(doc), None) is not None
    except PDFPasswordIncorrect:
        return "This PDF is password-protected. Remove the password and upload it again."
    except Exception:
        return DAMAGED
    return DAMAGED if has_pages else NO_PAGES


def _save_image_frames(path: Path, out_dir: Path, settings: Settings) -> list[Path]:
    try:
        with Image.open(path) as img:
            _check_page_count(getattr(img, "n_frames", 1), settings)
            # Pillow checks only the first frame on open; later TIFF frames are checked here.
            for frame in ImageSequence.Iterator(img):
                _check_pixels(*frame.size)
            out_dir.mkdir(parents=True, exist_ok=True)
            pages = []
            for i, frame in enumerate(ImageSequence.Iterator(img)):
                target = out_dir / f"page-{i + 1}.png"
                frame.convert("RGB").save(target)
                pages.append(target)
            return pages
    except Image.DecompressionBombError as exc:
        raise IngestError(TOO_LARGE) from exc
    except (UnidentifiedImageError, OSError, SyntaxError) as exc:
        raise IngestError(DAMAGED) from exc
