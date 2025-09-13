import json

import httpx
import pytest
from httpx import Response

from app.services.proxies.local_opensearch import LocalOpenSearchVocabProxy


@pytest.mark.asyncio
async def test_local_os_proxy_autocomplete_chom_highlights_and_literals(
        mock_jel_autocomplete  # pylint: disable=unused-argument
):
    """Test autocomplete with 'chôm' query, expecting highlights and literals in FR."""
    proxy = LocalOpenSearchVocabProxy(
        identifier="jel",
        cfg={"host": "http://localhost", "port": 9200},
    )

    async with httpx.AsyncClient() as client:
        result = await proxy.autocomplete(
            client,
            q="chôm",  # will hit the autouse mock
            lang=["fr"],
            fields=["pref", "alt"],
            display_langs=["fr"],
            display_fields=None,
            limit=20,
            offset=0,
            highlight=True,
            broader="ids",
            narrower="ids",
            broader_depth=1,
            narrower_depth=1,
        )

    # total from the mocked payload
    assert result.total == 3
    assert len(result.items) == 3

    # Ensure we have highlights on best_label for at least one hit
    assert any(
        it.best_label
        and it.best_label.highlight and "em>chômage" in it.best_label.highlight.lower()
        for it in result.items
    )

    # Check one known IRI and that pref literal carries highlight on the first FR literal
    target = next((it for it in result.items if it.iri.endswith("#J64")), None)
    assert target is not None, "Expected #J64 in mocked hits"

    # pref literals exist and include a FR literal with highlight
    fr_pref = [lit for lit in (target.pref or []) if lit.lang == "fr"]
    assert fr_pref, "Expected FR pref literal"
    assert fr_pref[0].text.startswith("J64 - Chômage")
    assert fr_pref[0].lang == "fr"
    assert fr_pref[0].highlight is not None
    assert "chômage" in fr_pref[0].highlight.lower()


@pytest.mark.asyncio
async def test_local_os_proxy_autocomplete_payload(http_mock):
    """Test that the payload sent to OS matches exactly what we expect."""
    # proxy + mocked endpoint with any hits, as we only check the payload sent to OS
    proxy = LocalOpenSearchVocabProxy(
        identifier="jel",
        cfg={"host": "http://localhost", "port": 9200},
    )

    route = http_mock.post("http://localhost:9200/concepts/_search").mock(
        return_value=Response(
            200,
            json={
                "timed_out": False,
                "took": 1,
                "_shards": {"total": 1, "successful": 1, "skipped": 0, "failed": 0},
                "hits": {"total": {"relation": "eq", "value": 0}, "max_score": 0.0, "hits": []},
            },
        )
    )

    # Act: call autocomplete with the specified args
    async with httpx.AsyncClient() as client:
        await proxy.autocomplete(
            client=client,
            q="commer",
            lang=["fr", "en", "es"],
            fields=["pref", "description"],
            display_langs=["fr", "en"],
            display_fields=["pref", "alt", "description"],
            limit=50,
            offset=0,
            highlight=True,
            broader="ids",
            narrower="ids",
            broader_depth=1,
            narrower_depth=1,
        )

    # Assert: endpoint hit once and payload matches exactly
    assert route.called, "Expected OS endpoint to be called"
    assert len(route.calls) == 1

    sent = json.loads(route.calls[0].request.content.decode("utf-8"))
    expected = {
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
        "from": 0,
        "highlight": {
            "fields": {
                "alt.en": {"number_of_fragments": 0},
                "alt.fr": {"number_of_fragments": 0},
                "description.en": {"number_of_fragments": 0},
                "description.fr": {"number_of_fragments": 0},
                "pref.en": {"number_of_fragments": 0},
                "pref.fr": {"number_of_fragments": 0},
            },
            "require_field_match": False,
        },
        "query": {
            "multi_match": {
                "analyzer": "fold",
                "fields": [
                    "pref.fr.edge",
                    "pref.en.edge",
                    "pref.es.edge",
                    "description.fr",
                    "description.en",
                    "description.es",
                ],
                "query": "commer",
                "type": "bool_prefix",
            }
        },
        "size": 50,
        "track_total_hits": True,
    }

    assert sent == expected
