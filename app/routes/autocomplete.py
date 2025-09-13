""" Autocomplete routes"""

from __future__ import annotations

from typing import Annotated, Optional, Literal, List

from fastapi import APIRouter, Depends, Query, HTTPException

from app.config import get_app_settings
from app.models.concepts import SearchResults
from app.services.vocab_service import VocabService
from app.settings.app_settings import AppSettings
from app.utils.parameters import csv_to_list

router = APIRouter(tags=["autocomplete"])

tags_metadata = [
    {
        "name": "autocomplete",
        "description": "Concept suggestion for autocompletion fields.",
    }
]


@router.get(
    "/",
    name="autocomplete",
    summary="Prefix search for type-ahead UIs (same response shape as /search).",
    response_model=SearchResults,
)
async def autocomplete(
        # pylint: disable=too-many-arguments, too-many-locals, too-many-positional-arguments
        settings: Annotated[AppSettings, Depends(get_app_settings)],
        q: str = Query(..., description="Search string (treated as a prefix)"),
        vocabs: Optional[str] = Query(
            None, description='Comma-separated vocabulary IDs, e.g. "jel,mesh".'
        ),
        lang: Optional[str] = Query(
            None, description='Comma-separated languages, e.g. "fr,en".'
        ),
        fields: Optional[str] = Query(
            None,
            description='Comma-separated search fields. '
                        'Defaults: "pref,alt,description,search_all".',
        ),
        display_langs: Optional[str] = Query(
            None, description='Comma-separated response languages, e.g. "fr,en".'
        ),
        display_fields: Optional[str] = Query(
            None, description="Comma-separated response fields; default: all."
        ),
        limit: int = Query(20, ge=1, le=100, description="Page size (default 20, max 100)."),
        offset: int = Query(0, ge=0, description="Result offset for pagination (default 0)."),
        highlight: bool = Query(False, description="Include highlights (default: false)."),
        broader: Literal["ids", "full"] = Query(
            "ids", description='Return broader as "ids" or "full".'
        ),
        narrower: Literal["ids", "full"] = Query(
            "ids", description='Return narrower as "ids" or "full".'
        ),
        broader_depth: int = Query(
            1, description="Broader traversal depth (default 1, -1 for all)."
        ),
        narrower_depth: int = Query(
            1, description="Narrower traversal depth (default 1, -1 for all)."
        ),
) -> SearchResults:
    """
    Autocomplete endpoint for vocabularies.
    :param settings:
    :param q:
    :param vocabs:
    :param lang:
    :param fields:
    :param display_langs:
    :param display_fields:
    :param limit:
    :param offset:
    :param highlight:
    :param broader:
    :param narrower:
    :param broader_depth:
    :param narrower_depth:
    :return:
    """
    service = VocabService(settings)

    # Normalize CSV params to lists here (as requested)
    vocabs_list: Optional[List[str]] = csv_to_list(vocabs)
    lang_list: Optional[List[str]] = csv_to_list(lang)
    fields_list: Optional[List[str]] = csv_to_list(fields)
    display_langs_list: Optional[List[str]] = csv_to_list(display_langs)
    display_fields_list: Optional[List[str]] = csv_to_list(display_fields)

    try:
        return await service.autocomplete(
            q=q,
            vocabs=vocabs_list,
            lang=lang_list,
            fields=fields_list,
            display_langs=display_langs_list,
            display_fields=display_fields_list,
            limit=limit,
            offset=offset,
            highlight=highlight,
            broader=broader,
            narrower=narrower,
            broader_depth=broader_depth,
            narrower_depth=narrower_depth,
        )
    except AttributeError as e:
        raise HTTPException(status_code=400, detail="Invalid autocomplete parameters") from e
    except NotImplementedError as e:
        raise HTTPException(status_code=501, detail="autocomplete not implemented") from e
