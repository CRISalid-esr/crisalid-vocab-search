""" Person routes"""

from fastapi import APIRouter

router = APIRouter()

tags_metadata = [
    {
        "name": "search",
        "description": "Search for concepts in controlled vocabularies.",
    }
]
