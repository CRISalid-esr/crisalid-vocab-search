""" Service for managing vocabulary backends."""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Type

import httpx
from loguru import logger

from app.models.vocabs import Vocabulary, VocabStatus
from app.services.proxies.base import VocabProxy
from app.services.proxies.local_opensearch import LocalOpenSearchVocabProxy
from app.settings.app_settings import AppSettings


class VocabService:
    """
    Service for managing vocabulary backends.
    """
    _TYPE_REGISTRY: Dict[str, Type[VocabProxy]] = {
        "local_os": LocalOpenSearchVocabProxy,
        # future: "remote_api": RemoteApiVocabProxy, ...
    }

    def __init__(self, settings: AppSettings):
        self.settings = settings

    @classmethod
    def validate_config_or_fail(cls, settings: AppSettings) -> None:
        """
        Validate the vocab_config in settings. Raise RuntimeError on any issues.
        Each vocabulary entry is validated by its proxy class constructor
        :param settings: AppSettings instance with vocab_config attribute
        :return: None
        """
        cfg = settings.vocab_config or {}
        entries = cfg.get("vocabularies", [])
        if not isinstance(entries, list) or not entries:
            raise RuntimeError("vocab_config.vocabularies must be a non-empty list")

        seen_identifiers: set[str] = set()
        for entry in entries:
            if not isinstance(entry, dict):
                raise RuntimeError("Each vocabulary entry must be an object")

            identifier = entry.get("identifier")
            vtype = entry.get("type")
            vcfg = entry.get("config")

            if not identifier or not isinstance(identifier, str):
                raise RuntimeError("Each vocabulary must have a non-empty string 'identifier'")
            if identifier in seen_identifiers:
                raise RuntimeError(f"Duplicate vocabulary identifier '{identifier}'")
            seen_identifiers.add(identifier)

            if not vtype or not isinstance(vtype, str):
                raise RuntimeError(f"[{identifier}] 'type' must be specified and be a string")
            proxy_cls = cls._TYPE_REGISTRY.get(vtype)
            if not proxy_cls:
                raise RuntimeError(f"[{identifier}] Unsupported vocabulary type '{vtype}'")

            if not isinstance(vcfg, dict):
                raise RuntimeError(f"[{identifier}] 'config' must be an object")

            # Let the proxy validate its own config (constructor validates)
            proxy_cls(identifier=identifier, cfg=vcfg)

    async def list_vocabs(self, probe: bool = True) -> List[Vocabulary]:
        """
        List available vocabularies, optionally probing each backend
        for status, languages, and doc_count.
        If probe is False, returns vocabularies with empty languages and doc_count=0, status=OK.
        :raises RuntimeError: if vocab_config is missing or invalid
        :param probe: Whether to probe each backend to populate languages and doc_count.
        :return: List of Vocabulary instances
        """
        proxies = self._build_proxies()

        if not probe:
            # no network calls; assume ok but with unknown counts/langs
            return [Vocabulary(identifier=p.identifier, languages=[], doc_count=0,
                               status=VocabStatus.OK) for p in
                    proxies]

        async with httpx.AsyncClient(timeout=httpx.Timeout(3.0, connect=2.0, read=2.5)) as client:
            items = await asyncio.gather(*[p.probe(client) for p in proxies])

        # Optionally log items that are unavailable
        for it in items:
            if it.status == VocabStatus.UNAVAILABLE:
                logger.warning(f"[{it.identifier}] Marked unavailable by proxy")

        return items

    def _build_proxies(self) -> List[VocabProxy]:
        cfg = self.settings.vocab_config or {}
        entries: List[Dict[str, Any]] = cfg.get("vocabularies", []) or []
        proxies: List[VocabProxy] = []
        for entry in entries:
            identifier = entry["identifier"]
            vtype = entry["type"]
            vcfg = entry["config"]
            proxy_cls = self._TYPE_REGISTRY[vtype]
            proxies.append(proxy_cls(identifier=identifier, cfg=vcfg))
        return proxies
