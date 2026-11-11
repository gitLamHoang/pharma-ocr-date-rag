"""Run the pipeline over the evaluation sets and score it against their gold labels.

    uv run --project backend python eval/fetch.py               # once: download and check sha256
    uv run --project backend python eval/synth.py generate      # once: the synthetic set
    uv run --project backend python eval/run_eval.py --ai off   # rules + offline labels
    uv run --project backend python eval/run_eval.py --ai on    # Claude; needs credentials in .env

`--set public` (the default) is the hand-labelled public documents, `--set synth` the synthetic
pages from `eval/synth.py` (scored per degradation level), `--set all` both. Writes
`eval/results-<set>-<mode>.json` (git-ignored) and prints the tables. Exits 1 when the gate
fails: any hallucination (a date with no gold match whose text is not on its page) or any silent
resolution (an ambiguous date given one value without quoted evidence).

Matching: on the public set a predicted date matches a gold item on the same page whose raw text
is the same (case and whitespace ignored: OCR prints "11 /18/2022" for "11/18/2022"), one to one. On the synthetic set it matches a gold item
with the same possible values instead, because the gold text is what was drawn and OCR may read
"12 . 03 . 2026" as "12.03.2026". It is a true positive when the date type and the value also
agree: the gold `normalized` value, or for an ambiguous gold item (`candidates`) no single value
unless it is one of the gold readings backed by evidence.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from pharma_dates.models import LabeledDate
from pharma_dates.taxonomy import ALL_TYPES

EVAL_DIR = Path(__file__).resolve().parent
CACHE_DIR = EVAL_DIR / "cache"
GOLD_DIR = EVAL_DIR / "gold"
SOURCES = EVAL_DIR / "sources.json"
SYNTH_DIR = EVAL_DIR / "synth"
SETS = ("public", "synth", "all")


@dataclass
class PRF:
    tp: int = 0
    fp: int = 0
    fn: int = 0

    @property
    def precision(self) -> float:
        return self.tp / (self.tp + self.fp) if self.tp + self.fp else 0.0

    @property
    def recall(self) -> float:
        return self.tp / (self.tp + self.fn) if self.tp + self.fn else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if p + r else 0.0

    def __add__(self, other: PRF) -> PRF:
        return PRF(self.tp + other.tp, self.fp + other.fp, self.fn + other.fn)

    def as_dict(self) -> dict:
        return {"tp": self.tp, "fp": self.fp, "fn": self.fn} | {
            k: round(getattr(self, k), 4) for k in ("precision", "recall", "f1")
        }


@dataclass
class Scores:
    per_type: dict[str, PRF]
    micro: PRF
    hallucinations: int
    silent_resolutions: int
    detected: PRF = field(default_factory=PRF)  # the date found at all, whatever its type and value
    errors: list[dict] = field(default_factory=list)  # what went wrong, for reading the results

    def __add__(self, other: Scores) -> Scores:
        per_type = {t: self.per_type.get(t, PRF()) + other.per_type.get(t, PRF()) for t in self.per_type}
        per_type |= {t: prf for t, prf in other.per_type.items() if t not in self.per_type}
        return Scores(
            per_type,
            self.micro + other.micro,
            self.hallucinations + other.hallucinations,
            self.silent_resolutions + other.silent_resolutions,
            self.detected + other.detected,
            self.errors + other.errors,
        )


def score(
    predicted: list[LabeledDate], gold: list[dict], page_texts: dict[int, str], by: str = "text"
) -> Scores:
    """Score one document's predicted dates against its gold items (see the module docstring).

    `by="text"` pairs predictions and gold items by raw text, `by="value"` by possible values."""
    same = _same_text if by == "text" else _same_values
    per_type: dict[str, PRF] = {}

    def count(date_type: str, kind: str) -> None:
        prf = per_type.setdefault(date_type, PRF())
        setattr(prf, kind, getattr(prf, kind) + 1)

    unmatched = list(predicted)
    hallucinations = silent = 0
    errors: list[dict] = []
    for item in gold:
        same_text = [p for p in unmatched if p.page == item["page"] and same(p, item)]
        best = sorted(same_text, key=lambda p: (p.date_type != item["date_type"], not _value_ok(p, item)))
        if not best:
            count(item["date_type"], "fn")
            errors.append(_error("missed", item["page"], item["raw_text"], item["date_type"]))
            continue
        p = best[0]
        unmatched.remove(p)
        if _silent_resolution(p, item):
            silent += 1
            errors.append(_error("silent_resolution", p.page, p.raw_text, p.date_type))
        if p.date_type == item["date_type"] and _value_ok(p, item):
            count(p.date_type, "tp")
        else:
            count(p.date_type, "fp")
            count(item["date_type"], "fn")
            expected = {
                "gold_type": item["date_type"],
                "gold_value": item.get("normalized") or item["candidates"],
            }
            errors.append(_error("mismatch", p.page, p.raw_text, p.date_type, **expected))
    for p in unmatched:
        count(p.date_type, "fp")
        if _key(p.raw_text) in _key(page_texts.get(p.page, "")):
            errors.append(_error("false_positive", p.page, p.raw_text, p.date_type))
        else:
            hallucinations += 1
            errors.append(_error("hallucination", p.page, p.raw_text, p.date_type))
    micro = sum(per_type.values(), PRF())
    found = len(predicted) - len(unmatched)
    detected = PRF(found, len(unmatched), len(gold) - found)
    return Scores(per_type, micro, hallucinations, silent, detected, errors)


def _key(text: str) -> str:
    return "".join(text.casefold().split())


def _same_text(p: LabeledDate, item: dict) -> bool:
    return _key(p.raw_text) == _key(item["raw_text"])


def _same_values(p: LabeledDate, item: dict) -> bool:
    gold = {item["normalized"]} if "normalized" in item else set(item["candidates"])
    return (set(p.candidates) | ({p.normalized} if p.normalized else set())) == gold


def _value_ok(p: LabeledDate, item: dict) -> bool:
    if "normalized" in item:
        return (p.resolved_value or p.normalized) == item["normalized"]
    if p.resolved_value is not None:
        return p.evidence is not None and p.resolved_value in item["candidates"]
    return p.normalized is None


def _silent_resolution(p: LabeledDate, item: dict) -> bool:
    return "candidates" in item and p.evidence is None and (p.normalized or p.resolved_value) is not None


def _error(kind: str, page: int, raw_text: str, date_type: str, **extra: object) -> dict:
    return {
        "kind": kind,
        "page": page,
        "raw_text": raw_text,
        "date_type": date_type,
    } | extra


# --- Data set ---------------------------------------------------------------------------------


def load_sources() -> list[dict]:
    return json.loads(SOURCES.read_text(encoding="utf-8"))


def load_gold(source_id: str) -> list[dict]:
    """The gold items of one document; `ValueError` for an item the scorer cannot use."""
    items = json.loads((GOLD_DIR / f"{source_id}.json").read_text(encoding="utf-8"))
    check_items(items, f"{source_id}.json")
    return items


def load_synth() -> list[dict]:
    """The synthetic pages' gold files (`eval/synth.py`), each with its `folder` added."""
    pages = []
    for path in sorted(SYNTH_DIR.glob("*/gold.json")):
        gold = json.loads(path.read_text(encoding="utf-8"))
        check_items(gold["items"], f"{path.parent.name}/gold.json")
        pages.append(gold | {"folder": path.parent})
    return pages


def check_items(items: list[dict], name: str) -> None:
    """`ValueError` for a gold item the scorer cannot use."""
    for i, item in enumerate(items):
        where = f"{name} item {i}"
        if not isinstance(item.get("page"), int) or item["page"] < 1 or not item.get("raw_text"):
            raise ValueError(f"{where}: needs a page number and raw_text")
        if item.get("date_type") not in ALL_TYPES:
            raise ValueError(f"{where}: date_type {item.get('date_type')!r} is not in the taxonomy")
        if ("normalized" in item) == ("candidates" in item):
            raise ValueError(f"{where}: give exactly one of normalized or candidates")
        if "candidates" in item and len(item["candidates"]) < 2:
            raise ValueError(f"{where}: an ambiguous date needs at least two candidates")


def cached_file(source: dict) -> Path:
    return CACHE_DIR / f"{source['id']}{source['ext']}"


# --- Running ----------------------------------------------------------------------------------


def evaluate(mode: str, which: str = "public") -> dict:
    # Imported here so the scorer (and its tests) do not load PDF, OCR and SDK libraries.
    from pharma_dates.claude_client import make_client
    from pharma_dates.config import Settings
    from pharma_dates.store import Store

    sources = load_sources() if which != "synth" else []
    missing = [s["id"] for s in sources if not cached_file(s).exists()]
    if missing:
        sys.exit(f"Not downloaded: {', '.join(missing)}. Run eval/fetch.py first.")
    pages = load_synth() if which != "public" else []
    if which != "public" and not pages:
        sys.exit("No synthetic pages. Run eval/synth.py generate first.")
    results: dict = {"mode": mode, "set": which}
    with tempfile.TemporaryDirectory() as tmp:
        settings = Settings(data_dir=Path(tmp), ai_enabled=mode == "on")
        client = make_client(settings)
        if mode == "on" and client is None:
            sys.exit("--ai on needs provider credentials in .env (see .env.example).")
        store = Store(Path(tmp) / "eval.sqlite")
        if sources:
            results["public"] = _evaluate_public(sources, store, settings, client)
        if pages:
            results["synth"] = _evaluate_synth(pages, store, settings, client)
    return results


def _run(path: Path, store, settings, client) -> tuple[list[LabeledDate], dict[int, str]]:
    from pharma_dates.pipeline import run_document

    run_id = run_document(path, path.name, store, settings, client)
    run = store.get_run(run_id)
    if run is None or run.status != "done":
        sys.exit(f"{path}: run did not finish ({run.error if run else 'missing'})")
    return store.dates_for_run(run_id), {page.n: page.text for page in store.pages_for_run(run_id)}


def _evaluate_public(sources: list[dict], store, settings, client) -> dict:
    documents, total = [], Scores({}, PRF(), 0, 0)
    for source in sources:
        dates, page_texts = _run(cached_file(source), store, settings, client)
        result = score(dates, load_gold(source["id"]), page_texts)
        total = total + result
        documents.append({"id": source["id"], **_summary(result)})
    return {"documents": documents, **_summary(total)}


def _evaluate_synth(pages: list[dict], store, settings, client) -> dict:
    """Each page's PNG, several at once (Tesseract runs in its own processes)."""
    os.environ.setdefault("OMP_THREAD_LIMIT", "1")  # one Tesseract thread per page, many pages

    def one(page: dict) -> Scores:
        dates, page_texts = _run(page["folder"] / "page.png", store, settings, client)
        result = score(dates, page["items"], page_texts, by="value")
        result.errors = [{"page_id": page["id"]} | e for e in result.errors]
        return result

    with ThreadPoolExecutor(max_workers=min(8, os.cpu_count() or 1)) as pool:
        scored = list(pool.map(one, pages))
    by_degradation: dict[str, Scores] = {}
    for page, result in zip(pages, scored):
        level = page["degradation"]
        by_degradation[level] = by_degradation.get(level, Scores({}, PRF(), 0, 0)) + result
    total = sum(scored, Scores({}, PRF(), 0, 0))
    levels = {
        level: _summary(s) | {"pages": sum(p["degradation"] == level for p in pages)}
        for level, s in by_degradation.items()
    }
    for summary in levels.values():
        del summary["errors"], summary["per_type"]
    return {"pages": len(pages), "by_degradation": levels, **_summary(total)}


def _summary(s: Scores) -> dict:
    return {
        "micro": s.micro.as_dict(),
        "detected": s.detected.as_dict(),
        "per_type": {t: prf.as_dict() for t, prf in sorted(s.per_type.items())},
        "hallucinations": s.hallucinations,
        "silent_resolutions": s.silent_resolutions,
        "errors": s.errors,
    }


def table(results: dict) -> str:
    rows = []
    if "public" in results:
        rows += [
            f"PUBLIC SET ({len(results['public']['documents'])} documents)",
            _type_table(results["public"]),
            "",
        ]
    if "synth" in results:
        synth = results["synth"]
        rows += [f"SYNTHETIC SET ({synth['pages']} pages)", _type_table(synth), "", _level_table(synth), ""]
    rows.append(f"AI: {results['mode']}")
    for name in ("public", "synth"):
        if name in results:
            r = results[name]
            rows.append(
                f"{name}: hallucinations {r['hallucinations']}   silent resolutions {r['silent_resolutions']}"
            )
    rows.append(f"gate: {'PASS' if passed(results) else 'FAIL'}")
    return "\n".join(rows)


def _type_table(results: dict) -> str:
    rows = [f"{'date type':<32}{'gold':>6}{'tp':>5}{'fp':>5}{'fn':>5}{'P':>7}{'R':>7}{'F1':>7}"]
    items = list(results["per_type"].items()) + [("micro (all types)", results["micro"])]
    items.append(("detected (type ignored)", results["detected"]))
    for name, m in items:
        rows.append(
            f"{name:<32}{m['tp'] + m['fn']:>6}{m['tp']:>5}{m['fp']:>5}{m['fn']:>5}"
            f"{m['precision']:>7.2f}{m['recall']:>7.2f}{m['f1']:>7.2f}"
        )
    return "\n".join(rows)


def _level_table(synth: dict) -> str:
    """Detection (type ignored) and typed scores per degradation level."""
    rows = [
        f"{'degradation':<14}{'pages':>6}{'gold':>6}{'det P':>7}{'det R':>7}{'typed P':>9}{'typed R':>9}{'hall':>6}"
    ]
    for level, s in synth["by_degradation"].items():
        d, m = s["detected"], s["micro"]
        rows.append(
            f"{level:<14}{s['pages']:>6}{d['tp'] + d['fn']:>6}{d['precision']:>7.2f}{d['recall']:>7.2f}"
            f"{m['precision']:>9.2f}{m['recall']:>9.2f}{s['hallucinations']:>6}"
        )
    return "\n".join(rows)


def passed(results: dict) -> bool:
    sets = [results[name] for name in ("public", "synth") if name in results]
    return all(r["hallucinations"] == 0 and r["silent_resolutions"] == 0 for r in sets)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--ai", choices=["on", "off"], required=True)
    parser.add_argument("--set", choices=SETS, default="public", dest="which")
    args = parser.parse_args()
    results = evaluate(args.ai, args.which)
    out = EVAL_DIR / f"results-{args.which}-{args.ai}.json"
    out.write_text(json.dumps(results, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(table(results))
    print(f"\nwritten: {out.relative_to(EVAL_DIR.parent)}")
    sys.exit(0 if passed(results) else 1)


if __name__ == "__main__":
    main()
