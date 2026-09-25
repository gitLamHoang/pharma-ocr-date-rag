from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from .dates import DateHit, extract_dates
from .languages import validate_language
from .ocr import OCRResult, read_document
from .policies import resolve_date_orders
from .rag import DocumentChunk, split_chunks


@dataclass(frozen=True)
class ProcessedDocument:
    path: Path
    ocr: OCRResult
    dates: list[DateHit]
    chunks: list[DocumentChunk]
    language: str = "auto"
    date_order: str = "auto"


def process_text(
    name: str,
    text: str,
    language: str = "auto",
    date_order: str = "auto",
) -> ProcessedDocument:
    return _process(Path(name), OCRResult(text=text, engine="plain-text"), language, date_order)


def _process(path: Path, ocr: OCRResult, language: str, date_order: str) -> ProcessedDocument:
    return ProcessedDocument(
        path=path,
        ocr=ocr,
        dates=extract_dates(ocr.text, language=language, date_order=date_order),
        chunks=split_chunks(path.name, ocr.text, language=language, date_order=date_order),
        language=language,
        date_order=date_order,
    )


def process_document(
    path: str | Path,
    engine: str = "auto",
    language: str = "auto",
    date_order: str = "auto",
) -> ProcessedDocument:
    path = Path(path)
    ocr = read_document(path, engine=engine)
    return _process(path, ocr, language, date_order)


def document_paths(folder: str | Path) -> list[Path]:
    folder = Path(folder)
    return sorted(
        path
        for path in folder.iterdir()
        if path.is_file() and path.suffix.lower() in {".txt", ".md", ".png", ".jpg", ".jpeg"}
    )


def process_folder(
    folder: str | Path,
    engine: str = "auto",
    language: str = "auto",
    date_order: str = "auto",
    date_order_map: Mapping[str, str] | None = None,
) -> list[ProcessedDocument]:
    validate_language(language)
    paths = document_paths(folder)
    orders = resolve_date_orders(paths, date_order, date_order_map)
    return [
        process_document(path, engine=engine, language=language, date_order=orders[path.name])
        for path in paths
    ]


def all_chunks(documents: list[ProcessedDocument]) -> list[DocumentChunk]:
    chunks: list[DocumentChunk] = []
    for document in documents:
        chunks.extend(document.chunks)
    return chunks


def format_date_report(document: ProcessedDocument) -> str:
    lines = [
        f"{document.path.name} ({document.ocr.engine}; language={document.language}; "
        f"date_order={document.date_order})"
    ]
    if not document.dates:
        lines.append("  no dates found")
        return "\n".join(lines)

    for hit in document.dates:
        value = hit.normalized or " / ".join(hit.candidates)
        review = f" [review: {', '.join(hit.review_reasons)}]" if hit.review_reasons else ""
        lines.append(f"  {value:<10}  {hit.label:<11}  {hit.confidence:.2f}  {hit.context}{review}")
    return "\n".join(lines)
