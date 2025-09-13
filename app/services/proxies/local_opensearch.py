""" Local OpenSearch-backed vocabulary proxy """
from __future__ import annotations

from json import JSONDecodeError
from typing import List

import httpx
from loguru import logger

from app.models.vocabs import Vocabulary, VocabStatus
from app.services.proxies.base import VocabProxy


class LocalOpenSearchVocabProxy(VocabProxy):
    """
    Local OpenSearch-backed vocabulary proxy
    Config format:
      config:
        host: http://localhost
        port: 9200
    """

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
