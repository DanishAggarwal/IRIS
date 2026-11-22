"""Strategy for extracting document links from generic PEC institutional webpages."""

from pathlib import Path
import re
from urllib.parse import unquote, urldefrag, urljoin, urlparse
from bs4 import BeautifulSoup

from crawler.config import DiscoveredItem, SourceConfig
from crawler.strategies.base import BaseExtractionStrategy

DOCUMENT_EXTENSIONS = {
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".odt", ".ods", ".odp", ".rtf", ".txt", ".csv",
}

SKIP_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".css", ".js",
    ".ico", ".mp4", ".mp3", ".woff", ".woff2", ".ttf", ".eot",
}


def normalize_url(url: str) -> str:
    """Remove fragments; retain query strings."""
    return urldefrag(url.strip())[0]


def clean_title(value: str) -> str:
    """Normalize and clean document title for human readability."""
    value = unquote(value).replace("_", " ")
    value = re.sub(r"\s+", " ", value).strip()
    return value[:200] or "Institutional Document"


class GenericLinkStrategy(BaseExtractionStrategy):
    """Extracts document links from standard institutional landing pages and tables."""

    def extract_documents(
        self,
        soup: BeautifulSoup,
        page_url: str,
        source_config: SourceConfig,
    ) -> list[DiscoveredItem]:
        items: list[DiscoveredItem] = []
        seen_urls: set[str] = set()

        # Optional keyword filters from source config
        cfg = source_config.config or {}
        include_keywords = [k.lower() for k in cfg.get("include_keywords", [])]
        exclude_keywords = [k.lower() for k in cfg.get("exclude_keywords", [])]

        for anchor in soup.find_all("a", href=True):
            raw_href = anchor["href"].strip()
            if not raw_href or raw_href.startswith(("#", "javascript:", "mailto:", "tel:")):
                continue

            full_url = normalize_url(urljoin(page_url, raw_href))
            if full_url in seen_urls:
                continue

            parsed = urlparse(full_url)
            path = parsed.path.lower()
            ext = ""
            if "." in path:
                ext = path[path.rfind("."):].lower()

            if ext in SKIP_EXTENSIONS:
                continue

            # Check if link points to a document
            is_doc = ext in DOCUMENT_EXTENSIONS or ".pdf" in full_url.lower()
            if not is_doc:
                continue

            link_text = anchor.get_text(" ", strip=True)
            title_attr = anchor.get("title", "").strip()

            # Find context from parent (e.g., table row, list item, or paragraph)
            parent = anchor.find_parent(["tr", "li", "p", "div"])
            parent_text = parent.get_text(" ", strip=True) if parent else ""

            combined_search_text = f"{link_text} {title_attr} {parent_text} {full_url}".lower()

            # Check keyword inclusion
            if include_keywords and not any(kw in combined_search_text for kw in include_keywords):
                continue
            # Check keyword exclusion
            if exclude_keywords and any(kw in combined_search_text for kw in exclude_keywords):
                continue

            seen_urls.add(full_url)

            # Derive title: prefer link text, then title attr, then filename
            url_filename = Path(unquote(parsed.path)).stem
            candidate_title = link_text or title_attr or url_filename

            # If link text is purely generic like "Download" or "Click here" or "PDF", use parent text or filename
            if candidate_title.lower() in {"download", "view", "pdf", "click here", "link", "read more"}:
                if parent_text and len(parent_text) > len(candidate_title):
                    candidate_title = parent_text
                else:
                    candidate_title = url_filename

            final_title = clean_title(candidate_title)

            # Extract possible academic year or date from text/url
            # E.g. "2024-25", "2026", "25-26"
            acad_year_match = re.search(r"\b(20\d\d[-–]\d\d|20\d\d)\b", f"{final_title} {parent_text} {full_url}")
            academic_year = acad_year_match.group(0) if acad_year_match else None

            file_type = ext.lstrip(".") if ext else "pdf"

            items.append(
                DiscoveredItem(
                    title=final_title,
                    source_page_url=page_url,
                    download_url=full_url,
                    category=source_config.category,
                    file_type=file_type,
                    publication_date=None,
                    meeting_number=None,
                    academic_year=academic_year,
                    metadata={
                        "link_text": link_text,
                        "title_attr": title_attr,
                        "parent_text": parent_text[:300] if parent_text else None,
                        "raw_href": raw_href,
                    },
                )
            )

        return items
