"""Strategy for extracting Senate Meeting Minutes from structured tables."""

import re
from typing import Any, Optional
from urllib.parse import unquote, urldefrag, urljoin, urlparse
from bs4 import BeautifulSoup

from crawler.config import DiscoveredItem, SourceConfig
from crawler.strategies.base import BaseExtractionStrategy

DOCUMENT_EXTENSIONS = {
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".odt", ".ods", ".odp", ".rtf", ".txt", ".csv",
}

RELEVANT_TERMS = re.compile(
    r"\b(senate|minutes?|mom|meeting|agenda|proceedings|annexure|"
    r"annex|attachment|record|resolution)\b",
    re.I,
)


def normalize_url(url: str) -> str:
    """Remove fragments; retain query strings."""
    return urldefrag(url.strip())[0]


def clean_title(value: str) -> str:
    """Normalize and clean document title for human readability."""
    value = unquote(value).replace("_", " ")
    value = re.sub(r"\s+", " ", value).strip()
    return value[:200] or "Senate Document"


class SenateTableStrategy(BaseExtractionStrategy):
    """Parses PEC Senate meeting archives that organize meetings in HTML tables."""

    def extract_documents(
        self,
        soup: BeautifulSoup,
        page_url: str,
        source_config: SourceConfig,
        client: Optional[Any] = None,
    ) -> list[DiscoveredItem]:
        items: list[DiscoveredItem] = []
        seen_urls: set[str] = set()

        for table in soup.find_all("table"):
            header_text = " ".join(
                cell.get_text(" ", strip=True).lower()
                for cell in table.find_all(["th", "td"])[:12]
            )
            if "date of meeting" not in header_text or "description" not in header_text:
                continue

            for row in table.find_all("tr"):
                cells = row.find_all(["td", "th"], recursive=False)
                if len(cells) < 3 or row.find("th"):
                    continue

                description = cells[2].get_text(" ", strip=True)
                row_text = row.get_text(" ", strip=True)
                if not re.search(r"\bsenate\b", description + " " + row_text, re.I):
                    continue

                serial = cells[0].get_text(" ", strip=True)
                number_match = re.search(r"\d+", serial)
                meeting_number = number_match.group(0) if number_match else None
                meeting_date = cells[1].get_text(" ", strip=True)

                # Collect links in this meeting row
                for anchor in row.find_all("a", href=True):
                    raw_href = anchor["href"].strip()
                    if not raw_href or raw_href.startswith(("#", "javascript:", "mailto:")):
                        continue

                    full_url = normalize_url(urljoin(page_url, raw_href))
                    if full_url in seen_urls:
                        continue

                    link_text = anchor.get_text(" ", strip=True)
                    ext = ""
                    path = urlparse(full_url).path
                    if "." in path:
                        ext = path[path.rfind("."):].lower()

                    is_doc = ext in DOCUMENT_EXTENSIONS or ".pdf" in full_url.lower()
                    is_relevant = bool(RELEVANT_TERMS.search(link_text + " " + full_url))

                    if not (is_doc or is_relevant):
                        continue

                    seen_urls.add(full_url)

                    # Formulate title
                    if meeting_number and meeting_date:
                        base_title = f"Senate Meeting {meeting_number} ({meeting_date})"
                        if link_text and link_text.lower() not in {"view", "download", "pdf", "click here"}:
                            title = f"{base_title} - {clean_title(link_text)}"
                        else:
                            title = base_title
                    else:
                        title = clean_title(link_text or description or "Senate Document")

                    file_type = ext.lstrip(".") if ext else "pdf"

                    items.append(
                        DiscoveredItem(
                            title=title,
                            source_page_url=page_url,
                            download_url=full_url,
                            category=source_config.category,
                            file_type=file_type,
                            publication_date=meeting_date if meeting_date else None,
                            meeting_number=meeting_number,
                            metadata={
                                "serial": serial,
                                "description": description,
                                "link_text": link_text,
                                "raw_href": raw_href,
                            },
                        )
                    )

        return items
