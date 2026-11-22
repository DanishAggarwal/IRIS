"""Approved document acquisition, validation, duplicate detection, and IRIS ingestion coordinator.

Implements Phase 3:
1. Validated streaming download of approved documents with strict domain checks.
2. Binary PDF validation (magic header and PyMuPDF structure check).
3. SHA-256 calculation and duplicate content detection.
4. Safe handoff to existing IRIS ingestion pipeline.
5. Verification of database records (Document, Pages, Chunks, Embeddings).
6. Non-destructive catalogue status transitions and audit logging.
"""

from datetime import datetime, timezone
import hashlib
import logging
import os
from pathlib import Path
import re
import tempfile
import threading
from typing import Optional, Tuple
import uuid

import httpx
import pymupdf
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from crawler.engine import is_pec_domain
from database.connection import SessionLocal
from database.models import DiscoveredDocument, Document, DocumentApprovalAudit, DocumentChunk, User
from ingestion.pipeline import DOCUMENTS_DIR
from scripts.ingest import run_full_pipeline

logger = logging.getLogger(__name__)

# Constants
MAX_DOWNLOAD_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB
DEFAULT_TIMEOUT_SECONDS = 30.0
PDF_MAGIC_BYTES = b"%PDF-"

# Concurrency & Serialization Controls
_PIPELINE_LOCK = threading.Lock()
_ACTIVE_INGESTIONS: set[uuid.UUID] = set()
_ACTIVE_INGESTIONS_LOCK = threading.Lock()


def verify_local_pdf(
    file_path: Path, expected_sha256: Optional[str] = None
) -> Tuple[bool, Optional[str], Optional[str]]:
    """Verify that a local file exists, is a valid PDF, and matches the expected SHA-256.

    Returns:
        (is_valid, computed_sha256, error_reason)
    """
    if not file_path.is_file():
        return False, None, f"Local file '{file_path}' does not exist or is not a file."

    try:
        with file_path.open("rb") as f:
            header = f.read(5)
        if header != PDF_MAGIC_BYTES:
            return False, None, f"Local file '{file_path.name}' has invalid magic header {header!r}."

        doc = pymupdf.open(str(file_path))
        page_count = doc.page_count
        doc.close()
        if page_count < 1:
            return False, None, f"Local file '{file_path.name}' contains 0 pages."

        computed_sha256 = hashlib.sha256(file_path.read_bytes()).hexdigest()
        if expected_sha256 and computed_sha256 != expected_sha256:
            return False, computed_sha256, (
                f"Local file '{file_path.name}' SHA-256 mismatch "
                f"(expected {expected_sha256}, got {computed_sha256})."
            )

        return True, computed_sha256, None
    except Exception as exc:
        return False, None, f"Local file verification error: {exc}"


def recover_stale_ingestions_on_startup(session: Session) -> int:
    """Recover interrupted acquisition and ingestion operations left from a previous application run.

    - Documents left in 'downloading' -> marked 'download_failed'.
    - Documents left in 'ingesting' -> marked 'ingest_failed'.
    - Validated local files in documents/ are preserved so admins can retry them cleanly.
    - Appends immutable audit records for recovered operations.
    """
    stale_docs = list(
        session.scalars(
            select(DiscoveredDocument).where(
                DiscoveredDocument.status.in_(["downloading", "ingesting"])
            )
        ).all()
    )
    if not stale_docs:
        return 0

    now = datetime.now(timezone.utc)
    for doc in stale_docs:
        prev_status = doc.status
        if prev_status == "downloading":
            doc.status = "download_failed"
            doc.error_message = "Download interrupted by application restart."
            audit = DocumentApprovalAudit(
                document_id=doc.id,
                admin_email="system@startup.recovery",
                action="download_failed",
                previous_status="downloading",
                new_status="download_failed",
                reason="Download interrupted by application restart.",
                created_at=now,
            )
            session.add(audit)
        elif prev_status == "ingesting":
            doc.status = "ingest_failed"
            doc.error_message = "Ingestion interrupted by application restart."
            audit = DocumentApprovalAudit(
                document_id=doc.id,
                admin_email="system@startup.recovery",
                action="ingest_failed",
                previous_status="ingesting",
                new_status="ingest_failed",
                reason="Ingestion interrupted by application restart (local file preserved for retry).",
                created_at=now,
            )
            session.add(audit)

    session.commit()
    logger.warning("Recovered %d interrupted document acquisition/ingestion operations on startup.", len(stale_docs))
    return len(stale_docs)


def sanitize_pdf_filename(title: str, download_url: str, max_length: int = 80) -> str:
    """Generate a clean, filesystem-safe filename ending with .pdf."""
    candidate = title.strip() if title else ""
    if not candidate:
        candidate = download_url.rstrip("/").split("/")[-1]
    
    if candidate.lower().endswith(".pdf"):
        candidate = candidate[:-4]
    
    safe = re.sub(r"[^\w\-]+", "_", candidate).strip("_")
    if not safe:
        safe = f"pec_doc_{uuid.uuid4().hex[:8]}"
    
    if len(safe) > max_length:
        safe = safe[:max_length].rstrip("_")
    
    return f"{safe}.pdf"


def download_and_validate_pdf(
    url: str,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    max_bytes: int = MAX_DOWNLOAD_SIZE_BYTES,
    client: Optional[httpx.Client] = None,
) -> Tuple[Path, str, int]:
    """Download a document, validating domain boundaries, file size, magic header, and PDF structure.

    Returns:
        (temp_file_path, sha256_hash, file_size_bytes)

    Raises:
        ValueError: If domain security, size limit, magic header, or PDF structure checks fail.
        RuntimeError: If HTTP download returns non-200 or network fails.
    """
    if not is_pec_domain(url):
        raise ValueError(f"Security error: Download URL '{url}' is outside authorized PEC domains.")

    owns_client = False
    if client is None:
        client = httpx.Client(timeout=timeout, follow_redirects=True)
        owns_client = True

    temp_file = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    temp_path = Path(temp_file.name)
    hasher = hashlib.sha256()
    total_bytes = 0

    try:
        with client.stream("GET", url) as response:
            if response.status_code != 200:
                raise RuntimeError(
                    f"Remote server returned HTTP {response.status_code} while fetching '{url}'."
                )

            for hop in response.history:
                if not is_pec_domain(str(hop.url)):
                    raise ValueError(
                        f"Security error: Redirect hop '{hop.url}' points outside authorized PEC domains."
                    )
            if not is_pec_domain(str(response.url)):
                raise ValueError(
                    f"Security error: Final redirected URL '{response.url}' is outside authorized PEC domains."
                )

            reported_len = response.headers.get("Content-Length")
            if reported_len and reported_len.isdigit() and int(reported_len) > max_bytes:
                raise ValueError(
                    f"File size ({int(reported_len)} bytes) exceeds maximum limit of {max_bytes} bytes."
                )

            for chunk in response.iter_bytes(chunk_size=65536):
                total_bytes += len(chunk)
                if total_bytes > max_bytes:
                    raise ValueError(
                        f"Downloaded content exceeded maximum allowed limit of {max_bytes} bytes."
                    )
                temp_file.write(chunk)
                hasher.update(chunk)

        temp_file.flush()
        temp_file.close()

        with temp_path.open("rb") as f:
            header = f.read(5)
            if header != PDF_MAGIC_BYTES:
                raise ValueError(
                    f"Invalid document format: expected PDF magic header '%PDF-', got '{header!r}'."
                )

        try:
            doc = pymupdf.open(str(temp_path))
            page_count = doc.page_count
            doc.close()
            if page_count < 1:
                raise ValueError("PDF document contains 0 pages.")
        except Exception as exc:
            raise ValueError(f"Corrupt or unreadable PDF document: {exc}")

        sha256 = hasher.hexdigest()
        logger.info(
            "Successfully downloaded and validated PDF from %s (%d bytes, SHA-256: %s)",
            url,
            total_bytes,
            sha256,
        )
        return temp_path, sha256, total_bytes

    except Exception:
        if temp_path.exists():
            try:
                temp_file.close()
                temp_path.unlink(missing_ok=True)
            except Exception:
                pass
        raise
    finally:
        if owns_client:
            client.close()


def acquire_and_ingest_document(
    document_id: uuid.UUID,
    admin_user: User,
    documents_dir: Path = DOCUMENTS_DIR,
    force_reingest: bool = False,
    http_client: Optional[httpx.Client] = None,
    session: Optional[Session] = None,
) -> DiscoveredDocument:
    """Execute complete approved document acquisition, duplicate check, and IRIS ingestion."""
    # 0. Concurrency lock per document
    with _ACTIVE_INGESTIONS_LOCK:
        if document_id in _ACTIVE_INGESTIONS:
            raise RuntimeError(f"Acquisition for document {document_id} is already in progress.")
        _ACTIVE_INGESTIONS.add(document_id)

    owns_session = False
    if session is None:
        session = SessionLocal(expire_on_commit=False)
        owns_session = True

    try:
        doc = session.get(DiscoveredDocument, document_id)
        if not doc:
            raise ValueError(f"Discovered document with ID '{document_id}' not found.")

        # 1. State check
        if doc.status == "rejected":
            raise ValueError(f"Document '{doc.title}' is rejected and cannot be ingested.")
        if doc.status == "ingested" and not force_reingest:
            logger.info("Document '%s' (%s) is already ingested.", doc.title, doc.id)
            session.refresh(doc)
            return doc
        if doc.status not in ("approved", "downloading", "download_failed", "ingest_failed") and not force_reingest:
            raise ValueError(
                f"Document '{doc.title}' cannot be ingested because its status is '{doc.status}'. "
                "Only approved documents (or retried failed documents) can be ingested."
            )

        now = datetime.now(timezone.utc)
        prev_status = doc.status

        user_in_db = session.get(User, admin_user.id) if admin_user and getattr(admin_user, "id", None) else None
        admin_id = user_in_db.id if user_in_db else None

        documents_dir = Path(documents_dir).resolve()
        documents_dir.mkdir(parents=True, exist_ok=True)

        # 2. Check if local file can be reused on retry
        can_reuse_local = False
        target_path: Optional[Path] = None
        sha256: Optional[str] = None
        temp_path: Optional[Path] = None

        if doc.local_filename:
            candidate_local = documents_dir / doc.local_filename
            is_valid, computed_hash, reason = verify_local_pdf(
                candidate_local, expected_sha256=doc.sha256
            )
            if is_valid:
                can_reuse_local = True
                target_path = candidate_local
                sha256 = computed_hash
                logger.info(
                    "Reusing verified existing local PDF for document %s: %s (SHA-256: %s)",
                    doc.id,
                    target_path.name,
                    sha256,
                )
            else:
                logger.warning(
                    "Cannot reuse local file for document %s: %s. Will proceed with fresh download.",
                    doc.id,
                    reason,
                )

        if can_reuse_local:
            # Transition directly to ingesting
            doc.status = "ingesting"
            doc.error_message = None
            audit_reuse = DocumentApprovalAudit(
                document_id=doc.id,
                admin_user_id=admin_id,
                admin_email=admin_user.email,
                action="ingest_resumed",
                previous_status=prev_status,
                new_status="ingesting",
                reason=f"Retrying ingestion reusing verified local file '{target_path.name}'.",
                created_at=now,
            )
            session.add(audit_reuse)
            session.commit()
        else:
            # Transition to downloading
            doc.status = "downloading"
            doc.error_message = None

            audit_start = DocumentApprovalAudit(
                document_id=doc.id,
                admin_user_id=admin_id,
                admin_email=admin_user.email,
                action="ingest_started",
                previous_status=prev_status,
                new_status="downloading",
                reason="Administrator triggered document acquisition and ingestion.",
                created_at=now,
            )
            session.add(audit_start)
            session.commit()

            # Step 2: Download & Validate PDF
            try:
                temp_path, sha256, file_size = download_and_validate_pdf(
                    url=doc.download_url,
                    client=http_client,
                )
            except Exception as exc:
                logger.error("Download failed for document %s: %s", document_id, exc)
                doc.status = "download_failed"
                doc.error_message = f"Download failed: {exc}"
                audit_fail = DocumentApprovalAudit(
                    document_id=doc.id,
                    admin_user_id=admin_id,
                    admin_email=admin_user.email,
                    action="download_failed",
                    previous_status="downloading",
                    new_status="download_failed",
                    reason=str(exc),
                    created_at=datetime.now(timezone.utc),
                )
                session.add(audit_fail)
                session.commit()
                session.refresh(doc)
                return doc

            # Step 3: Duplicate Content Detection
            doc.downloaded_at = datetime.now(timezone.utc)
            doc.sha256 = sha256

            existing_iris_doc = session.scalar(
                select(Document).where(Document.sha256 == sha256)
            )

            if existing_iris_doc and existing_iris_doc.status == "complete":
                logger.info(
                    "Duplicate content detected: SHA-256 %s already ingested as '%s' (id: %s). "
                    "Linking catalogue record without re-ingesting.",
                    sha256,
                    existing_iris_doc.filename,
                    existing_iris_doc.id,
                )
                if temp_path and temp_path.exists():
                    temp_path.unlink(missing_ok=True)

                doc.status = "ingested"
                doc.change_status = "unchanged"
                doc.ingested_document_id = existing_iris_doc.id
                doc.local_filename = existing_iris_doc.filename
                doc.ingested_at = datetime.now(timezone.utc)
                doc.error_message = None

                audit_dup = DocumentApprovalAudit(
                    document_id=doc.id,
                    admin_user_id=admin_id,
                    admin_email=admin_user.email,
                    action="ingest_completed",
                    previous_status="downloading",
                    new_status="ingested",
                    reason=f"Content already ingested as '{existing_iris_doc.filename}' (SHA-256 duplicate matched).",
                    created_at=datetime.now(timezone.utc),
                )
                session.add(audit_dup)
                session.commit()
                session.refresh(doc)
                return doc

            # Step 4: Move validated file into documents/ directory
            base_filename = sanitize_pdf_filename(doc.title, doc.download_url)
            target_path = documents_dir / base_filename

            if target_path.exists():
                existing_file_hash = hashlib.sha256(target_path.read_bytes()).hexdigest()
                if existing_file_hash != sha256:
                    stem = target_path.stem
                    target_path = documents_dir / f"{stem}_{sha256[:8]}.pdf"

            if temp_path and temp_path.exists():
                import shutil
                shutil.move(str(temp_path), str(target_path))
                logger.info("Moved validated PDF to %s", target_path)

            # Step 5: Transition to ingesting
            doc.status = "ingesting"
            doc.local_filename = target_path.name
            session.commit()

        # Step 6: Trigger Existing Ingestion Pipeline (Serialized)
        pipeline_error: Optional[str] = None
        try:
            logger.info("Acquiring pipeline lock for %s...", target_path.name)
            with _PIPELINE_LOCK:
                logger.info("Triggering IRIS unified ingestion pipeline for %s...", target_path.name)
                exit_code = run_full_pipeline(force=False, skip_embeddings=False)
                if exit_code != 0:
                    pipeline_error = f"Ingestion pipeline runner returned exit code {exit_code}."
        except Exception as exc:
            logger.error("Ingestion pipeline failed: %s", exc, exc_info=True)
            pipeline_error = str(exc)

        # Step 7: Verify Ingestion in Database
        iris_doc = session.scalar(
            select(Document).where(Document.sha256 == sha256)
        )

        is_verified = False
        chunk_count = 0
        if not pipeline_error and iris_doc and iris_doc.status == "complete":
            chunk_count = session.scalar(
                select(func.count(DocumentChunk.id)).where(DocumentChunk.document_id == iris_doc.id)
            )
            if chunk_count and chunk_count > 0:
                is_verified = True

        if is_verified:
            doc.status = "ingested"
            doc.change_status = "unchanged"
            doc.ingested_document_id = iris_doc.id
            doc.ingested_at = datetime.now(timezone.utc)
            doc.error_message = None

            audit_success = DocumentApprovalAudit(
                document_id=doc.id,
                admin_user_id=admin_id,
                admin_email=admin_user.email,
                action="ingest_completed",
                previous_status="ingesting",
                new_status="ingested",
                reason=f"Successfully ingested into IRIS (Doc ID: {iris_doc.id}, {chunk_count} chunks).",
                created_at=datetime.now(timezone.utc),
            )
            session.add(audit_success)
            logger.info("Document %s successfully ingested into IRIS.", doc.id)
        else:
            doc.status = "ingest_failed"
            err = pipeline_error or "Ingestion verification failed: Document chunks not found in database."
            doc.error_message = err

            audit_fail = DocumentApprovalAudit(
                document_id=doc.id,
                admin_user_id=admin_id,
                admin_email=admin_user.email,
                action="ingest_failed",
                previous_status="ingesting",
                new_status="ingest_failed",
                reason=err,
                created_at=datetime.now(timezone.utc),
            )
            session.add(audit_fail)
            logger.error("Ingestion failed for document %s: %s", doc.id, err)

        session.commit()
        session.refresh(doc)
        return doc
    finally:
        with _ACTIVE_INGESTIONS_LOCK:
            _ACTIVE_INGESTIONS.discard(document_id)
        if owns_session:
            session.close()
