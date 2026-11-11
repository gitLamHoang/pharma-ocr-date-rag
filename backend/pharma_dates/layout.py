"""Step 2: words, boxes and text for one page.

Native PDF pages use the pdfplumber text layer; scans (and PDF pages with almost no text layer) use
Tesseract. Boxes are in page-image pixels. `PageLayout.text` joins words with spaces and lines with
newlines, and each word's `char_start/char_end` index into it.
"""

import logging

import pdfplumber
import pytesseract
from PIL import Image

from .config import Settings
from .ingest import IngestedFile, IngestError
from .models import BBox, PageLayout, Word

logger = logging.getLogger(__name__)

MIN_TEXT_LAYER_CHARS = 20
TESSERACT_CONFIG = "--oem 1 --psm 3"

Line = list[tuple[str, BBox]]


def layout_page(ingested: IngestedFile, n: int, settings: Settings) -> PageLayout:
    """Lay out page `n` (1-based)."""
    if not 1 <= n <= ingested.page_count:
        raise IndexError(f"page {n} out of range 1..{ingested.page_count}")
    with Image.open(ingested.page_images[n - 1]) as img:
        img.load()
    lines = _pdf_lines(ingested, n, settings) if ingested.kind == "pdf" else None
    source = "pdf"
    if lines is None:
        lines = _ocr_lines(img, settings)
        source = "ocr"
    text, words = _join(lines, img.width, img.height)
    return PageLayout(n=n, width=img.width, height=img.height, text=text, text_source=source, words=words)


def _pdf_lines(ingested: IngestedFile, n: int, settings: Settings) -> list[Line] | None:
    """Text-layer lines, or None when the page has too little text to trust (likely a scan).

    PDFium (used to render) accepts some files pdfminer cannot parse; those pages are read with OCR.
    Only the visible area of the page is used, and boxes are shifted so they start at its corner.
    """
    try:
        with pdfplumber.open(ingested.source) as pdf:
            page = pdf.pages[n - 1]
            visible = _visible_area(page)
            if visible is None:
                return None
            page = page.crop(visible, strict=False)
            if sum(1 for c in page.chars if not c["text"].isspace()) < MIN_TEXT_LAYER_CHARS:
                return None
            raw = page.extract_words()
    except Exception:
        logger.warning("text layer unreadable on page %d; using OCR", n)
        return None
    scale = settings.render_dpi / 72
    left, top = visible[0], visible[1]
    lines: list[Line] = []
    line_bottom = None
    for w in sorted(raw, key=lambda w: (w["top"], w["x0"])):
        box = BBox(
            x0=(w["x0"] - left) * scale,
            y0=(w["top"] - top) * scale,
            x1=(w["x1"] - left) * scale,
            y1=(w["bottom"] - top) * scale,
        )
        middle = (w["top"] + w["bottom"]) / 2
        if line_bottom is None or middle > line_bottom:
            lines.append([])
            line_bottom = w["bottom"]
        lines[-1].append((w["text"], box))
    return [sorted(line, key=lambda item: item[1].x0) for line in lines]


def _visible_area(page: pdfplumber.page.Page) -> tuple[float, float, float, float] | None:
    """The area PDFium renders (CropBox intersected with MediaBox), in pdfplumber coordinates.

    pdfplumber measures from the MediaBox, and its own `cropbox` is wrong on rotated pages, so the
    raw boxes are mapped with the same transforms pdfminer and pdfplumber apply to characters.
    """
    obj = page.page_obj
    mx0, mx1 = sorted(obj.mediabox[0::2])
    my0, my1 = sorted(obj.mediabox[1::2])
    cx0, cx1 = sorted(obj.cropbox[0::2])
    cy0, cy1 = sorted(obj.cropbox[1::2])
    x0, y0, x1, y1 = max(cx0, mx0), max(cy0, my0), min(cx1, mx1), min(cy1, my1)
    if x0 >= x1 or y0 >= y1:
        return None
    # pdfminer's page matrix: PDF user space -> rotated page as displayed (PDFPageInterpreter.process_page).
    a, b, c, d, e, f = {
        90: (0, -1, 1, 0, -my0, mx1),
        180: (-1, 0, 0, -1, mx1, my1),
        270: (0, 1, -1, 0, my1, -mx0),
    }.get(obj.rotate, (1, 0, 0, 1, -mx0, -my0))
    corners = [(a * x + c * y + e, b * x + d * y + f) for x in (x0, x1) for y in (y0, y1)]
    # pdfplumber's conversion of pdfminer coordinates (Page.process_object).
    mb_x0, mb_top = page.mediabox[:2]
    xs = [x + mb_x0 for x, _ in corners]
    tops = [page.height - y + mb_top for _, y in corners]
    return (min(xs), min(tops), max(xs), max(tops))


def _ocr_lines(img: Image.Image, settings: Settings) -> list[Line]:
    try:
        data = pytesseract.image_to_data(
            img, lang=settings.tesseract_langs, config=TESSERACT_CONFIG, output_type=pytesseract.Output.DICT
        )
    except pytesseract.TesseractNotFoundError as exc:
        raise IngestError("Text recognition (Tesseract) is not installed on the server.") from exc
    lines: dict[tuple[int, int, int], Line] = {}
    for i, text in enumerate(data["text"]):
        text = text.strip()
        if not text:
            continue
        left, top = data["left"][i], data["top"][i]
        box = BBox(x0=left, y0=top, x1=left + data["width"][i], y1=top + data["height"][i])
        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        lines.setdefault(key, []).append((text, box))
    return list(lines.values())


def _join(lines: list[Line], width: int, height: int) -> tuple[str, list[Word]]:
    parts: list[str] = []
    words: list[Word] = []
    pos = 0
    for li, line in enumerate(lines):
        if li:
            parts.append("\n")
            pos += 1
        for wi, (text, box) in enumerate(line):
            if wi:
                parts.append(" ")
                pos += 1
            clamped = BBox(
                x0=min(max(box.x0, 0), width),
                y0=min(max(box.y0, 0), height),
                x1=min(max(box.x1, 0), width),
                y1=min(max(box.y1, 0), height),
            )
            words.append(Word(text=text, bbox=clamped, char_start=pos, char_end=pos + len(text)))
            parts.append(text)
            pos += len(text)
    return "".join(parts), words
