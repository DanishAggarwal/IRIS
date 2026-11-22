"""Core discovery engine for scanning configured PEC institutional webpages."""

import logging
import re
import time
from typing import Optional
from urllib.parse import urldefrag, urljoin, urlparse

from bs4 import BeautifulSoup
import httpx

from crawler.config import DiscoveredItem, SourceConfig
from crawler.strategies import get_strategy

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 25.0
DEFAULT_REQUEST_DELAY = 0.3
DEFAULT_MAX_PAGES_PER_SOURCE = 10

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 "
        "(compatible; IRIS-PEC-Discovery/1.0)"
    )
}


def is_pec_domain(url: str) -> bool:
    """Strict domain boundary check. Only allows pec.ac.in and *.pec.ac.in."""
    try:
        hostname = (urlparse(url).hostname or "").lower()
        return hostname == "pec.ac.in" or hostname.endswith(".pec.ac.in")
    except Exception:
        return False


def normalize_url(url: str) -> str:
    """Strip fragments and whitespace while preserving query strings."""
    return urldefrag(url.strip())[0]


class PECCrawlerEngine:
    """Discovers public documents from configured PEC institutional pages without downloading files."""

    def __init__(
        self,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        request_delay: float = DEFAULT_REQUEST_DELAY,
        max_pages_per_source: int = DEFAULT_MAX_PAGES_PER_SOURCE,
        inspect_http_headers: bool = True,
        client: Optional[httpx.Client] = None,
    ) -> None:
        self.timeout = timeout
        self.request_delay = request_delay
        self.max_pages_per_source = max_pages_per_source
        self.inspect_http_headers = inspect_http_headers
        self._external_client = client

    def _get_client(self) -> httpx.Client:
        if self._external_client is not None:
            return self._external_client
        return httpx.Client(
            headers=DEFAULT_HEADERS,
            timeout=self.timeout,
            follow_redirects=True,
            verify=False,  # Allow PEC self-signed/institutional certs
        )

    def scan_source(self, source: SourceConfig) -> list[DiscoveredItem]:
        """Scan a single configured source webpage and return discovered document items.

        Does NOT download files. Operates strictly within PEC domains.
        """
        if not source.enabled:
            logger.info("Source %s (%s) is disabled. Skipping.", source.source_id, source.url)
            return []

        if not is_pec_domain(source.url):
            logger.warning(
                "Source %s URL '%s' violates PEC domain security boundary. Skipping.",
                source.source_id,
                source.url,
            )
            return []

        strategy = get_strategy(source.strategy)
        discovered: list[DiscoveredItem] = []
        visited_pages: set[str] = set()
        queue: list[str] = [normalize_url(source.url)]
        seen_download_urls: set[str] = set()

        logger.info("Starting discovery scan for source: %s (%s)", source.name, source.url)

        owns_client = self._external_client is None
        client = self._get_client()
        try:
            while queue and len(visited_pages) < self.max_pages_per_source:
                current_url = queue.pop(0)
                if current_url in visited_pages:
                    continue

                if not is_pec_domain(current_url):
                    continue

                visited_pages.add(current_url)

                try:
                    resp = client.get(current_url)
                    if resp.status_code != 200:
                        logger.warning("HTTP %d for URL: %s", resp.status_code, current_url)
                        continue

                    # Validate response is HTML
                    content_type = resp.headers.get("Content-Type", "").lower()
                    if "html" not in content_type and not resp.text.lstrip().startswith("<"):
                        logger.debug("Skipping non-HTML page: %s", current_url)
                        continue

                    soup = BeautifulSoup(resp.text, "html.parser")
                except Exception as exc:
                    logger.error("Failed to fetch %s: %exc", current_url, exc)
                    continue

                # Extract documents via strategy
                items = strategy.extract_documents(soup, current_url, source)
                for item in items:
                    # Enforce PEC domain on all discovered download URLs
                    if not is_pec_domain(item.download_url):
                        logger.warning(
                            "Discovered download URL '%s' is external to PEC domain. Skipping.",
                            item.download_url,
                        )
                        continue

                    if item.download_url not in seen_download_urls:
                        seen_download_urls.add(item.download_url)

                        # Opportunistically inspect HTTP headers via lightweight HEAD request (no download)
                        if self.inspect_http_headers:
                            try:
                                head_resp = client.head(item.download_url, timeout=5.0)
                                if head_resp.status_code == 200:
                                    item.http_etag = head_resp.headers.get("etag")
                                    item.http_last_modified = head_resp.headers.get("last-modified")
                                    cl = head_resp.headers.get("content-length")
                                    item.http_content_length = int(cl) if cl and cl.isdigit() else None
                            except Exception as head_exc:
                                logger.debug("HEAD request failed for %s: %s", item.download_url, head_exc)

                        discovered.append(item)

                # Pagination discovery for multi-page archives
                self._discover_pagination(soup, current_url, queue, visited_pages)

                # Polite delay between page requests
                if queue:
                    time.sleep(self.request_delay)

        finally:
            if owns_client:
                client.close()

        logger.info(
            "Scan complete for '%s': visited %d pages, discovered %d documents.",
            source.name,
            len(visited_pages),
            len(discovered),
        )
        return discovered

    def _discover_pagination(
        self,
        soup: BeautifulSoup,
        current_url: str,
        queue: list[str],
        visited_pages: set[str],
    ) -> None:
        """Find pagination links (e.g. ?page=1) on the same site to continue archive scans."""
        for anchor in soup.find_all("a", href=True):
            raw_href = anchor["href"].strip()
            if not raw_href or raw_href.startswith(("#", "javascript:", "mailto:")):
                continue

            target = normalize_url(urljoin(current_url, raw_href))
            if not is_pec_domain(target) or target in visited_pages or target in queue:
                continue

            parsed = urlparse(target)
            label = anchor.get_text(" ", strip=True).lower()
            classes = " ".join(anchor.get("class", [])).lower()
            is_pager = (
                "pager" in classes
                or label in {"next", "›", "»", "last", "older", "1", "2", "3"}
                or bool(re.search(r"(?:^|[?&])(?:page|paged)=\d+", parsed.query))
            )
            if is_pager:
                queue.append(target)
