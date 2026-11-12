"""PDF discovery and content hashing for the IRIS ingestion pipeline.

Treats `documents/` as the complete input allowlist.
Computes deterministic SHA-256 hashes for change detection and provenance.
"""

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
from typing import List


@dataclass(frozen=True)
class DiscoveredPDF:
    """Metadata representing a discovered source PDF."""
    filename: str
    path: Path
    relative_path: str
    file_size_bytes: int
    sha256: str
    modified_at: float

    def to_dict(self) -> dict:
        return {
            "filename": self.filename,
            "path": str(self.path),
            "relative_path": self.relative_path,
            "file_size_bytes": self.file_size_bytes,
            "sha256": self.sha256,
            "modified_at": self.modified_at,
        }


def compute_sha256(file_path: Path | str, chunk_size: int = 65536) -> str:
    """Compute the SHA-256 hash of a file using chunked streaming."""
    hasher = hashlib.sha256()
    path = Path(file_path)
    with path.open("rb") as f:
        while chunk := f.read(chunk_size):
            hasher.update(chunk)
    return hasher.hexdigest()


def discover_pdfs(source_dir: Path | str = "documents") -> List[DiscoveredPDF]:
    """Discover all PDF files in the specified directory.
    
    Args:
        source_dir: Root directory for PDF discovery (default: documents).
        
    Returns:
        List of DiscoveredPDF objects sorted by filename.
    """
    directory = Path(source_dir).resolve()
    if not directory.exists() or not directory.is_dir():
        raise FileNotFoundError(f"Source documents directory not found: {directory}")

    discovered: List[DiscoveredPDF] = []
    
    for entry in directory.iterdir():
        if entry.is_file() and entry.suffix.lower() == ".pdf":
            file_stat = entry.stat()
            file_hash = compute_sha256(entry)
            discovered.append(
                DiscoveredPDF(
                    filename=entry.name,
                    path=entry,
                    relative_path=str(entry.relative_to(directory.parent)),
                    file_size_bytes=file_stat.st_size,
                    sha256=file_hash,
                    modified_at=file_stat.st_mtime,
                )
            )

    return sorted(discovered, key=lambda doc: doc.filename)
