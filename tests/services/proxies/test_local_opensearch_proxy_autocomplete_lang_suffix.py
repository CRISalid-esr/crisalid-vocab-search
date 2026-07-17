import httpx
import pytest

from app.services.proxies.local_opensearch import LocalOpenSearchVocabProxy


@pytest.mark.asyncio
async def test_local_os_proxy_autocomplete_accepts_lang_suffixes_in_display_langs(
    mock_aat_autocomplete,  # pylint: disable=unused-argument
):
    """
    display_langs=['en'] must accept en-us/en-gb (take any),
    and best_label must also be computed accordingly.
    """
    proxy = LocalOpenSearchVocabProxy(
        identifier="aat",
        cfg={"host": "http://localhost", "port": 9200},
    )

    async with httpx.AsyncClient() as client:
        result = await proxy.autocomplete(
            client=client,
            q="port",
            lang=None,                    # query all langs
            fields=["pref", "alt"],
            display_langs=["en"],         # base language only
            display_fields=None,
            limit=2,
            offset=0,
            highlight=False,
            broader="ids",
            narrower="ids",
            broader_depth=1,
            narrower_depth=1,
        )

    assert result.total == 525
    assert len(result.items) == 2

    concept = next((it for it in result.items if it.iri.endswith("/300004145")), None)
    assert concept is not None, "Expected AAT 300004145 in hits"

    # With display_langs=['en'], we must still return an english pref literal
    # even if only en-us/en-gb exist in the document.
    assert concept.pref is not None, "Expected pref literals to be present"
    en_prefs = [lit for lit in concept.pref if lit.lang in ("en-us", "en-gb", "en")]
    assert en_prefs, "Expected at least one english pref literal (en-us/en-gb accepted for 'en')"

    # best_label should be english too (take any matching variant)
    assert concept.best_label is not None, "Expected best_label to be computed"
    assert concept.best_label.lang in ("en-us", "en-gb", "en")

    # and text should be one of the english pref labels from fixture
    assert concept.best_label.text in ("porticoes", "porticos (spaces)")

@pytest.mark.asyncio
async def test_local_os_proxy_autocomplete_display_langs_fr_does_not_match_en_variants(
    mock_aat_autocomplete,  # pylint: disable=unused-argument
):
    proxy = LocalOpenSearchVocabProxy(
        identifier="aat",
        cfg={"host": "http://localhost", "port": 9200},
    )

    async with httpx.AsyncClient() as client:
        result = await proxy.autocomplete(
            client=client,
            q="port",
            lang=None,
            fields=["pref", "alt"],
            display_langs=["fr"],
            display_fields=None,
            limit=2,
            offset=0,
            highlight=False,
            broader="ids",
            narrower="ids",
            broader_depth=1,
            narrower_depth=1,
        )

    concept = next((it for it in result.items if it.iri.endswith("/300004145")), None)
    assert concept is not None
    assert concept.pref is None, "No fr label exists in fixture, pref should be filtered out"