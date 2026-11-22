"""Database catalog repository for managing crawler sources, discovered documents, and idempotency."""

from datetime import datetime, timezone
import logging
from typing import Optional
import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from crawler.config import DEFAULT_PEC_SOURCES, DiscoveredItem, SourceConfig
from database.models import CrawlerSource, DiscoveredDocument

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
    logger.info("Seeded %d crawler sources into catalog.", len(sources))
    return sources


def get_all_sources(session: Session, enabled_only: bool = False) -> list[CrawlerSource]:
    """Retrieve all configured PEC sources from database."""
    stmt = select(CrawlerSource)
    if enabled_only:
        stmt = stmt.where(CrawlerSource.enabled == True)
    return list(session.scalars(stmt.order_by(CrawlerSource.created_at.asc())).all())


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
    """Idempotently insert or update discovered document records.

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
                metadata_=item.metadata,
                status="discovered",
                first_discovered_at=now,
                last_discovered_at=now,
                last_scanned_at=now,
            )
            session.add(doc)
            new_count += 1

    source = get_source_by_id(session, source_id)
    if source:
        source.last_scanned_at = now

    session.commit()
    logger.info(
        "Catalog sync for %s: %d new, %d updated.",
        source_id,
        new_count,
        updated_count,
    )
    return new_count, updated_count, potentially_changed_count


def list_discovered_documents(
    session: Session,
    source_id: Optional[str] = None,
    status: Optional[str] = None,
    category: Optional[str] = None,
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


def get_catalog_stats(session: Session) -> dict[str, int]:
    """Return counts of discovered documents grouped by status."""
    rows = session.execute(
        select(DiscoveredDocument.status, func.count(DiscoveredDocument.id)).group_by(
            DiscoveredDocument.status
        )
    ).all()
    stats = {status: count for status, count in rows}
    stats["total"] = sum(stats.values())
    return stats
