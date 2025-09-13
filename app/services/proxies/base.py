"""Abstract base class for vocabulary proxies."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict

import httpx

from app.models.vocabs import Vocabulary


class VocabProxy(ABC):
    """
    Abstract proxy for a vocabulary backend.
    Concrete proxies validate their config and implement 'probe'.
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
        Build and return a VocabItem for this backend.
        Implementations must catch their own network/parse errors and
        return a VocabItem with status=UNAVAILABLE when failing.
        """
