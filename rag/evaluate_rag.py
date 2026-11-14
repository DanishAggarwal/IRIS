"""Evaluation suite for IRIS RAG Answer Engine.

Evaluates against curated dataset in eval/rag_eval_dataset.json measuring:
1. Final status classification accuracy (answered, clarification_needed, handoff_recommended).
2. Citation existence accuracy (reference matches an actual retrieved chunk).
3. Citation provenance accuracy (page range overlap matches chunk).
4. Claim-level evidence support (factual and numerical claims substantiated by text).
5. Factual coverage of key ground truth terms.
6. Safe handoff accuracy (explains missing evidence without hallucinating contact info).
"""

import json
import logging
import os
from pathlib import Path
import sys
import time
from typing import Any, Optional

from database.connection import SessionLocal
from rag.models import AnswerStatus, RAGResponse
from rag.pipeline import answer_question

logger = logging.getLogger(__name__)

DEFAULT_DATASET_PATH = Path("eval") / "rag_eval_dataset.json"


def evaluate_rag_engine(
    dataset_path: Path = DEFAULT_DATASET_PATH,
    top_k: int = 5,
    verbose: bool = True,
) -> dict[str, Any]:
    """Run full evaluation suite across the curated RAG benchmark questions."""
    if not dataset_path.exists():
        raise FileNotFoundError(f"Evaluation dataset not found at {dataset_path}")

    with open(dataset_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    questions = data.get("questions", [])
    total_count = len(questions)

    # Metrics counters
    status_matches = 0
    total_answered_evaluated = 0
    total_handoff_evaluated = 0

    citation_exist_count = 0
    citation_prov_count = 0
    claim_support_count = 0
    total_citations_evaluated = 0

    fact_covered_count = 0
    safe_handoff_passed = 0

    per_question_results = []

    db = SessionLocal()
    try:
        if verbose:
            print("=" * 80)
            print("IRIS MILESTONE 8: RAG ANSWER ENGINE EVALUATION")
            print(f"Dataset   : {dataset_path} ({total_count} questions total)")
            print(f"Top-K     : {top_k}")
            print("=" * 80)

        for q in questions:
            qid = q["id"]
            query_str = q["query"]
            exp_status = q["expected_status"]
            exp_facts = q.get("expected_facts", [])

            response: RAGResponse = answer_question(
                query=query_str,
                top_k=top_k,
                session=db,
            )

            # 1. Final status classification check
            status_match = response.status == exp_status
            if status_match:
                status_matches += 1

            # 2. Answered question evaluations (citations, claims, facts)
            q_citations_ok = True
            q_exist_ok = True
            q_prov_ok = True
            q_claim_ok = True

            if exp_status == AnswerStatus.ANSWERED.value:
                total_answered_evaluated += 1
                if not response.citations:
                    q_citations_ok = False
                else:
                    for c in response.citations:
                        total_citations_evaluated += 1
                        if c.exists_in_retrieval:
                            citation_exist_count += 1
                        else:
                            q_exist_ok = False

                        if c.provenance_valid:
                            citation_prov_count += 1
                        else:
                            q_prov_ok = False

                        if c.claim_supported:
                            claim_support_count += 1
                        else:
                            q_claim_ok = False

                        if not c.is_valid:
                            q_citations_ok = False

                # 3. Fact coverage check
                ans_str = response.answer or ""
                ans_lower = ans_str.lower()
                facts_present = 0
                for f in exp_facts:
                    if f.lower() in ans_lower:
                        facts_present += 1
                coverage = (facts_present / len(exp_facts)) if exp_facts else 1.0
                if coverage >= 0.5:
                    fact_covered_count += 1

            # 4. Handoff quality evaluation
            if exp_status == AnswerStatus.HANDOFF_RECOMMENDED.value:
                total_handoff_evaluated += 1
                rec_str = (response.handoff_recommendation or "").lower()
                # Check for safe handoff: non-empty, neutral or valid authority, no fabricated emails/phones
                has_rec = len(rec_str) > 10
                no_fake_phone = not any(char.isdigit() for char in rec_str if rec_str.count(char) > 5)
                no_fake_email = "@" not in rec_str
                no_fake_ticket = "ticket" not in rec_str and "case #" not in rec_str

                if has_rec and no_fake_phone and no_fake_email and no_fake_ticket:
                    safe_handoff_passed += 1

            ans_preview = (response.answer or "")[:150] + ("..." if len(response.answer or "") > 150 else "")
            record = {
                "id": qid,
                "category": q.get("category"),
                "query": query_str,
                "expected_status": exp_status,
                "actual_status": response.status,
                "internal_status": response.internal_status,
                "status_match": status_match,
                "citations_count": len(response.citations),
                "citations": [c.to_dict() for c in response.citations],
                "answer_preview": ans_preview,
                "clarification": response.clarification_question,
                "handoff": response.handoff_recommendation,
                "limitations": response.limitations,
            }
            per_question_results.append(record)

            if verbose:
                status_str = f"STATUS: {response.status} (exp: {exp_status})"
                c_str = f"Cites: {len(response.citations)}"
                print(f"[{qid}] {'PASS' if status_match else 'FAIL':4} | {status_str:<45} | {c_str:<10} | \"{query_str[:35]}\"")

            time.sleep(0.5)

    finally:
        db.close()

    pct_status = (status_matches / total_count * 100.0) if total_count > 0 else 0.0
    pct_cit_exist = (citation_exist_count / total_citations_evaluated * 100.0) if total_citations_evaluated > 0 else 100.0
    pct_cit_prov = (citation_prov_count / total_citations_evaluated * 100.0) if total_citations_evaluated > 0 else 100.0
    pct_claim_supp = (claim_support_count / total_citations_evaluated * 100.0) if total_citations_evaluated > 0 else 100.0
    pct_facts = (fact_covered_count / total_answered_evaluated * 100.0) if total_answered_evaluated > 0 else 0.0
    pct_handoff = (safe_handoff_passed / total_handoff_evaluated * 100.0) if total_handoff_evaluated > 0 else 100.0

    summary = {
        "total_questions": total_count,
        "status_accuracy_pct": round(pct_status, 2),
        "citation_existence_pct": round(pct_cit_exist, 2),
        "citation_provenance_pct": round(pct_cit_prov, 2),
        "claim_support_pct": round(pct_claim_supp, 2),
        "fact_coverage_pct": round(pct_facts, 2),
        "safe_handoff_accuracy_pct": round(pct_handoff, 2),
        "metrics": {
            "status_matches": f"{status_matches}/{total_count}",
            "citation_existence": f"{citation_exist_count}/{total_citations_evaluated}",
            "citation_provenance": f"{citation_prov_count}/{total_citations_evaluated}",
            "claim_support": f"{claim_support_count}/{total_citations_evaluated}",
            "fact_covered": f"{fact_covered_count}/{total_answered_evaluated}",
            "safe_handoff": f"{safe_handoff_passed}/{total_handoff_evaluated}",
        },
        "per_question_results": per_question_results,
    }

    if verbose:
        print("\n" + "=" * 80)
        print("RAG EVALUATION SUMMARY")
        print("=" * 80)
        print(f"Total Questions Evaluated : {total_count}")
        print(f"Status Classification Acc : {status_matches} / {total_count} ({pct_status:.1f}%)")
        print(f"Citation Existence Acc    : {citation_exist_count} / {total_citations_evaluated} ({pct_cit_exist:.1f}%)")
        print(f"Citation Provenance Acc   : {citation_prov_count} / {total_citations_evaluated} ({pct_cit_prov:.1f}%)")
        print(f"Claim-Level Support Acc   : {claim_support_count} / {total_citations_evaluated} ({pct_claim_supp:.1f}%)")
        print(f"Factual Coverage Passed   : {fact_covered_count} / {total_answered_evaluated} ({pct_facts:.1f}%)")
        print(f"Safe Handoff Accuracy     : {safe_handoff_passed} / {total_handoff_evaluated} ({pct_handoff:.1f}%)")
        print("=" * 80)

        # Highlight key audit questions
        print("\nTARGETED AUDIT QUESTIONS:")
        for r in per_question_results:
            if r["id"] in ["Q31", "Q34", "Q36"]:
                print(f"- [{r['id']}] Query: \"{r['query']}\"")
                print(f"    Expected Status : {r['expected_status']}")
                print(f"    Actual Status   : {r['actual_status']} (Internal: {r.get('internal_status')})")
                print(f"    Match           : {'PASS' if r['status_match'] else 'FAIL'}")
                if r.get("clarification"):
                    print(f"    Clarification   : {r['clarification']}")
                if r.get("handoff"):
                    print(f"    Handoff Rec     : {r['handoff']}")
                print(f"    Answer Preview  : {r['answer_preview']}")

    return summary


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    evaluate_rag_engine()
