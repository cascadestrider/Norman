from abc import ABC, abstractmethod
from norman.models import Lead, ScoutResult


class BaseScout(ABC):
    """Base class for all Norman scout agents."""

    name: str = "base"
    source: str = "base"

    @abstractmethod
    def run(self, seen_urls: set[str]) -> ScoutResult:
        """Execute the scout and return leads + errors.

        Args:
            seen_urls: URLs already visited in previous runs (for dedup).

        Returns:
            ScoutResult with leads above threshold and any errors.
        """
        ...
