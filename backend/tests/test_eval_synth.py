"""The synthetic page generator (`eval/synth.py`): files, gold format and determinism."""

import json

import synth
from run_eval import check_items

from pharma_dates.taxonomy import ALL_TYPES


def test_generates_one_folder_per_page_with_valid_gold(tmp_path):
    synth.generate(len(synth.DEGRADATIONS) * len(synth.KINDS), seed=3, out=tmp_path)
    folders = sorted(p for p in tmp_path.iterdir())
    assert len(folders) == 32
    golds = [json.loads((f / "gold.json").read_text()) for f in folders]
    assert {(g["kind"], g["degradation"]) for g in golds} == {
        (k, d) for k in synth.KINDS for d in synth.DEGRADATIONS
    }
    for folder, gold in zip(folders, golds):
        assert (folder / "page.png").stat().st_size and (folder / "page.pdf").read_bytes()[:5] == b"%PDF-"
        assert gold["items"] and all(item["date_type"] in ALL_TYPES for item in gold["items"])
        check_items(gold["items"], folder.name)
    assert {g["dpi"] for g in golds if g["degradation"] == "dpi150"} == {150}


def test_same_seed_gives_the_same_pages():
    first, _, gold_a = synth.generate_page(5, seed=11)
    second, _, gold_b = synth.generate_page(5, seed=11)
    assert gold_a == gold_b
    assert first.tobytes() == second.tobytes()
    assert synth.generate_page(5, seed=12)[2] != gold_a


def test_numeric_dates_that_read_two_ways_get_both_candidates():
    from datetime import date

    assert synth._gold_value("dmy_slash", date(2026, 3, 12)) == {"candidates": ["2026-03-12", "2026-12-03"]}
    assert synth._gold_value("dmy_slash", date(2026, 3, 25)) == {"normalized": "2026-03-25"}
    assert synth._gold_value("dmy_slash", date(2026, 3, 3)) == {"normalized": "2026-03-03"}
    assert synth._gold_value("roman_dot", date(2026, 3, 12)) == {"normalized": "2026-03-12"}
    assert synth._gold_value("mon_year", date(2026, 3, 12)) == {"normalized": "2026-03"}


def test_regenerating_replaces_only_earlier_pages(tmp_path):
    keep = tmp_path / "notes.txt"
    keep.write_text("not a page")
    synth.generate(3, seed=1, out=tmp_path)
    synth.generate(2, seed=1, out=tmp_path)
    assert sorted(p.name for p in tmp_path.iterdir() if p.is_dir()) == ["000-coa-clean", "001-cpp-clean"]
    assert keep.read_text() == "not a page"
