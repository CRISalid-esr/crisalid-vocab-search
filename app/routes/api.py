"""
API redirection router
"""

from fastapi import APIRouter

from app.routes import vocabs, search

router = APIRouter()
# router.include_router(autocomplete.router, tags=["autocomplete"], prefix="/autocomplete")
router.include_router(vocabs.router, tags=["vocabs"], prefix="/vocabs")
router.include_router(search.router, tags=["search"], prefix="/search")
