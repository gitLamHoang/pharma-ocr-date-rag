"""Fit and evaluate a real-document column classifier; keep held-out documents out of fitting."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from pharma_ocr_date_rag.recalls import (
    column_examples,
    evaluate_roles,
    fit_role_model,
    recall_register,
    split_documents,
)

DATA = ROOT / "data/public_mhra"
REPORT = ROOT / "reports/mhra_training.json"
PUBLIC = ROOT / "web/public/data/recalls.json"


def build() -> tuple[dict, dict, object]:
    import sklearn

    dataset = json.loads((DATA / "documents.json").read_text(encoding="utf-8"))
    labels = json.loads((DATA / "header_labels.json").read_text(encoding="utf-8"))["labels"]
    documents = dataset["documents"]
    splits = split_documents(documents)
    examples = column_examples(documents, labels, splits)
    model = fit_role_model(examples)
    evaluation = evaluate_roles(examples, model)
    records, excluded = recall_register(documents, model, splits)
    paths = [
        *sorted(DATA.glob("*.json")),
        Path(__file__).resolve(),
        *(
            ROOT / "src/pharma_ocr_date_rag" / name
            for name in ("public_data.py", "recalls.py", "dates.py", "languages.py")
        ),
    ]
    provenance = {
        str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths
    }
    vectorizer, classifier = model.steps[0][1], model.steps[1][1]
    feature_names = vectorizer.get_feature_names_out()
    report = {
        "schema_version": 1,
        "scope": "Trained table-heading classifier, not a trained OCR recognizer. English public MHRA templates; explicit AI-assisted labels, not independent clinical ground truth.",
        "environment": {"python": platform.python_version(), "scikit_learn": sklearn.__version__},
        "protocol": json.loads((DATA / "protocol.json").read_text(encoding="utf-8")),
        "corpus": {
            "documents": len(documents),
            "tables": sum(len(doc["tables"]) for doc in documents),
            "table_rows": sum(len(table["rows"]) for doc in documents for table in doc["tables"]),
            "columns": len(examples),
            "unique_headings": len({row["header"].casefold() for row in examples}),
            "document_splits": dict(Counter(splits.values())),
            "column_splits": dict(Counter(row["split"] for row in examples)),
        },
        "splits": splits,
        "training_example_ids": [row["id"] for row in examples if row["split"] == "train"],
        "model": {
            "name": "Character TF-IDF + balanced logistic regression",
            "feature_count": len(feature_names),
            "top_features": {
                str(role): [str(feature_names[i]) for i in weights.argsort()[-8:][::-1]]
                for role, weights in zip(classifier.classes_, classifier.coef_)
            },
        },
        "evaluation": evaluation,
        "register": {
            "candidates": len(records),
            "unparsed": sum(not row["candidates"] for row in records),
            "ambiguous": sum(len(row["candidates"]) > 1 for row in records),
            "excluded_tables": excluded,
        },
        "source_sha256": provenance,
    }
    public = {
        "schemaVersion": 1,
        "attribution": dataset["attribution"],
        "licence": dataset["licence"],
        "snapshotRetrievedAt": dataset["selection"]["retrieved_at"],
        "scope": "Public medicine notices. Static research snapshot, not current recall advice. Every extracted value requires source review.",
        "corpus": report["corpus"],
        "evaluation": {
            key: {k: v for k, v in result.items() if k != "predictions"} for key, result in evaluation.items()
        },
        "documents": [{**doc, "split": splits[doc["id"]]} for doc in documents],
        "records": records,
        "excludedTables": excluded,
        "sourceSha256": provenance,
    }
    return report, public, model


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="Retrain and compare metrics/snapshot; no network calls"
    )
    parser.add_argument(
        "--model-output",
        type=Path,
        help="Optional local joblib artifact; never load untrusted pickle/joblib files",
    )
    args = parser.parse_args()
    report, public, model = build()
    for path, value in ((REPORT, report), (PUBLIC, public)):
        if args.check:
            saved = json.loads(path.read_text(encoding="utf-8"))
            saved.pop("environment", None)
            comparable = {key: item for key, item in value.items() if key != "environment"}
            if saved != comparable:
                parser.exit(
                    1,
                    f"{path.relative_to(ROOT)} differs from a fresh training run; inspect before updating.\n",
                )
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.model_output:
        import joblib

        args.model_output.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(model, args.model_output)
    print(
        json.dumps(
            {
                "corpus": report["corpus"],
                "register": {k: v for k, v in report["register"].items() if k != "excluded_tables"},
                "test": {
                    key: value for key, value in report["evaluation"]["test"].items() if key != "predictions"
                },
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
