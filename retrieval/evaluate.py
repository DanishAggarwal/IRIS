"""Retrieval evaluation runner for IRIS Milestone 7.

Measures Hit@1, Hit@3, and Hit@5 against the curated evaluation dataset
(data/retrieval_eval_dataset.json).

Usage:
    python -m retrieval.evaluate [--dataset-path data/retrieval_eval_dataset.json] [--top-k 5]
"""

import argparse
import json
import logging
from pathlib import Path
import sys
from typing import Any, Optional

from database.connection import SessionLocal
from retrieval.retriever import retrieve_relevant_chunks
from retrieval.result import RetrievalResult

logger = logging.getLogger(__name__)

DEFAULT_DATASET_PATH = (
    Path("eval") / "retrieval_eval_dataset.json"
    if (Path("eval") / "retrieval_eval_dataset.json").exists()
    else Path("data") / "retrieval_eval_dataset.json"
)


def check_hit(
    result: RetrievalResult,
    expected_doc: str,
    exp_pages: list[int],
    acceptable_sources: Optional[list[dict]] = None,
) -> bool:
    """Check if a retrieved chunk matches expected document/page range or acceptable sources."""
    if result.document.filename == expected_doc:
        exp_start, exp_end = exp_pages
        if max(result.chunk.start_page, exp_start) <= min(result.chunk.end_page, exp_end):
            return True

    if acceptable_sources:
        for src in acceptable_sources:
            if result.document.filename == src.get("document"):
                s_pages = src.get("pages", [])
                if len(s_pages) == 2:
                    if max(result.chunk.start_page, s_pages[0]) <= min(result.chunk.end_page, s_pages[1]):
                        return True

    return False


def evaluate_dataset(
    dataset_path: Path = DEFAULT_DATASET_PATH,
    top_k: int = 5,
    verbose: bool = True,
) -> dict[str, Any]:
    """Execute evaluation across all questions in the dataset and compute Hit@K metrics."""
    if not dataset_path.exists():
        raise FileNotFoundError(f"Evaluation dataset not found at: {dataset_path}")

    dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
    questions = dataset.get("questions", [])

    answerable = [q for q in questions if q.get("answerable", False)]
    unanswerable = [q for q in questions if not q.get("answerable", False)]

    hits_at_1 = 0
    hits_at_3 = 0
    hits_at_5 = 0

    per_question_results = []
    unanswerable_inspections = []

    # Use a single shared database session for all queries
    db = SessionLocal()
    try:
        if verbose:
            print("=" * 80)
            print("IRIS MILESTONE 7: RETRIEVAL EVALUATION")
            print(f"Dataset   : {dataset_path} ({len(questions)} questions total)")
            print(f"Answerable: {len(answerable)} | Unanswerable: {len(unanswerable)}")
            print(f"Top-K     : {top_k}")
            print("=" * 80)

        # 1. Evaluate answerable questions
        for idx, q in enumerate(answerable, start=1):
            qid = q["id"]
            query_str = q["query"]
            exp_doc = q["expected_document"]
            exp_pages = q["expected_pages"]

            results = retrieve_relevant_chunks(query=query_str, top_k=top_k, session=db)

            acc_sources = q.get("acceptable_sources")

            # Determine rank of first hit
            hit_rank: Optional[int] = None
            for r in results:
                if check_hit(r, exp_doc, exp_pages, acceptable_sources=acc_sources):
                    hit_rank = r.rank
                    break

            is_hit_1 = hit_rank is not None and hit_rank <= 1
            is_hit_3 = hit_rank is not None and hit_rank <= 3
            is_hit_5 = hit_rank is not None and hit_rank <= 5

            if is_hit_1:
                hits_at_1 += 1
            if is_hit_3:
                hits_at_3 += 1
            if is_hit_5:
                hits_at_5 += 1

            record = {
                "id": qid,
                "category": q.get("category"),
                "query": query_str,
                "expected_document": exp_doc,
                "expected_pages": exp_pages,
                "hit_rank": hit_rank,
                "hit_at_1": is_hit_1,
                "hit_at_3": is_hit_3,
                "hit_at_5": is_hit_5,
                "top_result": (
                    {
                        "rank": results[0].rank,
                        "document": results[0].document.filename,
                        "pages": [results[0].chunk.start_page, results[0].chunk.end_page],
                        "cosine_distance": round(results[0].cosine_distance, 4),
                        "similarity": round(results[0].similarity_score, 4),
                    }
                    if results
                    else None
                ),
            }
            per_question_results.append(record)

            if verbose:
                status_str = f"HIT (Rank {hit_rank})" if hit_rank is not None else "MISS"
                top_d = f"{results[0].document.filename[:20]} P{results[0].chunk.start_page}-{results[0].chunk.end_page}" if results else "None"
                print(f"[{qid}] {status_str:<14} | Top1: {top_d:<28} | Query: \"{query_str[:45]}\"")

        # 2. Inspect unanswerable questions
        if verbose:
            print("\n" + "-" * 80)
            print("UNANSWERABLE QUESTIONS INSPECTION (retrieval distances on out-of-corpus queries)")
            print("-" * 80)

        for q in unanswerable:
            qid = q["id"]
            query_str = q["query"]
            results = retrieve_relevant_chunks(query=query_str, top_k=top_k, session=db)
            top_res = results[0] if results else None
            record = {
                "id": qid,
                "query": query_str,
                "explanation": q.get("relevance_explanation"),
                "top_result": (
                    {
                        "document": top_res.document.filename,
                        "pages": [top_res.chunk.start_page, top_res.chunk.end_page],
                        "cosine_distance": round(top_res.cosine_distance, 4),
                        "similarity": round(top_res.similarity_score, 4),
                    }
                    if top_res
                    else None
                ),
            }
            unanswerable_inspections.append(record)
            if verbose and top_res:
                print(f"[{qid}] Dist: {top_res.cosine_distance:.4f} | Nearest: {top_res.document.filename[:25]} P{top_res.chunk.start_page}-{top_res.chunk.end_page} | Query: \"{query_str[:40]}\"")

    finally:
        db.close()

    total_ans = len(answerable)
    pct_hit_1 = (hits_at_1 / total_ans * 100.0) if total_ans > 0 else 0.0
    pct_hit_3 = (hits_at_3 / total_ans * 100.0) if total_ans > 0 else 0.0
    pct_hit_5 = (hits_at_5 / total_ans * 100.0) if total_ans > 0 else 0.0

    summary = {
        "total_questions": len(questions),
        "answerable_count": total_ans,
        "unanswerable_count": len(unanswerable),
        "metrics": {
            "hit_at_1": hits_at_1,
            "hit_at_1_pct": round(pct_hit_1, 2),
            "hit_at_3": hits_at_3,
            "hit_at_3_pct": round(pct_hit_3, 2),
            "hit_at_5": hits_at_5,
            "hit_at_5_pct": round(pct_hit_5, 2),
        },
        "per_question_results": per_question_results,
        "unanswerable_inspections": unanswerable_inspections,
    }

    if verbose:
        print("\n" + "=" * 80)
        print("RETRIEVAL EVALUATION SUMMARY")
        print("=" * 80)
        print(f"Answerable Questions : {total_ans}")
        print(f"Hit@1                : {hits_at_1} / {total_ans} ({pct_hit_1:.1f}%)")
        print(f"Hit@3                : {hits_at_3} / {total_ans} ({pct_hit_3:.1f}%)")
        print(f"Hit@5                : {hits_at_5} / {total_ans} ({pct_hit_5:.1f}%)")
        print(f"Initial 80% Target   : {'ACHIEVED' if pct_hit_5 >= 80.0 else 'NOT ACHIEVED'}")
        print("=" * 80)

    return summary


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run IRIS Milestone 7 retrieval evaluation.")
    parser.add_argument(
        "--dataset-path",
        type=Path,
        default=DEFAULT_DATASET_PATH,
        help="Path to evaluation dataset JSON.",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=5,
        help="Number of chunks retrieved per query (default: 5).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output evaluation summary as JSON.",
    )

    args = parser.parse_args(argv)

    try:
        summary = evaluate_dataset(
            dataset_path=args.dataset_path,
            top_k=args.top_k,
            verbose=not args.json,
        )
    except Exception as exc:
        print(f"Evaluation error: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(summary, indent=2))

    return 0


if __name__ == "__main__":
    sys.exit(main())
