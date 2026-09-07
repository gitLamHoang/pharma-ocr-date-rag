from __future__ import annotations

from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pharma_ocr_date_rag.pipeline import process_folder


def main() -> None:
    expected_path = ROOT / "data" / "expected_dates.json"
    expected_rows = json.loads(expected_path.read_text(encoding="utf-8"))
    expected = {(row["doc"], row["normalized"], row["label"]) for row in expected_rows}

    docs = process_folder(ROOT / "data" / "synthetic_docs")
    predicted = {
        (doc.path.name, hit.normalized, hit.label)
        for doc in docs
        for hit in doc.dates
    }

    true_positive = len(expected & predicted)
    precision = true_positive / len(predicted) if predicted else 0
    recall = true_positive / len(expected) if expected else 0

    print(f"expected:  {len(expected)}")
    print(f"predicted: {len(predicted)}")
    print(f"matches:   {true_positive}")
    print(f"precision: {precision:.2f}")
    print(f"recall:    {recall:.2f}")

    missed = sorted(expected - predicted)
    extra = sorted(predicted - expected)
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
