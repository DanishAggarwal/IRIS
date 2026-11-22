"""Base extraction strategy interface for parsing PEC webpages."""

from abc import ABC, abstractmethod
from bs4 import BeautifulSoup

from crawler.config import DiscoveredItem, SourceConfig


class BaseExtractionStrategy(ABC):
    """Abstract base class for extracting document candidates from a page's DOM."""

    @abstractmethod
    def extract_documents(
        self,
        soup: BeautifulSoup,
        page_url: str,
        source_config: SourceConfig,
    ) -> list[DiscoveredItem]:
        """Extract candidate document items from the parsed HTML page.

        Args:
            soup: Parsed BeautifulSoup object.
            page_url: The canonical URL of the page being parsed.
            source_config: The source configuration being processed.

        Returns:
            List of DiscoveredItem metadata objects.
        """
        pass
