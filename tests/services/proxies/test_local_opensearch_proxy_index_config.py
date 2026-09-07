"""Tests for the index name derivation and override of LocalOpenSearchVocabProxy."""
import httpx
import pytest
from httpx import Response

from app.services.proxies.local_opensearch import LocalOpenSearchVocabProxy

_EMPTY_OS_RESPONSE = {
    "timed_out": False,
    "took": 1,
    "_shards": {"total": 1, "successful": 1, "skipped": 0, "failed": 0},
    "hits": {"total": {"relation": "eq", "value": 0}, "max_score": 0.0, "hits": []},
}


async def _autocomplete(proxy: LocalOpenSearchVocabProxy) -> None:
    async with httpx.AsyncClient() as client:
        await proxy.autocomplete(
            client=client,
            q="test",
            lang=None,
            fields=None,
            display_langs=None,
            display_fields=None,
            limit=10,
            offset=0,
            highlight=False,
            broader="ids",
            narrower="ids",
            broader_depth=1,
            narrower_depth=1,
        )


@pytest.mark.asyncio
async def test_index_name_derived_from_identifier(http_mock):
    """Without an 'index' key, the proxy targets concepts_<identifier>."""
    proxy = LocalOpenSearchVocabProxy(
        identifier="jel",
        cfg={"host": "http://localhost", "port": 9200},
    )

    route = http_mock.post("http://localhost:9200/concepts_jel/_search").mock(
        return_value=Response(200, json=_EMPTY_OS_RESPONSE)
    )

    await _autocomplete(proxy)

    assert route.called, "Expected the derived concepts_jel index to be queried"


@pytest.mark.asyncio
async def test_index_name_override_from_config(http_mock):
    """An explicit 'index' key in the config overrides the derived index name."""
    proxy = LocalOpenSearchVocabProxy(
        identifier="jel",
        cfg={"host": "http://localhost", "port": 9200, "index": "custom_concepts"},
    )

    route = http_mock.post("http://localhost:9200/custom_concepts/_search").mock(
        return_value=Response(200, json=_EMPTY_OS_RESPONSE)
    )

    await _autocomplete(proxy)

    assert route.called, "Expected the overridden index to be queried"


@pytest.mark.asyncio
async def test_probe_uses_derived_index(http_mock):
    """probe() must target the same derived index as autocomplete()."""
    proxy = LocalOpenSearchVocabProxy(
        identifier="aat",
        cfg={"host": "http://localhost", "port": 9200},
    )

    route = http_mock.post("http://localhost:9200/concepts_aat/_search").mock(
        return_value=Response(
            200,
            json={
                "hits": {"total": {"relation": "eq", "value": 7}},
                "aggregations": {"langs": {"buckets": [{"key": "en"}, {"key": "fr"}]}},
            },
        )
    )

    async with httpx.AsyncClient() as client:
        item = await proxy.probe(client)

    assert route.called
    assert item.doc_count == 7
    assert item.languages == ["en", "fr"]


def test_invalid_index_config_raises():
    """A non-string or empty 'index' key must fail validation."""
    with pytest.raises(ValueError):
        LocalOpenSearchVocabProxy(
            identifier="jel",
            cfg={"host": "http://localhost", "port": 9200, "index": ""},
        )
    with pytest.raises(ValueError):
        LocalOpenSearchVocabProxy(
            identifier="jel",
            cfg={"host": "http://localhost", "port": 9200, "index": 42},
        )
