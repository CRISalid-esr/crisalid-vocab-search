""" Local OpenSearch-backed vocabulary proxy """
from __future__ import annotations

from dataclasses import dataclass
from json import JSONDecodeError
from typing import List, Optional, Dict, Any, Literal

import httpx
from loguru import logger

from app.models.concepts import (
    RDFLiteral,
    BestLabel,
    Concept,
    SearchResults,
)
from app.models.vocabs import Vocabulary, VocabStatus
from app.services.proxies.base import VocabProxy


@dataclass
class _OSHitParts:  # pylint: disable=too-many-instance-attributes
    """ Parts of an OpenSearch hit """
    iri: Optional[str]
    scheme: Optional[str]
    top_concept: Optional[bool]
    lang_set: Optional[List[str]]
    broader_ids: List[str]
    narrower_ids: List[str]
    score: Optional[float]
    hl: Dict[str, List[str]]
    pref_map: Optional[Dict[str, Any]]
    alt_map: Optional[Dict[str, Any]]
    desc_map: Optional[Dict[str, Any]]


class LocalOpenSearchVocabProxy(VocabProxy):
    """
    Local OpenSearch-backed vocabulary proxy
    Config format:
      config:
        host: http://localhost
        port: 9200
    """

    # -------------------------
    # Config / base URL
    # -------------------------
    def _validate_cfg(self) -> None:
        host = self.cfg.get("host")
        port = self.cfg.get("port")
        if not isinstance(host, str) or not host:
            raise ValueError(f"[{self.identifier}] config.host must be a non-empty string")
        if not isinstance(port, int):
            try:
                self.cfg["port"] = int(port)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"[{self.identifier}] config.port must be an integer") from exc

    def _base_url(self) -> str:
        host = self.cfg["host"].rstrip("/")
        port = int(self.cfg["port"])
        if host.startswith(("http://", "https://")):
            return f"{host}:{port}"
        return f"http://{host}:{port}"

    # -------------------------
    # Probe
    # -------------------------
    async def probe(self, client: httpx.AsyncClient) -> Vocabulary:
        item = Vocabulary(
            identifier=self.identifier, languages=[], doc_count=0, status=VocabStatus.UNAVAILABLE
        )

        url = f"{self._base_url()}/concepts/_search"
        payload = {
            "size": 0,
            "track_total_hits": True,
            "aggs": {"langs": {"terms": {"field": "lang_set"}}},
        }

        try:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()

            doc_count = int(data.get("hits", {}).get("total", {}).get("value", 0) or 0)
            buckets = data.get("aggregations", {}).get("langs", {}).get("buckets", []) or []
            languages: List[str] = [
                b.get("key") for b in buckets if isinstance(b, dict) and "key" in b
            ]

            item.languages = languages
            item.doc_count = doc_count
            item.status = VocabStatus.OK
        except httpx.RequestError as e:
            logger.warning(f"[{self.identifier}] Request error probing OS backend: {e!r}")
        except httpx.HTTPStatusError as e:
            code = e.response.status_code if e.response is not None else "?"
            logger.warning(f"[{self.identifier}] HTTP {code} probing OS backend: {e!r}")
        except JSONDecodeError as e:
            logger.warning(f"[{self.identifier}] Invalid JSON from OS backend: {e!r}")
        except ValueError as e:
            # covers unexpected shapes/values we cast
            logger.warning(f"[{self.identifier}] Value error parsing OS response: {e!r}")

        return item

    # -------------------------
    # Autocomplete (public)
    # -------------------------
    async def autocomplete(  # pylint: disable=too-many-arguments, too-many-locals
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
        Prefix search using .edge subfields (pref/alt). Returns SearchResults with
        Concept items that include RDFLiteral lists and optional highlights.

        NOTE:
        - Relations are returned as IDs only; if 'full' is requested,
        a warning is logged and IDs are returned.
        - 'display_fields' is currently advisory; all fields are populated when available,
          with language filtering via 'display_langs'.
        """
        if broader == "full" or narrower == "full":
            logger.warning(
                f"[{self.identifier}] 'full' relation expansion requested; "
                "returning IDs only (not implemented)."
            )

        payload = self._generate_os_payload(  # pylint: disable=duplicate-code
            q=q,
            lang=lang,
            fields=fields,
            display_langs=display_langs,
            limit=limit,
            offset=offset,
            highlight=highlight,
        )

        data = await self._send_os_query(
            client,
            f"{self._base_url()}/concepts/_search",
            payload
        )

        return self._format_result(
            data=data,
            display_langs=display_langs,
            broader=broader,
            narrower=narrower,
        )

    # -------------------------
    # Phase 1: generate payload
    # -------------------------
    def _generate_os_payload(  # pylint: disable=too-many-arguments
            self,
            *,
            q: str,
            lang: Optional[List[str]],
            fields: Optional[List[str]],
            display_langs: Optional[List[str]],
            limit: int,
            offset: int,
            highlight: bool,
    ) -> Dict[str, Any]:
        # Determine which fields to query for prefix matching
        requested = set((fields or ["pref", "alt"]))
        query_fields = self._build_os_query_fields(lang, requested)

        hl_fields = self._build_os_hl_fields(display_langs) if highlight else {}

        payload: Dict[str, Any] = {
            "from": offset,
            "size": limit,
            "track_total_hits": True,
            "_source": [
                "iri",
                "scheme",
                "top_concept",
                "lang_set",
                "pref",
                "alt",
                "description",
                "broader",
                "narrower",
            ],
            "query": {
                "multi_match": {
                    "query": q,
                    "type": "bool_prefix",
                    "fields": query_fields or ["pref.*.edge", "alt.*.edge"],
                    "analyzer": "fold",
                }
            },
        }

        if highlight and hl_fields:
            payload["highlight"] = {
                "require_field_match": False,
                "fields": hl_fields,
            }

        return payload

    def _build_os_hl_fields(self, display_langs):
        # Build highlight fields on BASE (not .edge) for nicer snippets
        hl_fields: Dict[str, Dict[str, Any]] = {}
        # Use display_langs to decide what to show to users;
        # if not provided, highlight all langs.
        target_langs = display_langs if display_langs else None

        def add_hl(root: str):
            if target_langs:
                for l in target_langs:
                    hl_fields[f"{root}.{l}"] = {"number_of_fragments": 0}
            else:
                hl_fields[f"{root}.*"] = {"number_of_fragments": 0}

        add_hl("pref")
        add_hl("alt")
        add_hl("description")
        return hl_fields

    def _build_os_query_fields(self, lang, requested):
        query_fields: List[str] = []

        def add_edge_fields(root: str):
            if lang:
                for l in lang:
                    query_fields.append(f"{root}.{l}.edge")
            else:
                query_fields.append(f"{root}.*.edge")

        if "pref" in requested:
            add_edge_fields("pref")
        if "alt" in requested:
            add_edge_fields("alt")
        if "description" in requested:
            # Not n-grammed, but bool_prefix works reasonably for autocomplete
            if lang:
                for l in lang:
                    query_fields.append(f"description.{l}")
            else:
                query_fields.append("description.*")
        if "search_all" in requested:
            # Fallback catch-all for cross-language text
            query_fields.append("search_all")
        return query_fields

    # -------------------------
    # Phase 2: send to OS
    # -------------------------
    async def _send_os_query(
            self, client: httpx.AsyncClient, url: str, payload: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        try:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            return resp.json()
        except httpx.RequestError as e:
            logger.warning(f"[{self.identifier}] Request error during autocomplete: {e!r}")
        except httpx.HTTPStatusError as e:
            code = e.response.status_code if e.response is not None else "?"
            logger.warning(f"[{self.identifier}] HTTP {code} during autocomplete: {e!r}")
        except JSONDecodeError as e:
            logger.warning(f"[{self.identifier}] Invalid JSON during autocomplete: {e!r}")
        except ValueError as e:
            logger.warning(f"[{self.identifier}] Value error parsing autocomplete response: {e!r}")
        return None

    # -------------------------
    # Phase 3: format result
    # -------------------------
    def _format_result(  # no pragma needed anymore
            self,
            *,
            data: Optional[Dict[str, Any]],
            display_langs: Optional[List[str]],
            broader: Literal["ids", "full"],
            narrower: Literal["ids", "full"],
    ) -> SearchResults:
        if data is None:
            return SearchResults(total=0, items=[])
        if broader == "full" or narrower == "full":
            logger.warning(
                f"[{self.identifier}] 'full' relation expansion requested; "
                "returning IDs only (not implemented)."
            )
        hits = data.get("hits", {}).get("hits", []) or []
        items: List[Concept] = []
        for h in hits:
            parts = self._parse_hit(h)
            items.append(
                self._concept_from_parts(parts, display_langs)
            )

        total = int(data.get("hits", {}).get("total", {}).get("value", 0) or 0)
        return SearchResults(total=total, items=items)

    @staticmethod
    def _dict_to_literals(
            obj: Optional[Dict[str, Any]],
            field_name: str,
            display_langs: Optional[List[str]] = None,
            hl: Optional[Dict[str, List[str]]] = None,
    ) -> Optional[List[RDFLiteral]]:
        if obj is None:
            return None
        out: List[RDFLiteral] = []
        for lang_code, texts in obj.items():
            if display_langs and lang_code not in display_langs:
                continue
            if not isinstance(texts, list):
                continue
            # First snippet for that (field, lang), if any
            hl_key = f"{field_name}.{lang_code}"
            snippet = None
            snippets = hl.get(hl_key)
            if isinstance(snippets, list) and snippets:
                snippet = str(snippets[0])
            for idx, t in enumerate(texts):
                out.append(
                    RDFLiteral(
                        text=None if t is None else str(t),
                        lang=str(lang_code),
                        # attach highlight only to the first literal of that language/field
                        highlight=(snippet if (idx == 0) else None),
                    )
                )
        return out or None

    @staticmethod
    def _choose_best_litteral(
            pref_literals: Optional[List[RDFLiteral]],
            alt_literals: Optional[List[RDFLiteral]],
            desc_literals: Optional[List[RDFLiteral]],
            display_langs: Optional[List[str]] = None,
    ) -> Optional[BestLabel]:
        # Prefer a highlighted pref label in display_langs,
        # then any highlight on pref/alt/description
        def pick_from(
                lits: Optional[List[RDFLiteral]],
                source: Literal["pref", "alt", "description"],
        ):
            if not lits:
                return None
            # try priority by display_langs if provided
            candidates = lits
            if display_langs:
                # stable order: keep only desired langs, preserve original order
                candidates = [x for x in lits if x.lang in display_langs]
                if not candidates:
                    candidates = lits
            # prefer highlighted literal
            for lit in candidates:
                if lit.highlight:
                    return BestLabel(
                        text=lit.text, lang=lit.lang, highlight=lit.highlight,
                        source_field=source
                    )
            # else first available
            lit0 = candidates[0]
            return BestLabel(
                text=lit0.text, lang=lit0.lang, highlight=lit0.highlight,
                source_field=source
            )

        for source, lits in (("pref", pref_literals), ("alt", alt_literals),
                             ("description", desc_literals)):
            chosen = pick_from(lits, source)  # type: ignore[arg-type]
            if chosen:
                return chosen
        return None

    def _parse_hit(self, h: Dict[str, Any]) -> _OSHitParts:
        src = h.get("_source", {}) or {}
        return _OSHitParts(
            iri=src.get("iri"),
            scheme=src.get("scheme"),
            top_concept=src.get("top_concept") if isinstance(src.get("top_concept"),
                                                             bool) else None,
            lang_set=[str(x) for x in src.get("lang_set", [])] if isinstance(src.get("lang_set"),
                                                                             list) else None,
            broader_ids=[str(x) for x in (src.get("broader") or []) if isinstance(x, str)],
            narrower_ids=[str(x) for x in (src.get("narrower") or []) if isinstance(x, str)],
            score=(float(h.get("_score")) if h.get("_score") is not None else None),
            hl=(h.get("highlight") or {}),
            pref_map=src.get("pref"),
            alt_map=src.get("alt"),
            desc_map=src.get("description"),
        )

    def _concept_from_parts(
            self,
            parts: _OSHitParts,
            display_langs: Optional[List[str]],
    ) -> Concept:
        pref_literals = self._dict_to_literals(parts.pref_map, "pref", display_langs, parts.hl)
        alt_literals = self._dict_to_literals(parts.alt_map, "alt", display_langs, parts.hl)
        desc_literals = self._dict_to_literals(parts.desc_map, "description", display_langs,
                                               parts.hl)

        best = self._choose_best_litteral(
            pref_literals=pref_literals,
            alt_literals=alt_literals,
            desc_literals=desc_literals,
            display_langs=display_langs,
        )

        return Concept(
            iri=str(parts.iri),
            scheme=(None if parts.scheme is None else str(parts.scheme)),
            score=parts.score,
            top_concept=parts.top_concept,
            lang_set=parts.lang_set,
            best_label=best,
            pref=pref_literals,
            alt=alt_literals,
            description=desc_literals,
            broader=parts.broader_ids,
            narrower=parts.narrower_ids,
        )
