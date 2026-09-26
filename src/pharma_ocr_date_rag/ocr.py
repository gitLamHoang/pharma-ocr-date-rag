from __future__ import annotations

import math
import re
import shlex
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class OCRResult:
    text: str
    engine: str
    confidence: float | None = None


class OCRUnavailable(RuntimeError):
    """An optional package, executable, or requested language pack is missing."""


class OCRExecutionError(RuntimeError):
    """An installed OCR backend failed to read or recognize the input."""


def read_document(path: str | Path, engine: str = "auto") -> OCRResult:
    """Read text directly, or try English OCR; use read_tesseract for other packs."""
    if engine not in {"auto", "tesseract", "paddle"}:
        raise ValueError(f"Unknown OCR engine: {engine}")
    path = Path(path)
    suffix = path.suffix.lower()

    if suffix in {".txt", ".md"}:
        return OCRResult(text=path.read_text(encoding="utf-8"), engine="plain-text", confidence=1.0)

    unavailable = []
    if engine in {"auto", "tesseract"}:
        try:
            return read_tesseract(path)
        except OCRUnavailable as exc:
            if engine == "tesseract":
                raise
            unavailable.append(str(exc))

    if engine in {"auto", "paddle"}:
        result = _try_paddle(path)
        if result:
            return result
        unavailable.append("PaddleOCR Python package is not installed (adapter is unverified).")

    raise OCRUnavailable(" ".join(unavailable) + " Use a UTF-8 .txt sample to run without OCR.")


def _tesseract_dependencies():
    try:
        import pytesseract
        from PIL import Image
    except ImportError as exc:
        raise OCRUnavailable('Install the Python adapter with pip install -e ".[tesseract]".') from exc
    return pytesseract, Image


def _data_config(tessdata_dir: str | Path | None) -> str:
    if tessdata_dir is None:
        return ""
    directory = Path(tessdata_dir).resolve()
    if not directory.is_dir():
        raise OCRUnavailable(f"Tesseract language directory does not exist: {directory}")
    return f"--tessdata-dir {shlex.quote(str(directory))}"


def tesseract_info(tessdata_dir: str | Path | None = None) -> dict:
    """Probe the selected executable and language directory, without recognizing an image."""
    pytesseract, _ = _tesseract_dependencies()
    config = _data_config(tessdata_dir)
    try:
        return {
            "engine": str(pytesseract.get_tesseract_version()),
            "adapter": pytesseract.__version__,
            "languages": sorted(pytesseract.get_languages(config=config)),
        }
    except pytesseract.TesseractNotFoundError as exc:
        raise OCRUnavailable("Tesseract executable is missing; install it and add it to PATH.") from exc
    except (OSError, RuntimeError) as exc:
        raise OCRExecutionError(f"Tesseract environment check failed: {exc}") from exc


def read_tesseract(
    path: str | Path,
    *,
    language: str = "eng",
    psm: int = 3,
    timeout: float = 30,
    tessdata_dir: str | Path | None = None,
) -> OCRResult:
    """Recognize image pixels using explicit Tesseract packs (e.g. fra or eng+fra).

    OCR language names are independent of the date extractor's language/date order.
    No confidence is invented from a successful process exit.
    """
    if not re.fullmatch(r"[A-Za-z0-9_]+(?:\+[A-Za-z0-9_]+)*", language):
        raise ValueError("language must contain Tesseract pack names, such as eng or eng+fra")
    if isinstance(psm, bool) or not isinstance(psm, int) or not 3 <= psm <= 13:
        raise ValueError("psm must be an integer from 3 to 13")
    if isinstance(timeout, bool) or not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("timeout must be a positive finite number of seconds")
    pytesseract, Image = _tesseract_dependencies()
    installed = tesseract_info(tessdata_dir)["languages"]
    missing = sorted(set(language.split("+")) - set(installed))
    if missing:
        raise OCRUnavailable(
            f"Missing Tesseract language packs: {', '.join(missing)}. Installed: {', '.join(installed)}"
        )
    config = f"{_data_config(tessdata_dir)} --oem 1 --psm {psm}".strip()
    try:
        with Image.open(path) as image:
            text = pytesseract.image_to_string(image, lang=language, config=config, timeout=timeout)
    except pytesseract.TesseractNotFoundError as exc:
        raise OCRUnavailable("Tesseract executable is missing; install it and add it to PATH.") from exc
    except (OSError, RuntimeError, ValueError) as exc:
        raise OCRExecutionError(f"Tesseract could not recognize {Path(path).name}: {exc}") from exc

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
