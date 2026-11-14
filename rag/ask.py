"""CLI interface for IRIS RAG Question Answering Engine.

Usage:
    python -m rag.ask "<question>" [--top-k 5] [--json]

Example:
    python -m rag.ask "What are the course objectives of Cloud Computing?" --top-k 5
"""

import argparse
import json
import sys
from typing import Sequence

from rag.pipeline import answer_question


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Ask questions grounded in PEC institutional documents using IRIS RAG."
    )
    parser.add_argument(
        "question",
        type=str,
        help="Natural language question.",
    )
    parser.add_argument(
        "--top-k",
        "-k",
        type=int,
        default=5,
        help="Number of chunks to retrieve for evidence context (default: 5).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output response as structured JSON.",
    )

    args = parser.parse_args(argv)

    if not args.question or not args.question.strip():
        print("Error: Question cannot be empty or whitespace.", file=sys.stderr)
        return 1

    try:
        response = answer_question(query=args.question, top_k=args.top_k)
    except EnvironmentError as exc:
        print(f"Configuration Error: {exc}", file=sys.stderr)
        return 2
    except ValueError as exc:
        print(f"Validation Error: {exc}", file=sys.stderr)
        return 3
    except Exception as exc:
        print(f"RAG Error: {exc}", file=sys.stderr)
        return 4

    if args.json:
        print(json.dumps(response.to_dict(), indent=2))
    else:
        print("=" * 80)
        print("IRIS RAG ANSWER ENGINE")
        print(f"Question: \"{args.question}\"")
        print("=" * 80)
        print()
        print(response.to_human_readable())
        print()
        print("=" * 80)

    return 0


if __name__ == "__main__":
    sys.exit(main())
