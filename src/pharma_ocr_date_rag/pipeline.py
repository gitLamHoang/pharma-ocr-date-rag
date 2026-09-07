from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .dates import DateHit, extract_dates
from .ocr import OCRResult, read_document
from .rag import DocumentChunk, split_chunks


@dataclass(frozen=True)
class ProcessedDocument:
    path: Path
    ocr: OCRResult
    dates: list[DateHit]
    chunks: list[DocumentChunk]


def process_document(path: str | Path, engine: str = "auto") -> ProcessedDocument:
    path = Path(path)
    ocr = read_document(path, engine=engine)
    return ProcessedDocument(
        path=path,
        ocr=ocr,
        dates=extract_dates(ocr.text),
        chunks=split_chunks(path.name, ocr.text),
    )


def process_folder(folder: str | Path, engine: str = "auto") -> list[ProcessedDocument]:
    folder = Path(folder)
    paths = sorted(path for path in folder.iterdir() if path.suffix.lower() in {".txt", ".md", ".png", ".jpg", ".jpeg"})
    return [process_document(path, engine=engine) for path in paths]


def all_chunks(documents: list[ProcessedDocument]) -> list[DocumentChunk]:
    chunks: list[DocumentChunk] = []
    for document in documents:
        chunks.extend(document.chunks)
    return chunks


def format_date_report(document: ProcessedDocument) -> str:
    lines = [f"{document.path.name} ({document.ocr.engine})"]
    if not document.dates:
        lines.append("  no dates found")
        return "\n".join(lines)

    for hit in document.dates:
        lines.append(
            f"  {hit.normalized:<10}  {hit.label:<11}  {hit.confidence:.2f}  {hit.context}"
        )
    return "\n".join(lines)
