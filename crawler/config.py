"""Configuration definitions and default sources for the PEC Document Crawler."""

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class SourceConfig:
    """Configuration for a curated PEC source webpage."""

    source_id: str
    name: str
    url: str
    category: str
    strategy: str = "generic_link"  # "senate_table" | "generic_link"
    enabled: bool = True
    config: dict[str, Any] = field(default_factory=dict)


@dataclass
class DiscoveredItem:
    """Metadata record for a discovered document candidate (no file download)."""

    title: str
    source_page_url: str
    download_url: str
    category: str
    file_type: str = "pdf"
    publication_date: Optional[str] = None
    meeting_number: Optional[str] = None
    academic_year: Optional[str] = None
    http_etag: Optional[str] = None
    http_last_modified: Optional[str] = None
    http_content_length: Optional[int] = None
    metadata: dict[str, Any] = field(default_factory=dict)


# Default curated PEC source webpages provided by administrative authority
DEFAULT_PEC_SOURCES: list[SourceConfig] = [
    SourceConfig(
        source_id="senate-moms",
        name="PEC Senate Meeting Minutes",
        url="https://pec.ac.in/minutes-senate-meetings",
        category="Governance / Senate",
        strategy="senate_table",
        enabled=True,
    ),
    SourceConfig(
        source_id="ug-structure",
        name="Undergraduate Programmes Structure & Scheme",
        url="https://pec.ac.in/programmes/ug/structure",
        category="Curriculum",
        strategy="generic_link",
        enabled=True,
    ),
    SourceConfig(
        source_id="academic-calendar",
        name="Academic Calendar",
        url="https://pec.ac.in/academics/calendar",
        category="Academic Calendar",
        strategy="generic_link",
        enabled=True,
    ),
    SourceConfig(
        source_id="rules-procedures",
        name="Rules & Procedures Guidelines",
        url="https://pec.ac.in/programmes/rules-procedures",
        category="Rules & Regulations",
        strategy="generic_link",
        enabled=True,
    ),
    SourceConfig(
        source_id="tnp-policy",
        name="Training & Placement (T&P) Policy",
        url="https://pec.ac.in/tnp/policy",
        category="Training & Placement",
        strategy="generic_link",
        enabled=True,
    ),
]
