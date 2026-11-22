"""Administrative endpoints for managing PEC document crawler, catalogue, change detection, and approvals."""

from datetime import datetime, timezone
import logging
import math
from typing import Optional
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.dependencies import get_database_session, require_admin
from api.schemas import (
    CrawlerScanResponse,
    CrawlerScanTriggerRequest,
    CrawlerSourceSchema,
    CrawlerSourceUpdateSchema,
    DiscoveredDocumentListResponse,
    DiscoveredDocumentSchema,
    DocumentAuditSchema,
    DocumentIngestionStatusResponse,
    DocumentRejectionRequest,
)
from crawler.acquisition import acquire_and_ingest_document
from database.models import DiscoveredDocument
from crawler.catalog import (
    approve_document,
    complete_scan_execution,
    get_all_sources,
    get_catalog_stats,
    get_discovered_document_by_id,
    get_document_approval_history,
    get_latest_scan,
    get_scan_by_id,
    get_source_by_id,
    list_discovered_documents_paginated,
    reconsider_document,
    reject_document,
    seed_default_sources,
    start_scan_execution,
    update_source_config,
    upsert_discovered_documents,
)
from crawler.config import SourceConfig
from crawler.engine import PECCrawlerEngine
from database.connection import SessionLocal
from database.models import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/crawler", tags=["Admin Document Crawler"])


def _execute_background_scan(scan_id: uuid.UUID, source_id: Optional[str]) -> None:
    """Worker task executed in FastAPI background thread to run discovery scan.

    Isolates per-source errors: a failure on one source does not abort the others.
    """
    db: Session = SessionLocal()
    try:
        logger.info("Background scan %s started (source_id=%s)", scan_id, source_id)
        if source_id:
            src = get_source_by_id(db, source_id)
            sources_to_scan = [src] if src and src.enabled else []
        else:
            sources_to_scan = get_all_sources(db, enabled_only=True)

        if not sources_to_scan:
            logger.warning("Background scan %s: No enabled sources found to scan.", scan_id)
            complete_scan_execution(
                session=db,
                scan_id=scan_id,
                total_sources=0,
                total_discovered=0,
                new_documents=0,
                updated_documents=0,
                potentially_changed=0,
                error_message="No enabled crawler sources found to scan.",
                status="completed",
            )
            return

        engine = PECCrawlerEngine()
        total_discovered = 0
        new_docs = 0
        updated_docs = 0
        potentially_changed = 0

        successful_sources = []
        failed_sources = []
        per_source_errors: dict[str, str] = {}

        for src in sources_to_scan:
            try:
                cfg = SourceConfig(
                    source_id=src.source_id,
                    name=src.name,
                    url=src.url,
                    category=src.category,
                    strategy=src.strategy,
                    enabled=src.enabled,
                    config=src.config or {},
                )
                items = engine.scan_source(cfg)
                total_discovered += len(items)
                n, u, c = upsert_discovered_documents(db, src.source_id, items)
                new_docs += n
                updated_docs += u
                potentially_changed += c
                successful_sources.append(src.source_id)
                logger.info(
                    "Source '%s' scanned successfully (%d discovered, %d new, %d changed).",
                    src.source_id,
                    len(items),
                    n,
                    c,
                )
            except Exception as src_exc:
                logger.error("Scan failed for source '%s': %s", src.source_id, src_exc, exc_info=True)
                failed_sources.append(src.source_id)
                per_source_errors[src.source_id] = str(src_exc)

        # Determine overall scan outcome
        if len(failed_sources) == len(sources_to_scan):
            # All sources failed
            scan_status = "failed"
            error_details = "; ".join([f"{sid}: {err}" for sid, err in per_source_errors.items()])
            summary_err = f"All {len(sources_to_scan)} source(s) failed: {error_details}"
        elif failed_sources:
            # Partial success: at least one source succeeded
            scan_status = "completed"
            error_details = "; ".join([f"{sid}: {err}" for sid, err in per_source_errors.items()])
            summary_err = (
                f"Partial scan success ({len(successful_sources)}/{len(sources_to_scan)} succeeded). "
                f"Failures: {error_details}"
            )
        else:
            scan_status = "completed"
            summary_err = None

        complete_scan_execution(
            session=db,
            scan_id=scan_id,
            total_sources=len(sources_to_scan),
            total_discovered=total_discovered,
            new_documents=new_docs,
            updated_documents=updated_docs,
            potentially_changed=potentially_changed,
            error_message=summary_err,
            status=scan_status,
        )
        logger.info(
            "Background scan %s finalized with status '%s': %d discovered (%d new, %d updated, %d changed).",
            scan_id,
            scan_status,
            total_discovered,
            new_docs,
            updated_docs,
            potentially_changed,
        )
    except Exception as exc:
        logger.error("Background scan %s encountered fatal error: %s", scan_id, exc, exc_info=True)
        try:
            complete_scan_execution(
                session=db,
                scan_id=scan_id,
                total_sources=0,
                total_discovered=0,
                new_documents=0,
                updated_documents=0,
                potentially_changed=0,
                error_message=f"Fatal scan error: {exc}",
                status="failed",
            )
        except Exception:
            pass
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 1. Sources Management
# ---------------------------------------------------------------------------


@router.get(
    "/sources",
    response_model=list[CrawlerSourceSchema],
    summary="List all configured PEC sources",
)
def list_sources(
    db: Session = Depends(get_database_session),
    admin_user: User = Depends(require_admin),
) -> list[CrawlerSourceSchema]:
    """Retrieve all configured PEC crawler sources, seeding defaults if empty."""
    sources = get_all_sources(db)
    if not sources:
        sources = seed_default_sources(db)
    return sources


@router.patch(
    "/sources/{source_id}",
    response_model=CrawlerSourceSchema,
    summary="Update crawler source configuration",
)
def update_source(
    source_id: str,
    payload: CrawlerSourceUpdateSchema,
    db: Session = Depends(get_database_session),
    admin_user: User = Depends(require_admin),
) -> CrawlerSourceSchema:
    """Enable, disable, or modify properties of a PEC source webpage."""
    updated = update_source_config(
        session=db,
        source_id=source_id,
        enabled=payload.enabled,
        name=payload.name,
        category=payload.category,
        config=payload.config,
    )
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Crawler source '{source_id}' not found.",
        )
    return updated


# ---------------------------------------------------------------------------
# 2. Scan Execution & Status
# ---------------------------------------------------------------------------


@router.post(
    "/scan",
    response_model=CrawlerScanResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger crawler discovery scan",
)
def trigger_scan(
    background_tasks: BackgroundTasks,
    payload: Optional[CrawlerScanTriggerRequest] = None,
    db: Session = Depends(get_database_session),
    admin_user: User = Depends(require_admin),
) -> CrawlerScanResponse:
    """Initiate a discovery scan across enabled sources without downloading PDFs.

    Rejects request with HTTP 409 Conflict if a scan is already running.
    """
    target_source = payload.source_id if payload else None
    if target_source:
        src = get_source_by_id(db, target_source)
        if not src:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Crawler source '{target_source}' not found.",
            )

    try:
        scan = start_scan_execution(
            session=db,
            initiated_by=admin_user.email,
            source_id=target_source,
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )

    # Launch in-process background worker
    background_tasks.add_task(_execute_background_scan, scan.id, target_source)

    return scan


@router.get(
    "/scans/latest",
    response_model=Optional[CrawlerScanResponse],
    summary="Get latest crawler scan execution",
)
def get_latest_scan_status(
    db: Session = Depends(get_database_session),
    admin_user: User = Depends(require_admin),
) -> Optional[CrawlerScanResponse]:
    """Retrieve status and statistics of the most recent discovery scan."""
    return get_latest_scan(db)


@router.get(
    "/scans/{scan_id}",
    response_model=CrawlerScanResponse,
    summary="Get specific crawler scan execution by ID",
)
def get_scan_status_by_id(
    scan_id: uuid.UUID,
    db: Session = Depends(get_database_session),
    admin_user: User = Depends(require_admin),
) -> CrawlerScanResponse:
    """Poll progress or inspect outcome of a specific scan execution."""
    scan = get_scan_by_id(db, scan_id)
    if not scan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scan record not found.",
        )
    return scan


# ---------------------------------------------------------------------------
# 3. Document Catalogue & Filtering
# ---------------------------------------------------------------------------


@router.get(
    "/documents",
    response_model=DiscoveredDocumentListResponse,
    summary="List and filter discovered documents",
)
def list_documents(
    page: int = Query(default=1, ge=1, description="1-based page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page"),
    source_id: Optional[str] = Query(default=None, description="Filter by source_id"),
    status: Optional[str] = Query(default=None, description="Filter by status (e.g. discovered, approved)"),
    category: Optional[str] = Query(default=None, description="Filter by category"),
    change_status: Optional[str] = Query(default=None, description="Filter by change_status (e.g. unchanged, potentially_changed, unknown)"),
    search: Optional[str] = Query(default=None, description="Search term in title or URL"),
    sort_by: Optional[str] = Query(default="document_date", description="Field to sort by: document_date, title, publication_date, status, discovered_at"),
    sort_order: Optional[str] = Query(default="desc", description="Sort order: asc or desc"),
    db: Session = Depends(get_database_session),
    admin_user: User = Depends(require_admin),
) -> DiscoveredDocumentListResponse:
    """Retrieve discovered documents with pagination, filters, sorting, and catalogue totals."""
    total, docs = list_discovered_documents_paginated(
        session=db,
        page=page,
        page_size=page_size,
        source_id=source_id,
        status=status,
        category=category,
        change_status=change_status,
        search=search,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    total_pages = math.ceil(total / page_size) if total > 0 else 0
    stats = get_catalog_stats(db)

    return DiscoveredDocumentListResponse(
        items=docs,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        stats=stats,
    )


@router.get(
    "/documents/{document_id}",
    response_model=DiscoveredDocumentSchema,
    summary="Get discovered document details",
)
def get_document(
    document_id: uuid.UUID,
    db: Session = Depends(get_database_session),
    admin_user: User = Depends(require_admin),
) -> DiscoveredDocumentSchema:
    """Retrieve complete metadata and change detection state for a discovered document."""
    doc = get_discovered_document_by_id(db, document_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Discovered document not found.",
        )
    return doc


@router.get(
    "/stats",
    response_model=dict[str, int],
    summary="Get high-level catalogue statistics",
)
def get_stats(
    db: Session = Depends(get_database_session),
    admin_user: User = Depends(require_admin),
) -> dict[str, int]:
    """Return catalogue document totals grouped by lifecycle status."""
    return get_catalog_stats(db)


# ---------------------------------------------------------------------------
# 4. Approval, Rejection, Reconsideration & Audit History
# ---------------------------------------------------------------------------


@router.post(
    "/documents/{document_id}/approve",
    response_model=DiscoveredDocumentSchema,
    summary="Approve document for acquisition",
)
def approve_document_endpoint(
    document_id: uuid.UUID,
    db: Session = Depends(get_database_session),
    admin_user: User = Depends(require_admin),
) -> DiscoveredDocumentSchema:
    """Approve a discovered document and append an immutable audit record."""
    try:
        doc = approve_document(db, document_id, admin_user)
        return doc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )


@router.post(
    "/documents/{document_id}/reject",
    response_model=DiscoveredDocumentSchema,
    summary="Reject document",
)
def reject_document_endpoint(
    document_id: uuid.UUID,
    payload: Optional[DocumentRejectionRequest] = None,
    db: Session = Depends(get_database_session),
    admin_user: User = Depends(require_admin),
) -> DiscoveredDocumentSchema:
    """Reject a discovered document with an optional reason and append an audit record."""
    reason = payload.reason if payload else None
    try:
        doc = reject_document(db, document_id, admin_user, reason=reason)
        return doc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )


@router.post(
    "/documents/{document_id}/reconsider",
    response_model=DiscoveredDocumentSchema,
    summary="Reconsider rejected document",
)
def reconsider_document_endpoint(
    document_id: uuid.UUID,
    db: Session = Depends(get_database_session),
    admin_user: User = Depends(require_admin),
) -> DiscoveredDocumentSchema:
    """Reset a rejected document back to discovered for review."""
    try:
        doc = reconsider_document(db, document_id, admin_user)
        return doc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )


@router.get(
    "/documents/{document_id}/history",
    response_model=list[DocumentAuditSchema],
    summary="Get document approval audit history",
)
def get_approval_history(
    document_id: uuid.UUID,
    db: Session = Depends(get_database_session),
    admin_user: User = Depends(require_admin),
) -> list[DocumentAuditSchema]:
    """Retrieve immutable chronological audit records for a document."""
    doc = get_discovered_document_by_id(db, document_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Discovered document not found.",
        )
    return get_document_approval_history(db, document_id)


# ---------------------------------------------------------------------------
# 5. Approved Document Ingestion & Acquisition (Phase 3)
# ---------------------------------------------------------------------------


@router.post(
    "/documents/{document_id}/ingest",
    response_model=DiscoveredDocumentSchema,
    summary="Initiate download and ingestion of an approved document",
)
def ingest_document_endpoint(
    document_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_database_session),
    admin_user: User = Depends(require_admin),
) -> DiscoveredDocumentSchema:
    """Download approved PDF, validate integrity, and trigger the IRIS ingestion pipeline."""
    # Row-level lock to prevent concurrent initiation on the same record
    doc = db.scalar(
        select(DiscoveredDocument)
        .where(DiscoveredDocument.id == document_id)
        .with_for_update()
    )
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Discovered document with ID '{document_id}' not found.",
        )
    if doc.status == "ingested":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Document '{doc.title}' is already ingested.",
        )
    if doc.status == "rejected":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Document '{doc.title}' is rejected and cannot be ingested. "
                "Only approved documents (or failed retries) can be ingested."
            ),
        )
    if doc.status in ("downloading", "ingesting"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Acquisition for document '{doc.title}' is already in progress (status: {doc.status}).",
        )
    if doc.status not in ("approved", "download_failed", "ingest_failed"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Document '{doc.title}' cannot be ingested because its status is '{doc.status}'. "
                "Only approved documents (or failed retries) can be ingested."
            ),
        )

    # Launch acquisition & ingestion in background task (synchronous under TestClient)
    background_tasks.add_task(acquire_and_ingest_document, document_id, admin_user)

    doc.status = "downloading"
    db.commit()
    db.refresh(doc)
    return doc


@router.post(
    "/documents/{document_id}/retry",
    response_model=DiscoveredDocumentSchema,
    summary="Retry failed download or ingestion",
)
def retry_document_endpoint(
    document_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_database_session),
    admin_user: User = Depends(require_admin),
) -> DiscoveredDocumentSchema:
    """Retry a failed document download or ingestion operation."""
    # Row-level lock to prevent concurrent retry requests on the same record
    doc = db.scalar(
        select(DiscoveredDocument)
        .where(DiscoveredDocument.id == document_id)
        .with_for_update()
    )
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Discovered document with ID '{document_id}' not found.",
        )
    if doc.status in ("downloading", "ingesting"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Acquisition for document '{doc.title}' is already in progress (status: {doc.status}).",
        )
    if doc.status not in ("download_failed", "ingest_failed"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Document with status '{doc.status}' is not in a failed state and cannot be retried.",
        )

    background_tasks.add_task(acquire_and_ingest_document, document_id, admin_user)

    doc.status = "downloading"
    doc.error_message = None
    db.commit()
    db.refresh(doc)
    return doc


@router.get(
    "/documents/{document_id}/ingestion-status",
    response_model=DocumentIngestionStatusResponse,
    summary="Get document acquisition and ingestion status",
)
def get_document_ingestion_status(
    document_id: uuid.UUID,
    db: Session = Depends(get_database_session),
    admin_user: User = Depends(require_admin),
) -> DocumentIngestionStatusResponse:
    """Inspect real-time download and ingestion status and error diagnostics."""
    doc = get_discovered_document_by_id(db, document_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Discovered document with ID '{document_id}' not found.",
        )
    return doc

