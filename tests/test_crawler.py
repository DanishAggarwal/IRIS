"""Unit and integration tests for Phase 1 PEC Document Crawler & Discovery Subsystem."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
import uuid
from bs4 import BeautifulSoup
import httpx
import pytest

from crawler.catalog import (
    get_all_sources,
    get_catalog_stats,
    get_source_by_id,
    list_discovered_documents,
    seed_default_sources,
    upsert_discovered_documents,
)
from crawler.config import DiscoveredItem, SourceConfig
from crawler.engine import is_pec_domain, normalize_url, PECCrawlerEngine
from crawler.strategies import get_strategy
from crawler.strategies.generic import GenericLinkStrategy
from crawler.strategies.senate import SenateTableStrategy
from database.connection import SessionLocal
from database.models import CrawlerSource, DiscoveredDocument


# ---------------------------------------------------------------------------
# 1. Security & Domain Boundary Tests
# ---------------------------------------------------------------------------


def test_is_pec_domain_validation():
    """Verify strict PEC domain allowlist enforcement."""
    # Valid PEC origins
    assert is_pec_domain("https://pec.ac.in") is True
    assert is_pec_domain("https://pec.ac.in/minutes-senate-meetings") is True
    assert is_pec_domain("https://subdomain.pec.ac.in/sites/default/files/doc.pdf") is True
    assert is_pec_domain("http://alumni.pec.ac.in/event") is True

    # Host spoofing / boundary escapes
    assert is_pec_domain("https://pec.ac.in.attacker.com") is False
    assert is_pec_domain("https://attacker.com/pec.ac.in") is False
    assert is_pec_domain("https://notpec.ac.in") is False
    assert is_pec_domain("https://google.com") is False
    assert is_pec_domain("ftp://pec.ac.in") is True  # hostname matches
    assert is_pec_domain("invalid-url") is False
    assert is_pec_domain("") is False


def test_normalize_url():
    """Verify URL normalization strips fragments and whitespace."""
    assert normalize_url("https://pec.ac.in/page#heading") == "https://pec.ac.in/page"
    assert normalize_url("  https://pec.ac.in/page?id=123#frag  ") == "https://pec.ac.in/page?id=123"


# ---------------------------------------------------------------------------
# 2. Strategy Parsing Tests
# ---------------------------------------------------------------------------


def test_senate_table_strategy_extraction():
    """Verify SenateTableStrategy extracts meeting rows and document links."""
    html = """
    <html>
      <body>
        <table>
          <tr>
            <th>Sr. No.</th>
            <th>Date of Meeting</th>
            <th>Description</th>
          </tr>
          <tr>
            <td>109</td>
            <td>14.05.2025</td>
            <td>Minutes of 109th Meeting of Senate held on 14.05.2025 <a href="/sites/files/senate_109.pdf">Download Minutes</a></td>
          </tr>
          <tr>
            <td>108</td>
            <td>10.01.2025</td>
            <td>Minutes of 108th Meeting of Senate held on 10.01.2025 <a href="https://pec.ac.in/sites/files/senate_108.pdf">PDF</a></td>
          </tr>
          <tr>
            <td>1</td>
            <td>01.01.2024</td>
            <td>General Public Notice <a href="/file.pdf">Notice</a></td>
          </tr>
        </table>
      </body>
    </html>
    """
    soup = BeautifulSoup(html, "html.parser")
    src = SourceConfig(
        source_id="senate-moms",
        name="Senate",
        url="https://pec.ac.in/minutes-senate-meetings",
        category="Governance / Senate",
        strategy="senate_table",
    )

    strategy = SenateTableStrategy()
    items = strategy.extract_documents(soup, src.url, src)

    assert len(items) == 2
    item1 = items[0]
    assert item1.meeting_number == "109"
    assert item1.publication_date == "14.05.2025"
    assert item1.download_url == "https://pec.ac.in/sites/files/senate_109.pdf"
    assert "Senate Meeting 109" in item1.title

    item2 = items[1]
    assert item2.meeting_number == "108"
    assert item2.download_url == "https://pec.ac.in/sites/files/senate_108.pdf"


def test_generic_link_strategy_extraction():
    """Verify GenericLinkStrategy extracts document links and ignores web media."""
    html = """
    <html>
      <body>
        <div>
          <h2>Academic Schedules</h2>
          <a href="/sites/default/files/Academic_Calendar_2025-26.pdf">Academic Calendar 2025-26</a>
          <a href="/photo.jpg">Campus Image</a>
          <a href="/script.js">Script</a>
          <a href="https://pec.ac.in/programmes/ug/structure/curriculum_2024.pdf">UG Curriculum 2024 Scheme</a>
        </div>
      </body>
    </html>
    """
    soup = BeautifulSoup(html, "html.parser")
    src = SourceConfig(
        source_id="academic-calendar",
        name="Calendar",
        url="https://pec.ac.in/academics/calendar",
        category="Academic Calendar",
        strategy="generic_link",
    )

    strategy = GenericLinkStrategy()
    items = strategy.extract_documents(soup, src.url, src)

    assert len(items) == 2
    urls = [it.download_url for it in items]
    assert "https://pec.ac.in/sites/default/files/Academic_Calendar_2025-26.pdf" in urls
    assert "https://pec.ac.in/programmes/ug/structure/curriculum_2024.pdf" in urls

    cal_item = next(it for it in items if "Calendar" in it.title)
    assert cal_item.academic_year == "2025-26"
    assert cal_item.category == "Academic Calendar"


def test_generic_link_strategy_keyword_filtering():
    """Verify include_keywords and exclude_keywords configurations work."""
    html = """
    <html>
      <body>
        <a href="/doc1.pdf">B.Tech Placement Policy 2024</a>
        <a href="/doc2.pdf">Hostel Mess Menu 2024</a>
        <a href="/doc3.pdf">M.Tech Placement Policy 2024 (Draft)</a>
      </body>
    </html>
    """
    soup = BeautifulSoup(html, "html.parser")
    src = SourceConfig(
        source_id="filtered-src",
        name="Filtered",
        url="https://pec.ac.in/test",
        category="Test",
        strategy="generic_link",
        config={
            "include_keywords": ["placement"],
            "exclude_keywords": ["draft"],
        },
    )

    strategy = GenericLinkStrategy()
    items = strategy.extract_documents(soup, src.url, src)

    assert len(items) == 1
    assert items[0].download_url == "https://pec.ac.in/doc1.pdf"


# ---------------------------------------------------------------------------
# 3. Engine & Mocked Crawler Tests
# ---------------------------------------------------------------------------


def test_engine_skips_disabled_and_external_sources():
    """Engine must immediately skip disabled sources and external URLs."""
    disabled_src = SourceConfig(
        source_id="test-disabled",
        name="Disabled",
        url="https://pec.ac.in/test",
        category="Test",
        enabled=False,
    )
    external_src = SourceConfig(
        source_id="test-external",
        name="External",
        url="https://external-university.edu/test",
        category="Test",
        enabled=True,
    )

    mock_client = MagicMock()
    engine = PECCrawlerEngine(client=mock_client)

    assert engine.scan_source(disabled_src) == []
    assert engine.scan_source(external_src) == []
    mock_client.get.assert_not_called()


def test_engine_discards_external_discovered_links():
    """Engine must discard any discovered link pointing outside pec.ac.in."""
    html = """
    <html>
      <body>
        <a href="https://external-site.com/malicious.pdf">External PDF</a>
        <a href="https://pec.ac.in/legit.pdf">Legitimate PEC PDF</a>
      </body>
    </html>
    """
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.headers = {"Content-Type": "text/html"}
    mock_resp.text = html

    mock_client = MagicMock()
    mock_client.get.return_value = mock_resp

    engine = PECCrawlerEngine(client=mock_client)
    src = SourceConfig(
        source_id="test-src",
        name="Test",
        url="https://pec.ac.in/test",
        category="Test",
        strategy="generic_link",
    )

    discovered = engine.scan_source(src)
    assert len(discovered) == 1
    assert discovered[0].download_url == "https://pec.ac.in/legit.pdf"


# ---------------------------------------------------------------------------
# 4. Database Catalog & Idempotency Tests
# ---------------------------------------------------------------------------


def test_catalog_seed_and_idempotent_upsert():
    """Verify seeding default sources and idempotent document discovery upsert."""
    session = SessionLocal()
    try:
        # 1. Seed sources
        sources = seed_default_sources(session)
        assert len(sources) >= 5
        src_ids = [s.source_id for s in sources]
        assert "senate-moms" in src_ids
        assert "tnp-policy" in src_ids

        # 2. Upsert mock discovered documents
        mock_items = [
            DiscoveredItem(
                title="Mock Placement Policy 2026",
                source_page_url="https://pec.ac.in/tnp/policy",
                download_url="https://pec.ac.in/sites/files/mock_policy.pdf",
                category="Training & Placement",
                file_type="pdf",
                academic_year="2026-27",
            ),
            DiscoveredItem(
                title="Mock Calendar 2026",
                source_page_url="https://pec.ac.in/academics/calendar",
                download_url="https://pec.ac.in/sites/files/mock_cal.pdf",
                category="Academic Calendar",
                file_type="pdf",
            ),
        ]

        # First scan: 2 new entries
        new_cnt, upd_cnt, chg_cnt = upsert_discovered_documents(session, "tnp-policy", mock_items)
        assert new_cnt == 2
        assert upd_cnt == 0

        # Query catalog
        docs = list_discovered_documents(session, source_id="tnp-policy")
        doc_urls = [d.download_url for d in docs]
        assert "https://pec.ac.in/sites/files/mock_policy.pdf" in doc_urls
        assert "https://pec.ac.in/sites/files/mock_cal.pdf" in doc_urls

        # Second scan with same items: 0 new, 2 updated (idempotent)
        new_cnt2, upd_cnt2, chg_cnt2 = upsert_discovered_documents(session, "tnp-policy", mock_items)
        assert new_cnt2 == 0
        assert upd_cnt2 == 2

        # Check stats
        stats = get_catalog_stats(session)
        assert stats["total"] >= 2
        assert stats.get("discovered", 0) >= 2

    finally:
        # Cleanup mock entries
        session.query(DiscoveredDocument).filter(
            DiscoveredDocument.download_url.like("%mock_%")
        ).delete(synchronize_session=False)
        session.commit()
        session.close()
