"""Abstract base class for vocabulary proxies."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, List, Literal

import httpx

from app.models.concepts import SearchResults
from app.models.vocabs import Vocabulary


class VocabProxy(ABC):
    """
    Abstract proxy for a vocabulary backend.
    Concrete proxies validate their config and implement 'probe' and 'autocomplete'.
    """

    def __init__(self, identifier: str, cfg: Dict[str, Any]):
        self.identifier = identifier
        self.cfg = cfg or {}
        self._validate_cfg()

    @abstractmethod
    def _validate_cfg(self) -> None:
        """
        Validate self.cfg and raise ValueError on any issues.
        """

    @abstractmethod
    async def probe(self, client: httpx.AsyncClient) -> Vocabulary:
        """
        Build and return a Vocabulary item for this backend.
        Implementations must catch their own network/parse errors and
        return a Vocabulary with status=UNAVAILABLE when failing.
        """

    @abstractmethod
    async def autocomplete(  # pylint: disable=too-many-arguments
            self,
            client: httpx.AsyncClient,
            *,
            q: str,
            lang: Optional[List[str]],
            fields: Optional[List[str]],
            display_langs: Optional[List[str]],
            display_fields: Optional[List[str]],
            limit: int,
            offset: int,
            highlight: bool,
            broader: Literal["ids", "full"],
            narrower: Literal["ids", "full"],
            broader_depth: int,
            narrower_depth: int,
    ) -> SearchResults:
        """
        Perform a prefix search against this single backend and return SearchResults.
        Implementations should handle their own network/parse errors and, on failure,
        return an empty SearchResults (total=0, items=[]), logging details as appropriate.
        """
