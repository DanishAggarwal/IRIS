"""Database catalog repository for managing crawler sources, discovered documents, change detection, and approvals."""

from datetime import datetime, timedelta, timezone
import logging
from typing import Optional
import uuid

from sqlalchemy import case, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from crawler.config import DEFAULT_PEC_SOURCES, DiscoveredItem, SourceConfig
from database.connection import SessionLocal
from database.models import (
    CrawlerScan,
    CrawlerSource,
    DiscoveredDocument,
    DocumentApprovalAudit,
    User,
)

logger = logging.getLogger(__name__)


def seed_default_sources(session: Session) -> list[CrawlerSource]:
    """Ensure default curated PEC sources exist in the database."""
    sources: list[CrawlerSource] = []
    for default_src in DEFAULT_PEC_SOURCES:
        existing = session.scalar(
            select(CrawlerSource).where(CrawlerSource.source_id == default_src.source_id)
        )
        if not existing:
            new_src = CrawlerSource(
                source_id=default_src.source_id,
                name=default_src.name,
                url=default_src.url,
                category=default_src.category,
                strategy=default_src.strategy,
                enabled=default_src.enabled,
                config=default_src.config,
            )
            session.add(new_src)
            sources.append(new_src)
        else:
            sources.append(existing)

    session.commit()
    return sources


def get_all_sources(session: Session, enabled_only: bool = False) -> list[CrawlerSource]:
    """Retrieve all configured sources from database."""
    stmt = select(CrawlerSource)
    if enabled_only:
        stmt = stmt.where(CrawlerSource.enabled == True)  # noqa: E712
    return list(session.scalars(stmt.order_by(CrawlerSource.name.asc())).all())


def get_source_by_id(session: Session, source_id: str) -> Optional[CrawlerSource]:
    """Fetch single source by source_id slug."""
    return session.scalar(
        select(CrawlerSource).where(CrawlerSource.source_id == source_id)
    )


def update_source_config(
    session: Session,
    source_id: str,
    enabled: Optional[bool] = None,
    name: Optional[str] = None,
    category: Optional[str] = None,
    config: Optional[dict] = None,
) -> Optional[CrawlerSource]:
    """Update configuration properties for an institutional source."""
    source = get_source_by_id(session, source_id)
    if not source:
        return None

    if enabled is not None:
        source.enabled = enabled
    if name is not None:
        source.name = name
    if category is not None:
        source.category = category
    if config is not None:
        source.config = config

    session.commit()
    session.refresh(source)
    return source


def get_discovered_document_by_id(
    session: Session, document_id: uuid.UUID
) -> Optional[DiscoveredDocument]:
    """Fetch single discovered document by primary key."""
    return session.get(DiscoveredDocument, document_id)


def upsert_discovered_documents(
    session: Session,
    source_id: str,
    items: list[DiscoveredItem],
    scan_time: Optional[datetime] = None,
) -> tuple[int, int, int]:
    """Idempotently insert or update discovered document records with change detection.

    Returns:
        (new_count, updated_count, potentially_changed_count)
    """
    now = scan_time or datetime.now(timezone.utc)
    new_count = 0
    updated_count = 0
    potentially_changed_count = 0

    for item in items:
        existing = session.scalar(
            select(DiscoveredDocument).where(
                DiscoveredDocument.source_id == source_id,
                DiscoveredDocument.download_url == item.download_url,
            )
        )

        if existing:
            # Update timestamps and descriptive metadata without wiping human decisions
            existing.last_discovered_at = now
            existing.last_scanned_at = now
            if item.title and existing.title != item.title:
                existing.title = item.title
            if item.publication_date and not existing.publication_date:
                existing.publication_date = item.publication_date
            if item.meeting_number and not existing.meeting_number:
                existing.meeting_number = item.meeting_number
            if item.academic_year and not existing.academic_year:
                existing.academic_year = item.academic_year
            if item.metadata:
                existing.metadata_ = {**(existing.metadata_ or {}), **item.metadata}

            # Change detection using HTTP metadata
            if item.http_etag or item.http_last_modified or item.http_content_length:
                existing.last_checked_at = now
                etag_changed = bool(
                    existing.http_etag and item.http_etag and existing.http_etag != item.http_etag
                )
                mod_changed = bool(
                    existing.http_last_modified
                    and item.http_last_modified
                    and existing.http_last_modified != item.http_last_modified
                )
                len_changed = bool(
                    existing.http_content_length
                    and item.http_content_length
                    and existing.http_content_length != item.http_content_length
                )

                if etag_changed or mod_changed or len_changed:
                    existing.change_status = "potentially_changed"
                    potentially_changed_count += 1
                    # Do NOT overwrite existing.status (e.g. 'ingested', 'approved', 'rejected').
                    # Preserves human approval decisions and ingestion provenance.
                else:
                    if existing.change_status == "unknown":
                        existing.change_status = "unchanged"

                # Store newest HTTP metadata
                if item.http_etag:
                    existing.http_etag = item.http_etag
                if item.http_last_modified:
                    existing.http_last_modified = item.http_last_modified
                if item.http_content_length:
                    existing.http_content_length = item.http_content_length

            updated_count += 1
        else:
            doc = DiscoveredDocument(
                source_id=source_id,
                title=item.title,
                source_page_url=item.source_page_url,
                download_url=item.download_url,
                category=item.category,
                file_type=item.file_type,
                publication_date=item.publication_date,
                meeting_number=item.meeting_number,
                academic_year=item.academic_year,
                http_etag=item.http_etag,
                http_last_modified=item.http_last_modified,
                http_content_length=item.http_content_length,
                last_checked_at=now if (item.http_etag or item.http_last_modified) else None,
                change_status="unchanged" if (item.http_etag or item.http_last_modified) else "unknown",
                metadata_=item.metadata,
                status="discovered",
                first_discovered_at=now,
                last_discovered_at=now,
                last_scanned_at=now,
            )
            session.add(doc)
            new_count += 1

    # Update source's last_scanned_at
    source = get_source_by_id(session, source_id)
    if source:
        source.last_scanned_at = now

    session.commit()
    logger.info(
        "Catalog sync for %s: %d new, %d updated, %d potentially changed.",
        source_id,
        new_count,
        updated_count,
        potentially_changed_count,
    )
    return new_count, updated_count, potentially_changed_count


# ---------------------------------------------------------------------------
# Approval Workflow & Immutable Audit Trail
# ---------------------------------------------------------------------------


def approve_document(
    session: Session,
    document_id: uuid.UUID,
    admin_user: User,
) -> DiscoveredDocument:
    """Approve a discovered document for future acquisition and ingestion.

    Appends an immutable audit record and transitions status to 'approved'.
    """
    doc = session.get(DiscoveredDocument, document_id)
    if not doc:
        raise ValueError(f"Document with ID {document_id} not found.")

    if doc.status == "approved":
        return doc  # Idempotent no-op

    prev_status = doc.status
    now = datetime.now(timezone.utc)

    doc.status = "approved"
    doc.approved_by = admin_user.email
    doc.approved_at = now
    doc.rejection_reason = None

    user_in_db = session.get(User, admin_user.id) if admin_user and getattr(admin_user, "id", None) else None
    valid_admin_id = user_in_db.id if user_in_db else None

    audit = DocumentApprovalAudit(
        document_id=doc.id,
        admin_user_id=valid_admin_id,
        admin_email=admin_user.email,
        action="approve",
        previous_status=prev_status,
        new_status="approved",
        reason=None,
        created_at=now,
    )
    session.add(audit)
    session.commit()
    session.refresh(doc)
    logger.info("Admin %s approved document %s ('%s')", admin_user.email, doc.id, doc.title)
    return doc


def reject_document(
    session: Session,
    document_id: uuid.UUID,
    admin_user: User,
    reason: Optional[str] = None,
) -> DiscoveredDocument:
    """Reject a discovered document from being ingested into IRIS.

    Appends an immutable audit record and stores the optional rejection reason.
    """
    doc = session.get(DiscoveredDocument, document_id)
    if not doc:
        raise ValueError(f"Document with ID {document_id} not found.")

    prev_status = doc.status
    now = datetime.now(timezone.utc)

    doc.status = "rejected"
    doc.rejection_reason = reason
    doc.approved_by = None
    doc.approved_at = None

    user_in_db = session.get(User, admin_user.id) if admin_user and getattr(admin_user, "id", None) else None
    valid_admin_id = user_in_db.id if user_in_db else None

    audit = DocumentApprovalAudit(
        document_id=doc.id,
        admin_user_id=valid_admin_id,
        admin_email=admin_user.email,
        action="reject",
        previous_status=prev_status,
        new_status="rejected",
        reason=reason,
        created_at=now,
    )
    session.add(audit)
    session.commit()
    session.refresh(doc)
    logger.info("Admin %s rejected document %s ('%s'): %s", admin_user.email, doc.id, doc.title, reason)
    return doc


def reconsider_document(
    session: Session,
    document_id: uuid.UUID,
    admin_user: User,
) -> DiscoveredDocument:
    """Reset a previously rejected document back to 'discovered' for review."""
    doc = session.get(DiscoveredDocument, document_id)
    if not doc:
        raise ValueError(f"Document with ID {document_id} not found.")

    if doc.status != "rejected" and doc.change_status != "potentially_changed":
        raise ValueError(
            f"Document with status '{doc.status}' and change_status '{doc.change_status}' cannot be reconsidered."
        )

    prev_status = doc.status
    now = datetime.now(timezone.utc)

    doc.status = "discovered"
    doc.rejection_reason = None
    doc.approved_by = None
    doc.approved_at = None

    user_in_db = session.get(User, admin_user.id) if admin_user and getattr(admin_user, "id", None) else None
    valid_admin_id = user_in_db.id if user_in_db else None

    audit = DocumentApprovalAudit(
        document_id=doc.id,
        admin_user_id=valid_admin_id,
        admin_email=admin_user.email,
        action="reconsider",
        previous_status=prev_status,
        new_status="discovered",
        reason="Reconsidered by administrator.",
        created_at=now,
    )
    session.add(audit)
    session.commit()
    session.refresh(doc)
    logger.info("Admin %s reconsidered document %s ('%s')", admin_user.email, doc.id, doc.title)
    return doc


def get_document_approval_history(
    session: Session, document_id: uuid.UUID
) -> list[DocumentApprovalAudit]:
    """Retrieve chronological approval audit history for a document."""
    stmt = (
        select(DocumentApprovalAudit)
        .where(DocumentApprovalAudit.document_id == document_id)
        .order_by(DocumentApprovalAudit.created_at.desc())
    )
    return list(session.scalars(stmt).all())


# ---------------------------------------------------------------------------
# Scan Execution Management & Concurrency Guard
# ---------------------------------------------------------------------------

STALE_SCAN_THRESHOLD_SECONDS = 1800  # 30 minutes


def recover_stale_scans_on_startup(session: Session) -> int:
    """Identify and fail any scan records left in 'running' status from a previous process.

    Safe to run on FastAPI startup. Does not touch completed or failed scans.
    """
    now = datetime.now(timezone.utc)
    stale_scans = list(
        session.scalars(
            select(CrawlerScan).where(CrawlerScan.status == "running")
        ).all()
    )
    if not stale_scans:
        return 0

    for scan in stale_scans:
        scan.status = "failed"
        scan.error_message = "Scan interrupted by application restart."
        scan.completed_at = now

    session.commit()
    logger.info("Recovered %d stale/orphaned running scans on startup.", len(stale_scans))
    return len(stale_scans)


def start_scan_execution(
    session: Session,
    initiated_by: str,
    source_id: Optional[str] = None,
) -> CrawlerScan:
    """Register a new scan execution.

    Enforces concurrency lock:
    1. Recovers any stale scans exceeding timeout threshold.
    2. Python check-and-raise for active running scans.
    3. Database partial unique index on status='running' prevents race-condition collisions.
    """
    now = datetime.now(timezone.utc)

    # 1. Recover any stale scans running longer than threshold
    stale_cutoff = now - timedelta(seconds=STALE_SCAN_THRESHOLD_SECONDS)
    stale_scans = list(
        session.scalars(
            select(CrawlerScan).where(
                CrawlerScan.status == "running",
                CrawlerScan.started_at <= stale_cutoff,
            )
        ).all()
    )
    for stale in stale_scans:
        stale.status = "failed"
        stale.error_message = (
            f"Scan exceeded timeout threshold of {STALE_SCAN_THRESHOLD_SECONDS}s (stale scan recovered)."
        )
        stale.completed_at = now
    if stale_scans:
        session.commit()
        logger.warning("Recovered %d timed-out running scan(s).", len(stale_scans))

    # 2. Check for active running scan
    running_scan = session.scalar(
        select(CrawlerScan).where(CrawlerScan.status == "running")
    )
    if running_scan:
        raise RuntimeError(
            f"A discovery scan is already in progress (started at {running_scan.started_at.isoformat()})."
        )

    scan = CrawlerScan(
        source_id=source_id,
        status="running",
        initiated_by=initiated_by,
        started_at=now,
    )
    session.add(scan)
    try:
        session.commit()
        session.refresh(scan)
        return scan
    except IntegrityError:
        session.rollback()
        raise RuntimeError(
            "A discovery scan is already in progress (enforced by concurrency lock)."
        )


def complete_scan_execution(
    session: Session,
    scan_id: uuid.UUID,
    total_sources: int,
    total_discovered: int,
    new_documents: int,
    updated_documents: int,
    potentially_changed: int,
    error_message: Optional[str] = None,
    status: Optional[str] = None,
) -> CrawlerScan:
    """Finalize a scan execution with outcome statistics and optional status override."""
    scan = session.get(CrawlerScan, scan_id)
    if not scan:
        raise ValueError(f"Scan {scan_id} not found.")

    scan.total_sources = total_sources
    scan.total_discovered = total_discovered
    scan.new_documents = new_documents
    scan.updated_documents = updated_documents
    scan.potentially_changed = potentially_changed
    scan.error_message = error_message
    if status:
        scan.status = status
    else:
        scan.status = "failed" if error_message else "completed"
    scan.completed_at = datetime.now(timezone.utc)

    session.commit()
    session.refresh(scan)
    return scan


def get_latest_scan(session: Session) -> Optional[CrawlerScan]:
    """Retrieve the most recent crawler scan execution record."""
    stmt = select(CrawlerScan).order_by(CrawlerScan.started_at.desc()).limit(1)
    return session.scalar(stmt)


def get_scan_by_id(session: Session, scan_id: uuid.UUID) -> Optional[CrawlerScan]:
    """Retrieve specific scan record by UUID."""
    return session.get(CrawlerScan, scan_id)


# ---------------------------------------------------------------------------
# Catalog Queries & Filtering
# ---------------------------------------------------------------------------


def get_catalog_stats(session: Session) -> dict[str, int]:
    """Return counts of discovered documents grouped by status and change signal."""
    rows = session.execute(
        select(DiscoveredDocument.status, func.count(DiscoveredDocument.id)).group_by(
            DiscoveredDocument.status
        )
    ).all()
    stats = {status: count for status, count in rows}
    stats["total"] = sum(stats.values())

    # Count potentially changed
    changed_cnt = session.scalar(
        select(func.count(DiscoveredDocument.id)).where(
            DiscoveredDocument.change_status == "potentially_changed"
        )
    )
    stats["potentially_changed"] = changed_cnt or 0
    return stats


def list_discovered_documents_paginated(
    session: Session,
    page: int = 1,
    page_size: int = 20,
    source_id: Optional[str] = None,
    status: Optional[str] = None,
    category: Optional[str] = None,
    change_status: Optional[str] = None,
    search: Optional[str] = None,
    sort_by: Optional[str] = "document_date",
    sort_order: Optional[str] = "desc",
) -> tuple[int, list[DiscoveredDocument]]:
    """Query discovered document catalog with pagination, multi-attribute filtering, and dynamic sorting.

    Returns:
        (total_matching_count, list_of_documents)
    """
    stmt = select(DiscoveredDocument)
    count_stmt = select(func.count(DiscoveredDocument.id))

    if source_id:
        stmt = stmt.where(DiscoveredDocument.source_id == source_id)
        count_stmt = count_stmt.where(DiscoveredDocument.source_id == source_id)
    if status:
        stmt = stmt.where(DiscoveredDocument.status == status)
        count_stmt = count_stmt.where(DiscoveredDocument.status == status)
    if category:
        stmt = stmt.where(DiscoveredDocument.category == category)
        count_stmt = count_stmt.where(DiscoveredDocument.category == category)
    if change_status:
        stmt = stmt.where(DiscoveredDocument.change_status == change_status)
        count_stmt = count_stmt.where(DiscoveredDocument.change_status == change_status)
    if search and search.strip():
        term = f"%{search.strip().lower()}%"
        search_filter = or_(
            func.lower(DiscoveredDocument.title).like(term),
            func.lower(DiscoveredDocument.download_url).like(term),
        )
        stmt = stmt.where(search_filter)
        count_stmt = count_stmt.where(search_filter)

    total_count = session.scalar(count_stmt) or 0
    offset = max(0, (page - 1) * page_size)

    # Normalized effective document date expression:
    # Converts DD.MM.YYYY strings (e.g. '18.01.2023') into sortable 'YYYY-MM-DD',
    # falling back to academic_year (e.g. '2026-07', '2024') or NULL.
    effective_doc_date = case(
        (
            func.length(DiscoveredDocument.publication_date) == 10,
            func.substr(DiscoveredDocument.publication_date, 7, 4)
            + "-"
            + func.substr(DiscoveredDocument.publication_date, 4, 2)
            + "-"
            + func.substr(DiscoveredDocument.publication_date, 1, 2),
        ),
        (
            DiscoveredDocument.publication_date.isnot(None),
            DiscoveredDocument.publication_date,
        ),
        (
            DiscoveredDocument.academic_year.isnot(None),
            DiscoveredDocument.academic_year,
        ),
        else_=None,
    )

    # Determine sort column
    sort_col_map = {
        "document_date": effective_doc_date,
        "date": effective_doc_date,
        "publication_date": effective_doc_date,
        "title": func.lower(DiscoveredDocument.title),
        "status": DiscoveredDocument.status,
        "first_discovered_at": DiscoveredDocument.first_discovered_at,
        "discovered_at": DiscoveredDocument.last_discovered_at,
        "last_discovered_at": DiscoveredDocument.last_discovered_at,
    }
    target_col = sort_col_map.get(sort_by or "document_date", effective_doc_date)
    is_desc = (sort_order or "desc").strip().lower() == "desc"
    order_expr = target_col.desc().nulls_last() if is_desc else target_col.asc().nulls_last()

    docs = list(
        session.scalars(
            stmt.order_by(order_expr, DiscoveredDocument.title.asc(), DiscoveredDocument.id.asc())
            .limit(page_size)
            .offset(offset)
        ).all()
    )

    return total_count, docs


def list_discovered_documents(
    session: Session,
    source_id: Optional[str] = None,
    status: Optional[str] = None,
    category: Optional[str] = None,
    change_status: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> list[DiscoveredDocument]:
    """Retrieve discovered documents as a flat list."""
    stmt = select(DiscoveredDocument)
    if source_id:
        stmt = stmt.where(DiscoveredDocument.source_id == source_id)
    if status:
        stmt = stmt.where(DiscoveredDocument.status == status)
    if category:
        stmt = stmt.where(DiscoveredDocument.category == category)
    if change_status:
        stmt = stmt.where(DiscoveredDocument.change_status == change_status)
    if search and search.strip():
        term = f"%{search.strip().lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(DiscoveredDocument.title).like(term),
                func.lower(DiscoveredDocument.download_url).like(term),
            )
        )
    return list(
        session.scalars(
            stmt.order_by(DiscoveredDocument.last_discovered_at.desc())
            .limit(limit)
            .offset(offset)
        ).all()
    )
