from __future__ import annotations

from dataclasses import dataclass


DateRecord = tuple[str, str, str]


@dataclass(frozen=True)
class LabelMetrics:
    label: str
    true_positive: int
    false_positive: int
    false_negative: int
    precision: float
    recall: float
    f1: float


@dataclass(frozen=True)
class EvaluationSummary:
    overall: LabelMetrics
    by_label: list[LabelMetrics]
    macro_f1: float
    missed: set[DateRecord]
    extra: set[DateRecord]


def _calculate_metrics(label: str, expected: set[DateRecord], predicted: set[DateRecord]) -> LabelMetrics:
    true_positive = len(expected & predicted)
    false_positive = len(predicted - expected)
    false_negative = len(expected - predicted)
    precision = true_positive / (true_positive + false_positive) if predicted else 0.0
    recall = true_positive / (true_positive + false_negative) if expected else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return LabelMetrics(
        label=label,
        true_positive=true_positive,
        false_positive=false_positive,
        false_negative=false_negative,
        precision=precision,
        recall=recall,
        f1=f1,
    )


def score_predictions(
    expected: set[DateRecord], predicted: set[DateRecord]
) -> EvaluationSummary:
    labels = sorted({row[2] for row in expected | predicted})
    by_label = []
    for label in labels:
        label_expected = {row for row in expected if row[2] == label}
        label_predicted = {row for row in predicted if row[2] == label}
        by_label.append(_calculate_metrics(label, label_expected, label_predicted))

    overall = _calculate_metrics("overall", expected, predicted)
    macro_f1 = sum(row.f1 for row in by_label) / len(by_label) if by_label else 0.0
    return EvaluationSummary(
        overall=overall,
        by_label=by_label,
        macro_f1=macro_f1,
        missed=expected - predicted,
        extra=predicted - expected,
    )
