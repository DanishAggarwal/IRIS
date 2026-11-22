"""Shortcut alias for running the unified IRIS ingestion pipeline.

Usage:
    python -m ingestion.run_all [--status] [--force] [--skip-embeddings]
"""

import sys
from pathlib import Path

# Delegate directly to scripts/ingest.py
from scripts.ingest import main

if __name__ == "__main__":
    sys.exit(main())
