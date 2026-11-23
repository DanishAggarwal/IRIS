"""Strategy factory for PEC document extraction."""

from crawler.strategies.base import BaseExtractionStrategy
from crawler.strategies.curriculum import CurriculumStructureStrategy
from crawler.strategies.generic import GenericLinkStrategy
from crawler.strategies.senate import SenateTableStrategy

STRATEGY_REGISTRY: dict[str, type[BaseExtractionStrategy]] = {
    "senate_table": SenateTableStrategy,
    "generic_link": GenericLinkStrategy,
    "curriculum_table": CurriculumStructureStrategy,
}


def get_strategy(strategy_name: str) -> BaseExtractionStrategy:
    """Retrieve extraction strategy instance by strategy name."""
    cls = STRATEGY_REGISTRY.get(strategy_name)
    if not cls:
        # Fallback to generic link strategy
        return GenericLinkStrategy()
    return cls()
