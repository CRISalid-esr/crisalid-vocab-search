import json

import httpx
import pytest
import respx
from httpx import Response

from tests.fixtures.common import os_json_data


@pytest.fixture(name="jel_autocomplete_chom_response_json")
def fixture_jel_autocomplete_chom_response_json(_base_path):
    """
    Returns the canned OpenSearch response for q='chôm'
    used by LocalOpenSearchVocabProxy.autocomplete().
    """
    return os_json_data(_base_path, "jel_autocomplete_chom_response.json")


@pytest.fixture(name="jel_autocomplete_neighborhood_response_json")
def fixture_jel_autocomplete_neighborhood_response_json(_base_path):
    """
    Returns the canned OpenSearch response for q='neighborhood'
    used by LocalOpenSearchVocabProxy.autocomplete().
    """
    return os_json_data(_base_path, "jel_autocomplete_neighborhood_response.json")


@pytest.fixture
def mock_jel_autocomplete(respx_mock: respx.MockRouter, jel_autocomplete_chom_response_json,
                          jel_autocomplete_neighborhood_response_json):
    """
    Autouse HTTP mock: intercept POST to http://localhost:9200/concepts_jel/_search
    - For q starting with "chôm", return the canned response fixture.
    - Otherwise, return an empty result set.
    """

    def responder(request: httpx.Request) -> httpx.Response:
        try:
            body = json.loads(request.content.decode("utf-8")) if request.content else {}
            q = body.get("query", {}).get("multi_match", {}).get("query")
        except Exception:  # pylint: disable=broad-except
            q = None

        if isinstance(q, str) and q.lower().startswith("chôm"):
            return Response(200, json=jel_autocomplete_chom_response_json)
        if isinstance(q, str) and q.lower().startswith("neighborhood"):
            return Response(200, json=jel_autocomplete_neighborhood_response_json)

        return Response(
            200,
            json={
                "timed_out": False,
                "took": 1,
                "hits": {"total": {"relation": "eq", "value": 0}, "max_score": 0.0, "hits": []},
                "_shards": {"total": 1, "successful": 1, "skipped": 0, "failed": 0},
            },
        )

    respx_mock.post("http://localhost:9200/concepts_jel/_search").mock(side_effect=responder)
    yield


@pytest.fixture(name="aat_autocomplete_lang_suffix_response_json")
def fixture_aat_autocomplete_lang_suffix_response_json(_base_path):
    """
    Returns the canned OpenSearch response for q='port'
    used by LocalOpenSearchVocabProxy.autocomplete().
    """
    return os_json_data(_base_path, "aat_autocomplete_lang_suffix.json")


@pytest.fixture
def mock_aat_autocomplete(
        respx_mock: respx.MockRouter,
        aat_autocomplete_lang_suffix_response_json,
):
    """
    Intercept POST to http://localhost:9200/concepts_aat/_search
    - For q starting with "port", return the canned AAT response fixture.
    - Otherwise, return empty hits.
    """

    def responder(request: httpx.Request) -> httpx.Response:
        try:
            body = json.loads(request.content.decode("utf-8")) if request.content else {}
            q = body.get("query", {}).get("multi_match", {}).get("query")
        except Exception:  # pylint: disable=broad-except
            q = None

        if isinstance(q, str) and q.lower().startswith("port"):
            return Response(200, json=aat_autocomplete_lang_suffix_response_json)

        return Response(
            200,
            json={
                "timed_out": False,
                "took": 1,
                "hits": {"total": {"relation": "eq", "value": 0}, "max_score": 0.0, "hits": []},
                "_shards": {"total": 1, "successful": 1, "skipped": 0, "failed": 0},
            },
        )

    respx_mock.post("http://localhost:9200/concepts_aat/_search").mock(side_effect=responder)
    yield
