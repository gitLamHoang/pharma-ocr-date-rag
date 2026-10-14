"""Compare indexed BM25 and the former cosine scorer on authored synthetic development cases."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pharma_ocr_date_rag.experiments import cosine_baseline, score_rankings
from pharma_ocr_date_rag.rag import RetrievalIndex, split_chunks

REPORT = ROOT / "reports/retrieval_quality.json"


def build() -> dict:
    fixture_path = ROOT / "data/retrieval_cases.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    paths = [ROOT / path for path in fixture["documents"]]
    chunks = []
    for path in paths:
        chunks.extend(
            split_chunks(
                path.name,
                path.read_text(encoding="utf-8"),
                max_words=fixture["chunk_words"],
                overlap=fixture["overlap"],
                date_order="mdy",
            )
        )
    index = RetrievalIndex(chunks)
    if len(chunks) > index.MAX_TOP_K:
        raise ValueError("Evaluation corpus exceeds search cutoff; revise document aggregation explicitly")
    queries = fixture["queries"]
    if len({query["id"] for query in queries}) != len(queries):
        raise ValueError("Query IDs must be unique")
    known_docs = {path.name for path in paths}
    if any(set(query["relevant_documents"]) - known_docs for query in queries):
        raise ValueError("Judgment references an unknown document")
    comparisons = {}
    for name in ("cosine_baseline", "bm25"):
        rows = []
        for query in queries:
            results = (
                index.search(query["question"], top_k=len(chunks))
                if name == "bm25"
                else cosine_baseline(chunks, query["question"], top_k=len(chunks))
            )
            # Document score is its best chunk score. Deduplicate before the cutoff.
            ranking = list(dict.fromkeys(result.chunk.doc_id for result in results))[: fixture["top_k"]]
            rows.append(
                {
                    "id": query["id"],
                    "question": query["question"],
                    "relevant_documents": query["relevant_documents"],
                    "retrieved_documents": ranking,
                    "judgment": query["judgment"],
                }
            )
        comparisons[name] = {
            "metrics": score_rankings(
                [row["retrieved_documents"] for row in rows],
                [row["relevant_documents"] for row in rows],
                top_k=fixture["top_k"],
            ),
            "queries": rows,
        }
    source_paths = [
        fixture_path,
        *paths,
        Path(__file__).resolve(),
        *(
            ROOT / "src/pharma_ocr_date_rag" / name
            for name in ("rag.py", "experiments.py", "dates.py", "languages.py")
        ),
    ]
    return {
        "schema_version": 1,
        "scope": fixture["scope"],
        "relevance_unit": fixture["relevance_unit"],
        "protocol": {
            "documents": len(paths),
            "chunks": len(chunks),
            "chunk_words": fixture["chunk_words"],
            "overlap": fixture["overlap"],
            "top_k": fixture["top_k"],
            "date_order": "mdy",
            "bm25": {"k1": index.config.k1, "b": index.config.b},
            "aggregation": "Maximum chunk score per document, deterministic source-ID ties.",
            "metric_denominators": "Ranking means use answerable queries only. Abstention uses no-match queries only. Precision divides by k even when fewer results are returned. Binary nDCG uses log2 discount.",
            "limitations": "No semantic embeddings, entailment check, generation, or unknown-entity detector. A shared date-field keyword can retrieve evidence for the wrong vendor. Parameters were not tuned on an independent validation set.",
        },
        "comparisons": comparisons,
        "source_sha256": {
            str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in source_paths
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="Verify the committed report without modifying it"
    )
    args = parser.parse_args()
    report = build()
    serialized = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if args.check:
        if not REPORT.exists() or REPORT.read_text(encoding="utf-8") != serialized:
            parser.exit(
                1,
                "Retrieval report differs; run scripts/benchmark_retrieval_quality.py and inspect the changes.\n",
            )
    else:
        REPORT.write_text(serialized, encoding="utf-8")
    for method, comparison in report["comparisons"].items():
        print(f"{method}: {json.dumps(comparison['metrics'], sort_keys=True)}")
    print("Authored synthetic development cases only; not held-out accuracy.")


if __name__ == "__main__":
    main()
