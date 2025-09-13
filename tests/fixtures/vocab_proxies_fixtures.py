"""Fixtures for vocabulary proxy tests"""
from __future__ import annotations

from typing import List

import httpx
import pytest
from loguru import logger

from app.models.vocabs import Vocabulary, VocabStatus
from app.services.proxies.base import VocabProxy
from app.services.vocab_service import VocabService


class FakeProxyOk(VocabProxy):
    """ Simulate a healthy backend """

    def _validate_cfg(self) -> None:
        # Accept any cfg in tests
        return None

    async def probe(self, client: httpx.AsyncClient) -> Vocabulary:
        """Simulate a healthy backend"""
        return Vocabulary(
            identifier=self.identifier,
            languages=["en", "fr"],
            doc_count=42,
            status=VocabStatus.OK,
        )


class FakeProxyUnavailable(VocabProxy):
    """ Simulate an unavailable backend """

    def _validate_cfg(self) -> None:
        return None

    async def probe(self, client: httpx.AsyncClient) -> Vocabulary:
        """Simulate an unavailable backend"""
        logger.warning(f"[{self.identifier}] simulated backend down")
        return Vocabulary(
            identifier=self.identifier,
            languages=[],
            doc_count=0,
            status=VocabStatus.UNAVAILABLE,
        )


# ---------- Fixtures ----------

@pytest.fixture
def proxy_ok() -> FakeProxyOk:
    """ Simple healthy proxy instance """
    return FakeProxyOk(identifier="jel", cfg={})


@pytest.fixture
def proxy_unavailable() -> FakeProxyUnavailable:
    """ Simple unavailable proxy instance """
    return FakeProxyUnavailable(identifier="mesh", cfg={})


@pytest.fixture
def proxies_ok() -> List[VocabProxy]:
    """ Two healthy proxy instances """
    return [FakeProxyOk(identifier="jel", cfg={}), FakeProxyOk(identifier="mesh", cfg={})]


@pytest.fixture
def proxies_mixed() -> List[VocabProxy]:
    """ One healthy and one unavailable proxy instance """
    return [FakeProxyOk(identifier="jel", cfg={}), FakeProxyUnavailable(identifier="mesh", cfg={})]


@pytest.fixture
def patch_build_proxies(monkeypatch):
    """
    Factory to patch VocabService._build_proxies() to return the provided list.
    Usage:
        patch_build_proxies(proxies)
    """

    def _apply(proxies_list):
        def _fake_build_proxies(_):
            return proxies_list

        monkeypatch.setattr(VocabService, "_build_proxies", _fake_build_proxies, raising=True)
        return proxies_list

    return _apply
