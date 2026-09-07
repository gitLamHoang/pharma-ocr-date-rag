from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class OCRResult:
    text: str
    engine: str
    confidence: float | None = None


def read_document(path: str | Path, engine: str = "auto") -> OCRResult:
    """Read a document with the simplest working adapter.

    Text files are used for the public demo. Image OCR is optional because
    Tesseract and PaddleOCR require local system dependencies.
    """
    path = Path(path)
    suffix = path.suffix.lower()

    if suffix in {".txt", ".md"}:
        return OCRResult(text=path.read_text(encoding="utf-8"), engine="plain-text", confidence=1.0)

    if engine in {"auto", "tesseract"}:
        result = _try_tesseract(path)
        if result:
            return result

    if engine in {"auto", "paddle"}:
        result = _try_paddle(path)
        if result:
            return result

    raise RuntimeError(
        f"Could not OCR {path}. Install optional OCR dependencies or use a .txt sample file."
    )


def _try_tesseract(path: Path) -> OCRResult | None:
    try:
        from PIL import Image
        import pytesseract
    except ImportError:
        return None

    text = pytesseract.image_to_string(Image.open(path))
    return OCRResult(text=text, engine="tesseract", confidence=None)


def _try_paddle(path: Path) -> OCRResult | None:
    try:
        from paddleocr import PaddleOCR
    except ImportError:
        return None

    ocr = PaddleOCR(use_angle_cls=True, lang="en", show_log=False)
    rows = ocr.ocr(str(path), cls=True)
    lines: list[str] = []
    confidences: list[float] = []

    for page in rows or []:
        for row in page or []:
            text, score = row[1]
            lines.append(text)
            confidences.append(float(score))

    confidence = sum(confidences) / len(confidences) if confidences else None
    return OCRResult(text="\n".join(lines), engine="paddleocr", confidence=confidence)
