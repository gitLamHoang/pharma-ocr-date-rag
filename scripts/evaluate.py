from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pharma_ocr_date_rag.evaluation import score_predictions
from pharma_ocr_date_rag.pipeline import process_folder


def main() -> None:
    expected_path = ROOT / "data" / "expected_dates.json"
    expected_rows = json.loads(expected_path.read_text(encoding="utf-8"))
    expected = {(row["doc"], row["normalized"], row["label"]) for row in expected_rows}

    docs = process_folder(ROOT / "data" / "synthetic_docs")
    predicted = {(doc.path.name, hit.normalized, hit.label) for doc in docs for hit in doc.dates}

    summary = score_predictions(expected, predicted)

    print(f"expected:  {len(expected)}")
    print(f"predicted: {len(predicted)}")
    print(f"matches:   {summary.overall.true_positive}")
    print(f"precision: {summary.overall.precision:.2f}")
    print(f"recall:    {summary.overall.recall:.2f}")
    print(f"f1:        {summary.overall.f1:.2f}")
    print(f"macro f1:  {summary.macro_f1:.2f}")

    print("\nPer-label metrics:")
    print(f"{'label':<14} {'support':>7} {'precision':>10} {'recall':>8} {'f1':>6}")
    for row in summary.by_label:
        support = row.true_positive + row.false_negative
        print(f"{row.label:<14} {support:>7} {row.precision:>10.2f} {row.recall:>8.2f} {row.f1:>6.2f}")

    missed = sorted(summary.missed)
    extra = sorted(summary.extra)
    if missed:
        print("\nMissed labels:")
        for row in missed:
            print("  ", row)
    if extra:
        print("\nExtra predictions:")
        for row in extra:
            print("  ", row)


if __name__ == "__main__":
    main()
