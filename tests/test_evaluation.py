from pharma_ocr_date_rag.evaluation import score_predictions


def test_scores_overall_and_per_label_metrics():
    expected = {
        ("one.txt", "2028-04-14", "expiry"),
        ("one.txt", "2026-04-15", "manufacture"),
        ("two.txt", "2029-07", "expiry"),
    }
    predicted = {
        ("one.txt", "2028-04-14", "expiry"),
        ("one.txt", "2026-04-15", "document"),
        ("two.txt", "2029-07", "expiry"),
    }

    summary = score_predictions(expected, predicted)
    metrics = {row.label: row for row in summary.by_label}

    assert summary.overall.true_positive == 2
    assert summary.overall.precision == 2 / 3
    assert summary.overall.recall == 2 / 3
    assert metrics["expiry"].f1 == 1.0
    assert metrics["manufacture"].recall == 0.0
    assert metrics["document"].precision == 0.0


def test_scores_empty_inputs_without_division_error():
    summary = score_predictions(set(), set())
    assert summary.overall.f1 == 0.0
    assert summary.macro_f1 == 0.0
    assert summary.by_label == []
