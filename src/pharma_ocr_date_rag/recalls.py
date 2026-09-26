"""Trainable table-role classification and conservative batch/date extraction."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from datetime import datetime

from .dates import extract_dates

ROLES = ("batch", "distribution", "expiry", "other")
THRESHOLD = 0.60


def heading_key(text: str) -> str:
    return " ".join(text.casefold().split())


def group_key(document: dict) -> str:
    payload = [{"headers": table["headers"], "rows": table["rows"]} for table in document["tables"]]
    return (
        hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        if payload
        else document["id"]
    )


def split_documents(documents: list[dict]) -> dict[str, str]:
    groups = {}
    for doc in documents:
        groups.setdefault(group_key(doc), []).append(doc)
    if len(groups) < 5:
        raise ValueError("At least five distinct document groups are required")
    ordered = sorted(
        groups, key=lambda key: (max(doc["published_at"] or doc["updated_at"] for doc in groups[key]), key)
    )
    held_out = max(1, round(len(ordered) * 0.2))
    splits = {}
    for index, key in enumerate(ordered):
        split = (
            "train"
            if index < len(ordered) - 2 * held_out
            else "validation"
            if index < len(ordered) - held_out
            else "test"
        )
        for doc in groups[key]:
            splits[doc["id"]] = split
    return splits


def column_examples(documents: list[dict], labels: dict[str, str], splits: dict[str, str]) -> list[dict]:
    examples = []
    for doc in documents:
        for table in doc["tables"]:
            for column, header in enumerate(table["headers"]):
                key = heading_key(header)
                if key not in labels or labels[key] not in ROLES:
                    raise ValueError(f"Column needs explicit annotation: {header!r}")
                examples.append(
                    {
                        "id": f"{doc['id']}:{table['table_index']}:{column}",
                        "document_id": doc["id"],
                        "split": splits[doc["id"]],
                        "header": header,
                        "label": labels[key],
                    }
                )
    return examples


def fit_role_model(examples: list[dict]):
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline

    training = [row for row in examples if row["split"] == "train"]
    if set(row["label"] for row in training) != set(ROLES):
        raise ValueError("Training split must contain each of the four column roles")
    model = make_pipeline(
        TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), lowercase=True),
        LogisticRegression(C=1.0, class_weight="balanced", max_iter=2000, random_state=42),
    )
    model.fit([row["header"] for row in training], [row["label"] for row in training])
    return model


def keyword_role(header: str) -> str:
    text = heading_key(header)
    if "batch" in text or "lot" in text:
        return "batch"
    if "expir" in text:
        return "expiry"
    if "distribut" in text or "dispatch" in text or "release" in text:
        return "distribution"
    return "other"


def predict_roles(model, headers: list[str]) -> list[dict]:
    probabilities = model.predict_proba(headers)
    output = []
    for row in probabilities:
        index = int(row.argmax())
        score = float(row[index])
        output.append(
            {
                "role": str(model.classes_[index]) if score >= THRESHOLD else "unclassified",
                "score": round(score, 6),
            }
        )
    return output


def date_cell(value: str) -> dict:
    """Do not infer missing days, century, range endpoints or numeric date convention."""
    value = value.strip()
    hits = extract_dates(value, language="en", date_order="auto", repair_ocr=False)
    if len(hits) == 1 and hits[0].start == 0 and hits[0].end == len(value):
        hit = hits[0]
        return {
            "normalized": hit.normalized,
            "candidates": list(hit.candidates),
            "precision": hit.precision,
            "review_reasons": [reason for reason in hit.review_reasons if reason != "unknown_label"],
        }
    # Named-month-only dates are common in public recall tables; retain month precision.
    if re.fullmatch(r"[A-Za-z]+[ -][12]\d{3}", value):
        for fmt in ("%B %Y", "%b %Y", "%B-%Y", "%b-%Y"):
            try:
                normalized = datetime.strptime(value, fmt).strftime("%Y-%m")
                return {
                    "normalized": normalized,
                    "candidates": [normalized],
                    "precision": "month",
                    "review_reasons": ["month_precision"],
                }
            except ValueError:
                pass
    return {
        "normalized": None,
        "candidates": [],
        "precision": "unknown",
        "review_reasons": ["unparsed_date_cell"],
    }


def recall_register(documents: list[dict], model, splits: dict[str, str]) -> tuple[list[dict], list[dict]]:
    records, excluded = [], []
    for doc in documents:
        for table in doc["tables"]:
            roles = predict_roles(model, table["headers"])
            batch_columns = [i for i, result in enumerate(roles) if result["role"] == "batch"]
            if len(batch_columns) != 1:
                excluded.append(
                    {
                        "document_id": doc["id"],
                        "table_index": table["table_index"],
                        "reason": "no_unique_confident_batch_column",
                        "predictions": roles,
                    }
                )
                continue
            for row_index, cells in enumerate(table["rows"]):
                for column, prediction in enumerate(roles):
                    if prediction["role"] not in {"expiry", "distribution"}:
                        continue
                    raw = cells[column]
                    records.append(
                        {
                            "id": f"{doc['id']}:{table['table_index']}:{row_index}:{column}",
                            "document_id": doc["id"],
                            "title": doc["title"],
                            "url": doc["url"],
                            "source_sha256": doc["source"]["sha256"],
                            "split": splits[doc["id"]],
                            "table_index": table["table_index"],
                            "row_index": row_index,
                            "column_index": column,
                            "batch_column_index": batch_columns[0],
                            "header": table["headers"][column],
                            "batch": cells[batch_columns[0]],
                            "raw_text": raw,
                            "role": prediction["role"],
                            "model_score": prediction["score"],
                            **date_cell(raw),
                            "status": "needs_review",
                        }
                    )
    return records, excluded


def score_roles(gold: list[str], predicted: list[str]) -> dict:
    from sklearn.metrics import accuracy_score, classification_report, confusion_matrix

    if not gold:
        return {"count": 0, "accuracy": None, "macro_f1": None, "by_role": {}, "confusion": []}
    report = classification_report(gold, predicted, labels=list(ROLES), output_dict=True, zero_division=0)
    return {
        "count": len(gold),
        "accuracy": round(float(accuracy_score(gold, predicted)), 6),
        "macro_f1": round(report["macro avg"]["f1-score"], 6),
        "by_role": {role: report[role] for role in ROLES},
        "confusion": confusion_matrix(gold, predicted, labels=list(ROLES)).tolist(),
    }


def evaluate_roles(examples: list[dict], model) -> dict:
    train = [row for row in examples if row["split"] == "train"]
    seen = {heading_key(row["header"]) for row in train}
    majority = Counter(row["label"] for row in train).most_common(1)[0][0]
    results = {}
    for split in ("validation", "test"):
        rows = [row for row in examples if row["split"] == split]
        headers = [row["header"] for row in rows]
        predicted = model.predict(headers).tolist()
        gold = [row["label"] for row in rows]
        unseen = [i for i, row in enumerate(rows) if heading_key(row["header"]) not in seen]
        reviewed = predict_roles(model, headers)
        accepted = [i for i, result in enumerate(reviewed) if result["role"] != "unclassified"]
        results[split] = {
            "model": score_roles(gold, predicted),
            "majority": score_roles(gold, [majority] * len(gold)),
            "keywords": score_roles(gold, [keyword_role(header) for header in headers]),
            "seen_heading_count": len(rows) - len(unseen),
            "unseen_headings": score_roles([gold[i] for i in unseen], [predicted[i] for i in unseen]),
            "abstention": {
                "threshold": THRESHOLD,
                "classified": len(accepted),
                "total": len(rows),
                "accuracy_when_classified": round(
                    sum(predicted[i] == gold[i] for i in accepted) / len(accepted), 6
                )
                if accepted
                else None,
            },
            "predictions": [
                {**row, "prediction": prediction, "review_prediction": review}
                for row, prediction, review in zip(rows, predicted, reviewed)
            ],
        }
    return results
