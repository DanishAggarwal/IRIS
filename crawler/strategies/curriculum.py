"""Strategy for extracting undergraduate and postgraduate programme curriculum schemes and syllabi from PEC table matrices."""

from pathlib import Path
import re
from typing import Any, Optional
from urllib.parse import unquote, urldefrag, urljoin, urlparse

from bs4 import BeautifulSoup

from crawler.config import DiscoveredItem, SourceConfig
from crawler.strategies.base import BaseExtractionStrategy


def normalize_url(url: str) -> str:
    """Remove fragments; retain query strings."""
    return urldefrag(url.strip())[0]


def clean_title(value: str) -> str:
    """Normalize and clean document title for human readability."""
    value = unquote(value).replace("_", " ")
    value = re.sub(r"\s+", " ", value).strip()
    return value[:200] or "Curriculum Scheme"


class CurriculumStructureStrategy(BaseExtractionStrategy):
    """Parses PEC Curriculum Matrix tables that link to both direct PDFs and discipline subpages."""

    def extract_documents(
        self,
        soup: BeautifulSoup,
        page_url: str,
        source_config: SourceConfig,
        client: Optional[Any] = None,
    ) -> list[DiscoveredItem]:
        items: list[DiscoveredItem] = []
        seen_urls: set[str] = set()

        tables = soup.find_all("table")
        if not tables:
            from crawler.strategies.generic import GenericLinkStrategy

            return GenericLinkStrategy().extract_documents(
                soup, page_url, source_config, client=client
            )

        for table in tables:
            # Extract header column titles (e.g. 2020 Batch Onwards, 2023 Batch Onwards, 2024 Batch Onwards)
            headers: list[str] = []
            header_tr = table.find("tr")
            if header_tr:
                for th in header_tr.find_all(["th", "td"]):
                    headers.append(clean_title(th.get_text(" ", strip=True)))

            for tr in table.find_all("tr"):
                cells = tr.find_all(["td", "th"])
                if not cells or cells[0].name == "th":
                    continue

                dept_name = clean_title(cells[0].get_text(" ", strip=True))
                if not dept_name or dept_name.lower() in ("department", "programmes", "discipline"):
                    continue

                for col_idx, cell in enumerate(cells[1:], start=1):
                    col_header = headers[col_idx] if col_idx < len(headers) else ""
                    for a in cell.find_all("a", href=True):
                        raw_href = a["href"].strip()
                        if not raw_href or raw_href.startswith(
                            ("#", "javascript:", "mailto:", "tel:")
                        ):
                            continue

                        full_link = normalize_url(urljoin(page_url, raw_href))
                        anchor_text = clean_title(a.get_text(" ", strip=True))

                        # Determine descriptive title
                        if (
                            anchor_text
                            and len(anchor_text) > 3
                            and anchor_text.lower()
                            not in ("download", "click here", "pdf", "link", "view")
                        ):
                            item_title = anchor_text
                        elif dept_name:
                            item_title = (
                                f"{dept_name} - {col_header}" if col_header else dept_name
                            )
                        else:
                            item_title = col_header or "UG Curriculum"

                        # If title is generic like "UG Curriculum (2020-21 Session Onwards)", qualify with department
                        if (
                            item_title.lower().startswith("ug curriculum")
                            and dept_name
                            and dept_name.lower() not in item_title.lower()
                        ):
                            item_title = f"{dept_name} - {item_title}"

                        parsed = urlparse(full_link)
                        path_lower = parsed.path.lower()

                        if path_lower.endswith(".pdf") or ".pdf" in full_link.lower():
                            # Direct PDF link
                            if full_link not in seen_urls:
                                seen_urls.add(full_link)
                                items.append(
                                    self._build_item(
                                        item_title, page_url, full_link, source_config, dept_name
                                    )
                                )
                        elif client is not None and (
                            "pec.ac.in" in parsed.netloc or full_link.startswith("/")
                        ):
                            # Follow discipline landing subpage to find the underlying PDF
                            try:
                                sub_resp = client.get(full_link, timeout=10.0)
                                if sub_resp.status_code == 200:
                                    sub_soup = BeautifulSoup(sub_resp.text, "html.parser")
                                    for sub_a in sub_soup.find_all("a", href=True):
                                        sub_href = sub_a["href"].strip()
                                        if ".pdf" in sub_href.lower():
                                            sub_pdf = normalize_url(
                                                urljoin(full_link, sub_href)
                                            )
                                            if sub_pdf not in seen_urls:
                                                seen_urls.add(sub_pdf)
                                                items.append(
                                                    self._build_item(
                                                        item_title,
                                                        full_link,
                                                        sub_pdf,
                                                        source_config,
                                                        dept_name,
                                                    )
                                                )
                            except Exception:
                                pass

        return items

    def _build_item(
        self,
        title: str,
        source_page_url: str,
        download_url: str,
        source_config: SourceConfig,
        dept_name: str,
    ) -> DiscoveredItem:
        acad_match = re.search(r"\b(20\d\d[-–]\d\d|20\d\d)\b", f"{title} {download_url}")
        academic_year = acad_match.group(0) if acad_match else None

        return DiscoveredItem(
            title=title,
            source_page_url=source_page_url,
            download_url=download_url,
            category=source_config.category,
            file_type="pdf",
            publication_date=None,
            meeting_number=None,
            academic_year=academic_year,
            metadata={
                "department": dept_name,
                "strategy": "curriculum_table",
            },
        )
