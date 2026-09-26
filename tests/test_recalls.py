import copy
import hashlib
import importlib
import json
from pathlib import Path

import pytest

from pharma_ocr_date_rag.recalls import (
    column_examples,
    date_cell,
    fit_role_model,
    group_key,
    recall_register,
    split_documents,
)

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/public_mhra"


def corpus():
    return json.loads((DATA / "documents.json").read_text(encoding="utf-8"))["documents"]


def test_chronological_document_splits_keep_duplicate_tables_together():
    docs = corpus()
    duplicate = copy.deepcopy(docs[-1])
    duplicate["id"] = "duplicate"
    docs.append(duplicate)
    splits = split_documents(docs)
    assert splits[duplicate["id"]] == splits[docs[-2]["id"]]
    groups = {}
    for doc in docs:
        groups.setdefault(group_key(doc), set()).add(splits[doc["id"]])
    assert all(len(values) == 1 for values in groups.values())
    latest_training = max(doc["published_at"] for doc in docs if splits[doc["id"]] == "train")
    earliest_test = min(doc["published_at"] for doc in docs if splits[doc["id"]] == "test")
    assert latest_training < earliest_test


def test_unannotated_columns_cannot_be_auto_labeled():
    docs = corpus()
    with pytest.raises(ValueError, match="explicit annotation"):
        column_examples(docs, {}, split_documents(docs))


@pytest.mark.parametrize(
    "raw,normalized,precision",
    [
        ("05/2028", "2028-05", "month"),
        ("September 2027", "2027-09", "month"),
        ("Sep-2027", "2027-09", "month"),
        ("28 January 2025", "2025-01-28", "day"),
        ("09/10/2026", None, "day"),
        ("Not yet distributed", None, "unknown"),
        ("31/02/2026", None, "unknown"),
        ("Sep-27", None, "unknown"),
        ("May 2026 to June 2026", None, "unknown"),
    ],
)
def test_real_cells_preserve_precision_and_uncertainty(raw, normalized, precision):
    parsed = date_cell(raw)
    assert parsed["normalized"] == normalized and parsed["precision"] == precision


def test_snapshot_record_values_are_exact_table_evidence():
    snapshot = json.loads((ROOT / "web/public/data/recalls.json").read_text(encoding="utf-8"))
    docs = {doc["id"]: doc for doc in snapshot["documents"]}
    assert len(docs) == 60 and len(snapshot["records"]) == 742
    for row in snapshot["records"]:
        doc = docs[row["document_id"]]
        table = next(table for table in doc["tables"] if table["table_index"] == row["table_index"])
        assert row["raw_text"] == table["rows"][row["row_index"]][row["column_index"]]
        assert row["batch"] == table["rows"][row["row_index"]][row["batch_column_index"]]
        assert row["source_sha256"] == doc["source"]["sha256"]
        assert row["status"] == "needs_review"
    for name, digest in snapshot["sourceSha256"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest


def test_classifier_never_fits_test_or_validation_headings(monkeypatch):
    pytest.importorskip("sklearn")
    from sklearn.pipeline import Pipeline

    docs = corpus()
    labels = json.loads((DATA / "header_labels.json").read_text())["labels"]
    examples = column_examples(docs, labels, split_documents(docs))
    seen = []
    real_fit = Pipeline.fit

    def observed_fit(self, x, y, **kwargs):
        seen.extend(x)
        return real_fit(self, x, y, **kwargs)

    monkeypatch.setattr(Pipeline, "fit", observed_fit)
    for row in examples:
        if row["split"] != "train":
            row["header"] = "HELD-OUT SENTINEL"
    fit_role_model(examples)
    assert "HELD-OUT SENTINEL" not in seen
    assert len(seen) == 182


def test_low_score_cannot_silently_assign_a_batch():
    np = pytest.importorskip("numpy")

    class Uncertain:
        classes_ = np.array(["batch", "distribution", "expiry", "other"])

        def predict_proba(self, headers):
            return np.full((len(headers), 4), 0.25)

    doc = corpus()[0]
    records, excluded = recall_register([doc], Uncertain(), {doc["id"]: "test"})
    assert records == []
    assert all(item["reason"] == "no_unique_confident_batch_column" for item in excluded)


def test_training_report_discloses_template_overlap_and_baselines():
    report = json.loads((ROOT / "reports/mhra_training.json").read_text(encoding="utf-8"))
    assert report["corpus"]["document_splits"] == {"train": 36, "validation": 12, "test": 12}
    for example_id in report["training_example_ids"]:
        assert report["splits"][example_id.split(":")[0]] == "train"
    test = report["evaluation"]["test"]
    assert test["model"]["count"] == 80
    assert test["seen_heading_count"] == 76
    assert test["keywords"]["accuracy"] >= test["model"]["accuracy"]


def test_original_pdf_evidence_can_be_verified_without_ocr(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    experiment = importlib.import_module("benchmark_mhra_pdf")
    report = json.loads(experiment.REPORT.read_text(encoding="utf-8"))
    experiment.check_report(report)
    assert sum(len(result["ocr_matched"]) for result in report["results"]) == 11


@pytest.mark.parametrize("mutation", ["reference", "selection", "pages", "source", "exclusion"])
def test_original_pdf_report_rejects_changed_evaluation_scope(monkeypatch, mutation):
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    experiment = importlib.import_module("benchmark_mhra_pdf")
    report = json.loads(experiment.REPORT.read_text(encoding="utf-8"))
    first = report["results"][0]
    if mutation == "reference":
        first["expected_date_keys"] = []
    elif mutation == "selection":
        report["results"][1] = copy.deepcopy(first)
    elif mutation == "pages":
        first["pages"] = first["pages"][1:]
    elif mutation == "source":
        first["pdf_source"]["url"] = "https://www.gov.uk/wrong.pdf"
    else:
        first["unsupported_html_cells"] = []
    with pytest.raises(ValueError, match="PDF"):
        experiment.check_report(report)
