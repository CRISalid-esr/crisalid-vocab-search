""" Service for managing vocabulary backends."""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Type, Optional, Literal

import httpx
from loguru import logger

from app.models.concepts import SearchResults, Concept
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
            return [
                Vocabulary(identifier=p.identifier, languages=[], doc_count=0,
                           status=VocabStatus.OK)
                for p in proxies
            ]

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

    # ------------------------
    # Autocomplete (lists already parsed in the route)
    # ------------------------
    async def autocomplete(  # pylint: disable=too-many-arguments, too-many-locals
            self,
            *,
            q: str,
            vocabs: Optional[List[str]],
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
        Fan-out prefix search across selected vocabularies, merge results, sort by score desc,
        deduplicate by IRI, then apply offset/limit. Returns SearchResults.
        """
        if not q:
            logger.info("autocomplete called with an empty 'q' parameter")
            return SearchResults(total=0, items=[])

        all_proxies = self._build_proxies()
        selected: List[VocabProxy]
        if vocabs:
            wanted = set(vocabs)
            selected = [p for p in all_proxies if p.identifier in wanted]
            missing = wanted.difference({p.identifier for p in selected})
            if missing:
                logger.warning(
                    f"autocomplete: unknown vocab identifiers ignored: {sorted(missing)}")
        else:
            selected = all_proxies

        if not selected:
            logger.info("autocomplete: no vocabularies selected after filtering")
            return SearchResults(total=0, items=[])

        # Ask each proxy for limit+offset results so we can globally merge/slice
        per_proxy_size = max(0, limit + offset)

        async with httpx.AsyncClient(timeout=httpx.Timeout(5.0, connect=2.0, read=3.0)) as client:
            tasks = [
                p.autocomplete(
                    client,
                    q=q,
                    lang=lang,
                    fields=fields,
                    display_langs=display_langs,
                    display_fields=display_fields,
                    limit=per_proxy_size,
                    offset=0,  # proxies fetch from 0; we slice globally below
                    highlight=highlight,
                    broader=broader,
                    narrower=narrower,
                    broader_depth=broader_depth,
                    narrower_depth=narrower_depth,
                )
                for p in selected
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        # Merge totals + items (ignore proxies that raised)
        total = 0
        merged: List[Concept] = []
        for res in results:
            if isinstance(res, Exception):
                logger.warning(f"autocomplete: proxy error ignored: {res!r}")
                continue
            total += int(res.total or 0)
            merged.extend(res.items or [])

        # Sort by score desc (None treated as 0), stable by iri
        merged.sort(key=lambda c: ((c.score or 0.0), c.iri), reverse=True)

        # Deduplicate by IRI, keeping first (highest score)
        seen: set[str] = set()
        deduped: List[Concept] = []
        for c in merged:
            if c.iri in seen:
                continue
            seen.add(c.iri)
            deduped.append(c)

        # Apply global offset/limit
        if offset:
            deduped = deduped[offset:]
        if limit is not None:
            deduped = deduped[:limit]

        return SearchResults(total=total, items=deduped)
