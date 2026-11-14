"""CLI interface for IRIS semantic retrieval.

Usage:
    python -m retrieval.search "<query>" [--top-k 5] [--json]

Example:
    python -m retrieval.search "What are the course objectives?" --top-k 5
"""

import argparse
import json
import sys
from typing import Sequence

from retrieval.retriever import retrieve_relevant_chunks


def format_page_range(start_page: int, end_page: int) -> str:
    """Format human-readable 1-based page range."""
    if start_page == end_page:
        return f"Page {start_page}"
    return f"Pages {start_page}–{end_page}"


def render_terminal_results(query: str, results: list) -> None:
    """Render retrieval results in terminal-friendly format with clear provenance."""
    print("=" * 80)
    print(f"IRIS SEMANTIC RETRIEVAL")
    print(f"Query : \"{query}\"")
    print(f"Total : {len(results)} chunks retrieved")
    print(f"Metric: Cosine Distance (0.00 = identical direction; lower distance = closer match)")
    print("=" * 80)

    if not results:
        print("\nNo matching document chunks found in database.")
        return

    for res in results:
        doc = res.document
        chunk = res.chunk
        page_str = format_page_range(chunk.start_page, chunk.end_page)
        sec_str = f" | Section: {chunk.section_title}" if chunk.section_title else ""
        table_str = " [Table Included]" if chunk.has_table else ""

        print(f"\n[Rank {res.rank} / {len(results)}] Cosine Distance: {res.cosine_distance:.6f} (Similarity: {res.similarity_score:.6f})")
        print(f"  Source  : {doc.filename}")
        print(f"  Location: {page_str}{sec_str}{table_str}")
        print(f"  Chunk ID: {chunk.id} (index: {chunk.chunk_index}, tokens: {chunk.token_count})")
        print("  " + "-" * 76)

        # Print indented chunk text
        lines = chunk.chunk_text.strip().splitlines()
        preview = "\n  ".join(lines)
        print(f"  {preview}")
        print("  " + "-" * 76)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Search IRIS document corpus using natural-language semantic similarity."
    )
    parser.add_argument(
        "query",
        type=str,
        help="Natural language query string.",
    )
    parser.add_argument(
        "--top-k",
        "-k",
        type=int,
        default=5,
        help="Number of nearest chunks to retrieve (default: 5, max: 100).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output raw results as structured JSON.",
    )

    args = parser.parse_args(argv)

    if not args.query or not args.query.strip():
        print("Error: Search query cannot be empty or whitespace.", file=sys.stderr)
        return 1

    try:
        results = retrieve_relevant_chunks(query=args.query, top_k=args.top_k)
    except EnvironmentError as exc:
        print(f"Configuration Error: {exc}", file=sys.stderr)
        return 2
    except ValueError as exc:
        print(f"Validation Error: {exc}", file=sys.stderr)
        return 3
    except Exception as exc:
        print(f"Retrieval Error: {exc}", file=sys.stderr)
        return 4

    if args.json:
        data = {
            "query": args.query,
            "top_k": args.top_k,
            "results": [r.to_dict() for r in results],
        }
        print(json.dumps(data, indent=2))
    else:
        render_terminal_results(query=args.query, results=results)

    return 0


if __name__ == "__main__":
    sys.exit(main())
