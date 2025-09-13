"""Vocab routes"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.encoders import jsonable_encoder
from starlette import status
from starlette.responses import JSONResponse

from app.config import get_app_settings
from app.services.vocab_service import VocabService
from app.settings.app_settings import AppSettings

router = APIRouter(tags=["vocabs"])

tags_metadata = [
    {
        "name": "vocabs",
        "description": "Lists of controlled vocabularies.",
    }
]


@router.get(
    "/vocabs",
    summary="List available vocabularies",
)
async def list_vocabs(
        settings: Annotated[AppSettings, Depends(get_app_settings)],
        probe: bool = Query(
            default=True,
            description="If true, probe each backend to check availability "
                        "and populate languages and doc_count.",
        ),
) -> JSONResponse:
    """
    List available vocabularies

    :param settings: AppSettings dependency
    :param probe: Whether to probe each backend to populate languages and doc_count.
    :return: JSONResponse with list of vocabularies
    """
    service = VocabService(settings)
    items = await service.list_vocabs(probe=probe)
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=jsonable_encoder({"items": items}),
    )
