"""Export measured synthetic-only checks with input hashes; no OCR/model benchmark claims."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from benchmark_retrieval import CASES

from pharma_ocr_date_rag.evaluation import score_predictions
from pharma_ocr_date_rag.experiments import evaluate_chunk_sizes
from pharma_ocr_date_rag.pipeline import process_folder


def evidence() -> dict:
    docs = process_folder(ROOT / "data" / "synthetic_docs")
    expected_path = ROOT / "data" / "expected_dates.json"
    expected_rows = json.loads(expected_path.read_text(encoding="utf-8"))
    expected = {(row["doc"], row["normalized"], row["label"]) for row in expected_rows}
    predicted = {(doc.path.name, hit.normalized, hit.label) for doc in docs for hit in doc.dates}
    summary = score_predictions(expected, predicted)
    paths = [expected_path, *(doc.path for doc in docs)]
    source_paths = [
        *sorted((ROOT / "src" / "pharma_ocr_date_rag").glob("*.py")),
        ROOT / "scripts" / "benchmark_retrieval.py",
        Path(__file__).resolve(),
    ]
    return {
        "schema_version": 1,
        "dataset": "Four synthetic text documents; not a held-out benchmark or a real-image OCR evaluation",
        "documents": len(docs),
        "extraction": {
            "unit": "unique (document, normalized date, label) tuple",
            "expected": len(expected),
            "predicted": len(predicted),
            "overall": asdict(summary.overall),
            "by_label": [asdict(row) for row in summary.by_label],
            "macro_f1": summary.macro_f1,
            "missed": sorted(summary.missed),
            "extra": sorted(summary.extra),
        },
        "retrieval": {
            "method": "term-frequency cosine with date bonus; top_k=3",
            "cases": [asdict(case) for case in CASES],
            "rows": [asdict(row) for row in evaluate_chunk_sizes(docs, CASES, [35, 60, 90], top_k=3)],
        },
        "input_sha256": {
            str(path.relative_to(ROOT)): sha256(path.read_bytes()).hexdigest() for path in paths
        },
        "source_sha256": {
            str(path.relative_to(ROOT)): sha256(path.read_bytes()).hexdigest() for path in source_paths
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Fail if checked-in evidence is stale")
    args = parser.parse_args()
    output = ROOT / "reports" / "synthetic_evaluation.json"
    serialized = json.dumps(evidence(), indent=2, sort_keys=True) + "\n"
    if args.check:
        if not output.exists() or output.read_text(encoding="utf-8") != serialized:
            parser.exit(1, "Evidence differs; run scripts/export_evidence.py and review the changes.\n")
        print("Synthetic evidence matches checked-in inputs and current code.")
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(serialized, encoding="utf-8")
        print(output.relative_to(ROOT))


if __name__ == "__main__":
    main()
