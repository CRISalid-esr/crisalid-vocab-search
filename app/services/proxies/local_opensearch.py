""" Local OpenSearch-backed vocabulary proxy """
from __future__ import annotations

from dataclasses import dataclass
from json import JSONDecodeError
from typing import List, Optional, Dict, Any, Literal, Iterable

import httpx
from loguru import logger

from app.models.concepts import RDFLiteral, BestLabel, Concept, SearchResults
from app.models.vocabs import Vocabulary, VocabStatus
from app.services.proxies.base import VocabProxy


@dataclass
class _OSHitParts:  # pylint: disable=too-many-instance-attributes
    """Parts of an OpenSearch hit"""
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
        index: concepts_jel  # optional, defaults to concepts_<identifier>
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
        if "index" in self.cfg:
            index = self.cfg["index"]
            if not isinstance(index, str) or not index:
                raise ValueError(f"[{self.identifier}] config.index must be a non-empty string")

    def _base_url(self) -> str:
        host = self.cfg["host"].rstrip("/")
        port = int(self.cfg["port"])
        if host.startswith(("http://", "https://")):
            return f"{host}:{port}"
        return f"http://{host}:{port}"

    def _index_name(self) -> str:
        return self.cfg.get("index") or f"concepts_{self.identifier}"

    # -------------------------
    # Language matching helpers
    # -------------------------
    @staticmethod
    def _norm_lang(code: str) -> str:
        """Normalize language tags: case-insensitive, dash-separated."""
        return code.strip().lower().replace("_", "-")

    @classmethod
    def _lang_base(cls, code: str) -> str:
        return cls._norm_lang(code).split("-", 1)[0]

    @classmethod
    def _lang_matches_any(cls, lang_code: str, wanted: Iterable[str]) -> bool:
        """
        True if lang_code matches any wanted code:
        - exact match: en-us in wanted
        - base match: wanted has en -> matches en-us/en-gb/...
        """
        lc = cls._norm_lang(lang_code)
        base = cls._lang_base(lc)
        wanted_norm = [cls._norm_lang(w) for w in wanted]

        if lc in wanted_norm:
            return True
        if base in wanted_norm:
            return True
        return False

    @classmethod
    def _pick_any_matching_lang(
            cls,
            available_langs: Iterable[str],
            wanted: Iterable[str],
    ) -> Optional[str]:
        """
        Choose any available language that matches wanted.
        Preference:
          1) exact match in wanted order
          2) base match in wanted order (e.g. wanted 'en' picks first available 'en-*')
        """
        avail_norm = [cls._norm_lang(a) for a in available_langs]
        wanted_norm = [cls._norm_lang(w) for w in wanted]

        # 1) exact match (respect wanted order)
        for w in wanted_norm:
            if w in avail_norm:
                return w

        # 2) base match (respect wanted order)
        for w in wanted_norm:
            if "-" in w:
                continue
            for a in avail_norm:
                if cls._lang_base(a) == w:
                    return a

        return None

    # -------------------------
    # Probe
    # -------------------------
    async def probe(self, client: httpx.AsyncClient) -> Vocabulary:
        item = Vocabulary(
            identifier=self.identifier, languages=[], doc_count=0, status=VocabStatus.UNAVAILABLE
        )

        url = f"{self._base_url()}/{self._index_name()}/_search"
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

        Language behavior:
        - display_langs may contain base tags like 'en' or 'fr'. These match variants
          like 'en-us', 'en-gb', 'fr-ca'. If multiple match, we keep any (deterministically
          picking one per base via wanted order + first available).

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

        payload = self._generate_os_payload(
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
            f"{self._base_url()}/{self._index_name()}/_search",
            payload,
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
            # deterministic sorting for stable pagination
            "sort": [{"_score": {"order": "desc"}}, {"iri": {"order": "asc"}}],
        }

        if highlight and hl_fields:
            payload["highlight"] = {
                "require_field_match": False,
                "fields": hl_fields,
            }

        return payload

    def _build_os_hl_fields(self, display_langs: Optional[List[str]]) -> Dict[str, Dict[str, Any]]:
        """
        Build highlight fields on BASE (not .edge) for nicer snippets.

        Important: if display_langs includes base tags like 'en' or 'fr', we cannot
        highlight 'pref.en' (field doesn't exist). In that case, highlight all
        languages and filter on the application side.
        """
        hl_fields: Dict[str, Dict[str, Any]] = {}

        target_langs = display_langs if display_langs else None
        target_norm = [self._norm_lang(x) for x in target_langs] if target_langs else None
        has_base = bool(target_norm and any("-" not in x for x in target_norm))

        def add_hl(root: str) -> None:
            if not target_langs:
                hl_fields[f"{root}.*"] = {"number_of_fragments": 0}
                return

            if has_base:
                # safest: highlight all and filter in _dict_to_literals
                hl_fields[f"{root}.*"] = {"number_of_fragments": 0}
                return

            # only region-specific tags were requested (en-us, fr-ca, ...)
            for l in target_norm or []:
                hl_fields[f"{root}.{l}"] = {"number_of_fragments": 0}

        add_hl("pref")
        add_hl("alt")
        add_hl("description")
        return hl_fields

    def _build_os_query_fields(self, lang: Optional[List[str]], requested: set[str]) -> List[str]:
        query_fields: List[str] = []

        def add_edge_fields(root: str) -> None:
            if lang:
                for l in lang:
                    query_fields.append(f"{root}.{self._norm_lang(l)}.edge")
            else:
                query_fields.append(f"{root}.*.edge")

        if "pref" in requested:
            add_edge_fields("pref")
        if "alt" in requested:
            add_edge_fields("alt")
        if "description" in requested:
            if lang:
                for l in lang:
                    query_fields.append(f"description.{self._norm_lang(l)}")
            else:
                query_fields.append("description.*")
        if "search_all" in requested:
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
            # include body for debugging
            try:
                body = e.response.text if e.response is not None else ""
            except httpx.HTTPError:
                body = ""
            logger.warning(f"[{self.identifier}] HTTP {code} during autocomplete: {e!r} {body}")
        except JSONDecodeError as e:
            logger.warning(f"[{self.identifier}] Invalid JSON during autocomplete: {e!r}")
        except ValueError as e:
            logger.warning(f"[{self.identifier}] Value error parsing autocomplete response: {e!r}")
        return None

    # -------------------------
    # Phase 3: format result
    # -------------------------
    def _format_result(
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
            items.append(self._concept_from_parts(parts, display_langs))

        total = int(data.get("hits", {}).get("total", {}).get("value", 0) or 0)
        return SearchResults(total=total, items=items)

    # -------------------------
    # Literal extraction + best label
    # -------------------------
    @classmethod
    def _dict_to_literals(  # pylint: disable=too-many-locals
            cls,
            field_name: str,
            obj: Optional[Dict[str, Any]],
            hl: Optional[Dict[str, List[str]]] = None,
            display_langs: Optional[List[str]] = None,
    ) -> Optional[List[RDFLiteral]]:
        """
        Convert {lang: [texts...]} to list[RDFLiteral].

        API stability rule:
        - if display_langs contains base tag 'en', and obj has 'en-us'/'en-gb',
          return ONE of them but expose lang='en' in the API.
        - same for 'fr' vs 'fr-ca', etc.
        - if display_langs contains region tag ('en-us'), return that exact one (lang='en-us').
        - if display_langs is None: return everything as-is.
        """
        if obj is None:
            return None

        hl = hl or {}
        out: List[RDFLiteral] = []

        # No filtering requested -> return all (keep original keys)
        if not display_langs:
            for lang_code_raw, texts in obj.items():
                if not isinstance(texts, list):
                    continue
                lang_code = cls._norm_lang(str(lang_code_raw))

                hl_key = f"{field_name}.{lang_code}"
                snippets = hl.get(hl_key)
                snippet = str(snippets[0]) if isinstance(snippets, list) and snippets else None
                snippet_source = snippet.replace("<em>", "").replace("</em>",
                                                                     "") if snippet else None

                for t in texts:
                    text = None if t is None else str(t)
                    out.append(
                        RDFLiteral(
                            text=text,
                            lang=lang_code,
                            highlight=(snippet if (
                                    snippet and snippet_source and text == snippet_source
                            ) else None),
                        )
                    )
            return out or None

        # Filtering requested: for each requested display language, pick ONE matching variant
        available = {cls._norm_lang(k): k for k in obj.keys()}  # norm -> original key
        available_norms = list(available.keys())

        def pick_variant(req: str) -> Optional[str]:
            """Return a *normalized* available language key matching req (normalized)."""
            # exact match
            if req in available:
                return req
            # base match (req='en' matches available 'en-us', 'en-gb', ...)
            if "-" not in req:
                for a in available_norms:
                    if cls._lang_base(a) == req:
                        return a
            return None

        for req_raw in display_langs:
            req = cls._norm_lang(req_raw)
            variant = pick_variant(req)
            if not variant:
                continue

            original_key = available[variant]
            texts = obj.get(original_key)
            if not isinstance(texts, list):
                continue

            # highlight lookup:
            # - If req is base ('en'), clients historically expect highlight field 'pref.en'.
            # - If req is region ('en-us'), highlight field 'pref.en-us'.
            hl_lookup_lang = req
            hl_key = f"{field_name}.{hl_lookup_lang}"

            snippets = hl.get(hl_key)
            snippet = str(snippets[0]) if isinstance(snippets, list) and snippets else None
            snippet_source = snippet.replace("<em>", "").replace("</em>", "") if snippet else None

            # expose base lang if requested base; else expose exact region tag
            exposed_lang = req

            for t in texts:
                text = None if t is None else str(t)
                out.append(
                    RDFLiteral(
                        text=text,
                        lang=exposed_lang,
                        highlight=(snippet if (
                                snippet and snippet_source and text == snippet_source) else None),
                    )
                )

        return out or None

    @classmethod
    def _choose_best_litteral(
            cls,
            pref_literals: Optional[List[RDFLiteral]],
            alt_literals: Optional[List[RDFLiteral]],
            desc_literals: Optional[List[RDFLiteral]],
            display_langs: Optional[List[str]] = None,
    ) -> Optional[BestLabel]:
        """
        Best label selection, API stable:
        - display_langs may contain base tags ('en'): match returned literals with lang 'en'
          (since _dict_to_literals exposes base tags).
        - prefer highlighted literal
        - prefer pref > alt > description
        """
        wanted = [cls._norm_lang(x) for x in display_langs] if display_langs else None

        def lang_ok(lit_lang: str) -> bool:
            if not wanted:
                return True
            # literals are already exposed as base or exact requested lang
            return cls._norm_lang(lit_lang) in wanted

        def pick_from(
                lits: Optional[List[RDFLiteral]],
                source: Literal["pref", "alt", "description"],
        ) -> Optional[BestLabel]:
            if not lits:
                return None

            candidates = [x for x in lits if lang_ok(x.lang)] if wanted else list(lits)
            if not candidates:
                candidates = list(lits)

            for lit in candidates:
                if lit.highlight:
                    return BestLabel(
                        text=lit.text,
                        lang=lit.lang,
                        highlight=lit.highlight,
                        source_field=source,
                    )

            lit0 = candidates[0]
            return BestLabel(
                text=lit0.text,
                lang=lit0.lang,
                highlight=lit0.highlight,
                source_field=source,
            )

        for source, lits in (("pref", pref_literals), ("alt", alt_literals),
                             ("description", desc_literals)):
            chosen = pick_from(lits, source)  # type: ignore[arg-type]
            if chosen:
                return chosen
        return None

    # -------------------------
    # Parse + Concept build
    # -------------------------
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
        pref_literals = self._dict_to_literals(
            "pref", parts.pref_map, parts.hl, display_langs
        )
        alt_literals = self._dict_to_literals(
            "alt", parts.alt_map, parts.hl, display_langs
        )
        desc_literals = self._dict_to_literals(
            "description", parts.desc_map, parts.hl,
            display_langs
        )

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
