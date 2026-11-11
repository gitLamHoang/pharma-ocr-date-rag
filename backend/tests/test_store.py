import sqlite3
from pathlib import Path

import pytest
from helpers import make_layout

from pharma_dates.models import BBox, Flag, LabeledDate
from pharma_dates.store import FrozenRunError, Store
from pharma_dates.taxonomy import family_of


def dated(id_, raw_text, normalized, *, page=1, char_start=0, date_type="expiry_date", **fields):
    defaults = {
        "candidates": [normalized] if normalized else [],
        "precision": "day",
        "bbox": BBox(x0=1, y0=2, x1=3, y1=4),
        "context": f"Expiry date: {raw_text}",
        "rule_label": "expiry",
        "source": "rules+ai",
        "qualifier": None,
        "resolved_value": None,
        "evidence": None,
        "confidence": 0.9,
        "rationale": "next to 'Expiry date'",
    }
    return LabeledDate(
        id=id_,
        page=page,
        raw_text=raw_text,
        normalized=normalized,
        char_start=char_start,
        char_end=char_start + len(raw_text),
        date_type=date_type,
        family=family_of(date_type),
        **(defaults | fields),
    )


@pytest.fixture
def store(tmp_path: Path) -> Store:
    return Store(tmp_path / "data" / "pharma.sqlite")


def new_run(store: Store, dates, flags=(), discarded=(), sha="a" * 64) -> tuple[int, int]:
    doc = store.upsert_document(sha, "coa.pdf", 1)
    run = store.create_run(doc, "1.0.0", "claude-opus-5-5", True)
    store.save_results(run, list(dates), list(flags), list(discarded))
    store.set_run_status(run, "done")
    return doc, run


def only_date(store: Store, run_id: int):
    (d,) = store.dates_for_run(run_id)
    return d


def review(store: Store, date_id: int, action: str, **kw):
    return store.add_review(
        date_id, action, kw.pop("reviewer", "A. Reviewer"), kw.pop("reason", "checked"), **kw
    )


def test_review_events_append_only(store, tmp_path):
    _, run = new_run(store, [dated("c1", "31/03/2027", "2027-03-31")])
    review(store, only_date(store, run).id, "accept")

    conn = sqlite3.connect(tmp_path / "data" / "pharma.sqlite")
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        conn.execute("UPDATE review_events SET reason = 'edited'")
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        conn.execute("DELETE FROM review_events")
    conn.close()
    assert [e.reason for e in store.history(only_date(store, run).id)] == ["checked"]


def test_status_follows_latest_event(store):
    _, run = new_run(store, [dated("c1", "31/03/2027", "2027-03-31")])
    date_id = only_date(store, run).id
    assert only_date(store, run).status == "needs_review"

    for action, status in [
        ("accept", "accepted"),
        ("reject", "rejected"),
        ("reopen", "needs_review"),
        ("correct", "corrected"),
    ]:
        extra = {"new_value": "2027-04-30"} if action == "correct" else {}
        event = review(store, date_id, action, **extra)
        assert event.action == action
        assert only_date(store, run).status == status
    assert [e.action for e in store.history(date_id)] == ["accept", "reject", "reopen", "correct"]


def test_correction_changes_current_type(store):
    _, run = new_run(store, [dated("c1", "03/04/2027", None, candidates=["2027-03-04", "2027-04-03"])])
    d = only_date(store, run)
    assert (d.current_type, d.current_family, d.current_value) == ("expiry_date", "product", None)

    review(store, d.id, "correct", new_type="retest_date")
    review(store, d.id, "correct", new_value="2027-04-03", reason="day-first, like the batch record")
    review(store, d.id, "accept")

    d = only_date(store, run)
    assert d.status == "accepted"
    assert (d.current_type, d.current_family, d.current_value) == ("retest_date", "product", "2027-04-03")
    assert d.date_type == "expiry_date"  # the pipeline's label is kept


def test_review_on_frozen_run_rejected(store):
    doc, old_run = new_run(store, [dated("c1", "31/03/2027", "2027-03-31")])
    old_date = only_date(store, old_run).id
    new = store.create_run(doc, "1.0.1", "claude-opus-5-5", True)

    with pytest.raises(FrozenRunError):
        review(store, old_date, "accept")
    assert store.history(old_date) == []
    assert only_date(store, old_run).status == "needs_review"
    assert store.latest_run(doc).id == new


def test_carry_over_exact_match_only(store):
    old_dates = [
        dated("c1", "31/03/2027", "2027-03-31"),
        dated("c2", "01/02/2026", "2026-02-01", char_start=40, date_type="manufacture_date"),
        dated("c3", "15/05/2026", "2026-05-15", char_start=80),
        dated("c4", "20/06/2026", "2026-06-20", page=2),
        dated("c5", "30/04/2027", "2027-04-30", char_start=120),
        dated("c6", "01/01/2028", "2028-01-01", char_start=160),
    ]
    doc, old_run = new_run(store, old_dates)
    ids = {d.candidate_id: d.id for d in store.dates_for_run(old_run)}
    review(store, ids["c1"], "accept")
    review(store, ids["c2"], "correct", new_type="packaging_date", new_value="2026-02-02", reason="typo")
    review(store, ids["c3"], "accept")
    review(store, ids["c4"], "reject")
    review(store, ids["c4"], "reopen")
    review(store, ids["c5"], "accept")
    review(store, ids["c6"], "accept")

    new_run_id = store.create_run(doc, "1.0.1", "claude-opus-5-5", True)
    store.save_results(
        new_run_id,
        [
            dated("n1", "31/03/2027", "2027-03-31", char_start=5),  # same page, text and value
            dated("n2", "01/02/2026", "2026-02-01", char_start=40, date_type="manufacture_date"),
            dated("n3", "15/05/2026", "2026-05-16", char_start=80),  # different value
            dated("n4", "20/06/2026", "2026-06-20", page=2),  # last event was a reopen
            dated("n5", "31/03/2027", "2027-03-31", page=2),  # different page
            dated("n6", "30.04.2027", "2027-04-30", char_start=120),  # same page and value, other text
            dated("n7", "01/01/2028", "2028-01-01", page=2, char_start=60),  # c6 has no page-1 twin
        ],
        [],
        [],
    )

    assert store.carry_over(old_run, new_run_id) == 2
    new = {d.candidate_id: d for d in store.dates_for_run(new_run_id)}
    assert (new["n1"].status, new["n1"].carried_from_run) == ("accepted", old_run)
    assert (new["n2"].status, new["n2"].current_type, new["n2"].current_value) == (
        "corrected",
        "packaging_date",
        "2026-02-02",
    )
    assert [(d.status, d.carried_from_run) for d in (new[k] for k in ("n3", "n4", "n5", "n6", "n7"))] == [
        ("needs_review", None)
    ] * 5
    (event,) = store.history(new["n1"].id)
    assert (event.reason, event.reviewer, event.carried_from_run) == (
        f"carried over from run {old_run}",
        "A. Reviewer",
        old_run,
    )
    assert len(store.history(ids["c1"])) == 1  # the old run is untouched


def test_carry_over_pairs_repeated_dates_in_reading_order(store):
    signature = {"date_type": "signature_date", "rule_label": "unknown"}
    doc, old_run = new_run(
        store,
        [
            dated("c1", "12/03/2026", None, **signature),
            dated("c2", "12/03/2026", None, char_start=50, **signature),
        ],
    )
    first, second = store.dates_for_run(old_run)
    review(store, second.id, "reject", reason="not a date")

    new_run_id = store.create_run(doc, "1.0.1", None, False)
    store.save_results(
        new_run_id,
        [
            dated("n1", "12/03/2026", None, **signature),
            dated("n2", "12/03/2026", None, char_start=50, **signature),
        ],
        [],
        [],
    )
    assert store.carry_over(old_run, new_run_id) == 1
    assert [d.status for d in store.dates_for_run(new_run_id)] == ["needs_review", "rejected"]


def test_carry_over_keeps_reviewer_decision(store):
    doc, old_run = new_run(store, [dated("c1", "31/03/2027", "2027-03-31")])
    review(store, only_date(store, old_run).id, "accept")
    new_run_id = store.create_run(doc, "1.0.1", "claude-opus-5-5", True)
    store.save_results(new_run_id, [dated("n1", "31/03/2027", "2027-03-31")], [], [])
    review(store, only_date(store, new_run_id).id, "reject", reason="wrong date")

    assert store.carry_over(old_run, new_run_id) == 0
    assert store.carry_over(old_run, new_run_id) == 0
    d = only_date(store, new_run_id)
    assert (d.status, d.carried_from_run) == ("rejected", None)
    assert [e.action for e in store.history(d.id)] == ["reject"]


def test_carry_over_is_idempotent(store):
    doc, old_run = new_run(store, [dated("c1", "31/03/2027", "2027-03-31")])
    review(store, only_date(store, old_run).id, "accept")
    new_run_id = store.create_run(doc, "1.0.1", "claude-opus-5-5", True)
    store.save_results(new_run_id, [dated("n1", "31/03/2027", "2027-03-31")], [], [])

    assert store.carry_over(old_run, new_run_id) == 1
    assert store.carry_over(old_run, new_run_id) == 0
    assert len(store.history(only_date(store, new_run_id).id)) == 1


def test_carry_over_into_frozen_run_rejected(store):
    doc, old_run = new_run(store, [dated("c1", "31/03/2027", "2027-03-31")])
    review(store, only_date(store, old_run).id, "accept")
    middle = store.create_run(doc, "1.0.1", "claude-opus-5-5", True)
    store.save_results(middle, [dated("n1", "31/03/2027", "2027-03-31")], [], [])
    store.create_run(doc, "1.0.2", "claude-opus-5-5", True)

    with pytest.raises(FrozenRunError):
        store.carry_over(old_run, middle)
    assert store.history(only_date(store, middle).id) == []


def test_reupload_same_sha_reuses_document(store):
    first = store.upsert_document("b" * 64, "coa.pdf", 3)
    again = store.upsert_document("b" * 64, "coa (1).pdf", 3)
    other = store.upsert_document("c" * 64, "sop.pdf", 1)

    assert first == again != other
    assert [(s.name, s.pages) for s in store.list_documents()] == [("sop.pdf", 1), ("coa.pdf", 3)]


def test_empty_reason_rejected(store):
    _, run = new_run(store, [dated("c1", "31/03/2027", "2027-03-31")])
    date_id = only_date(store, run).id

    with pytest.raises(ValueError, match="reason"):
        review(store, date_id, "accept", reason="   ")
    with pytest.raises(ValueError, match="reviewer"):
        review(store, date_id, "accept", reviewer="")
    with pytest.raises(ValueError, match="type"):
        review(store, date_id, "correct", new_type="birthday")
    assert store.history(date_id) == []


@pytest.mark.parametrize(
    ("action", "extra"),
    [
        ("approve", {}),
        ("correct", {}),
        ("accept", {"new_type": "retest_date"}),
        ("correct", {"new_value": "31/03/2027"}),
        ("correct", {"new_value": "2027-02-30"}),
    ],
)
def test_invalid_review_rejected(store, action, extra):
    _, run = new_run(store, [dated("c1", "31/03/2027", "2027-03-31")])
    date_id = only_date(store, run).id
    with pytest.raises(ValueError):
        review(store, date_id, action, **extra)
    assert store.history(date_id) == []


def test_month_value_accepted_in_correction(store):
    _, run = new_run(store, [dated("c1", "03/2027", "2027-03", precision="month")])
    review(store, only_date(store, run).id, "correct", new_value="2027-04")
    assert only_date(store, run).current_value == "2027-04"


def test_review_unknown_date_raises_lookup(store):
    with pytest.raises(LookupError):
        review(store, 999, "accept")


def test_results_round_trip_with_flags_and_discarded(store):
    dates = [
        dated("p1-c1", "01/02/2026", "2026-02-01", date_type="manufacture_date"),
        dated("p1-c2", "01/01/2026", "2026-01-01", char_start=30, resolved_value=None),
    ]
    flag = Flag(rule="expiry_before_manufacture", severity="error", message="x", date_ids=["p1-c2", "p1-c1"])
    discarded = [
        {"page": 1, "kind": "missed_date", "reason": "not found in the page text", "verbatim": "1/1/99"}
    ]
    _, run = new_run(store, dates, [flag], discarded)

    stored = store.dates_for_run(run)
    assert [d.candidate_id for d in stored] == ["p1-c1", "p1-c2"]
    assert stored[0].model_dump(include={"raw_text", "normalized", "bbox", "family", "run_id"}) == {
        "raw_text": "01/02/2026",
        "normalized": "2026-02-01",
        "bbox": {"x0": 1, "y0": 2, "x1": 3, "y1": 4},
        "family": "product",
        "run_id": run,
    }
    (stored_flag,) = store.flags_for_run(run)
    assert (stored_flag.rule, stored_flag.severity) == ("expiry_before_manufacture", "error")
    assert stored_flag.date_ids == [stored[1].id, stored[0].id]  # database ids, in the flag's order
    assert store.discarded_for_run(run) == discarded


def test_flag_with_unknown_date_id_rejected(store):
    doc = store.upsert_document("d" * 64, "x.pdf", 1)
    run = store.create_run(doc, "1.0.0", None, False)
    flag = Flag(rule="r", severity="info", message="m", date_ids=["missing"])
    with pytest.raises(ValueError, match="missing"):
        store.save_results(run, [dated("c1", "31/03/2027", "2027-03-31")], [flag], [])
    assert store.dates_for_run(run) == []  # nothing half-written


def test_run_status_and_error(store):
    doc = store.upsert_document("e" * 64, "broken.pdf", 0)
    run = store.create_run(doc, "1.0.0", None, False)
    r = store.latest_run(doc)
    assert (r.status, r.ai_used, r.ai_model, r.finished_at) == ("queued", False, None, None)

    store.set_run_status(run, "reading")
    store.set_run_status(run, "failed", "This file is damaged or incomplete and cannot be read.")
    r = store.get_run(run)
    assert (r.status, r.error) == ("failed", "This file is damaged or incomplete and cannot be read.")
    assert r.finished_at is not None
    assert store.get_document(doc).status == "failed"
    with pytest.raises(ValueError):
        store.set_run_status(run, "exploded")


def test_latest_run_none_without_runs(store):
    assert store.latest_run(store.upsert_document("f" * 64, "new.pdf", 1)) is None


def test_list_documents_counts_latest_run(store):
    dates = [dated("c1", "31/03/2027", "2027-03-31"), dated("c2", "01/02/2026", "2026-02-01", char_start=30)]
    flag = Flag(rule="r", severity="warning", message="m", date_ids=["c1"])
    doc, run = new_run(store, dates, [flag])
    review(store, store.dates_for_run(run)[0].id, "accept")

    (summary,) = store.list_documents()
    assert summary.model_dump(
        include={"id", "name", "pages", "status", "n_dates", "n_flags", "n_needs_review"}
    ) == {
        "id": doc,
        "name": "coa.pdf",
        "pages": 1,
        "status": "done",
        "n_dates": 2,
        "n_flags": 1,
        "n_needs_review": 1,
    }
    assert summary.created_at is not None

    store.create_run(doc, "1.0.1", None, False)
    (summary,) = store.list_documents()
    assert (summary.status, summary.n_dates, summary.n_flags) == ("queued", 0, 0)


def test_pages_round_trip(store):
    doc = store.upsert_document("g" * 64, "scan.png", 2)
    run = store.create_run(doc, "1.0.0", None, False)
    layouts = [make_layout(["Expiry date: 31/03/2027"], n=1), make_layout(["Signed 01/02/2026"], n=2)]
    store.save_pages(
        run, layouts, image_paths=[Path("data/uploads/x/page-1.png"), Path("data/uploads/x/page-2.png")]
    )

    pages = store.pages_for_run(run)
    assert [p.model_dump(exclude={"image_path"}) for p in pages] == [
        layout.model_dump() for layout in layouts
    ]
    assert [p.image_path for p in pages] == ["data/uploads/x/page-1.png", "data/uploads/x/page-2.png"]


def test_reopening_store_keeps_data(store, tmp_path):
    _, run = new_run(store, [dated("c1", "31/03/2027", "2027-03-31")])
    reopened = Store(tmp_path / "data" / "pharma.sqlite")
    assert only_date(reopened, run).raw_text == "31/03/2027"
