from __future__ import annotations

from typing import List, Optional, Union, Literal

from pydantic import BaseModel, Field, ConfigDict, field_validator


# ---------- RDF-like literal ----------

class RDFLiteral(BaseModel):
    """
    Minimal RDF-like literal for labels/descriptions.
    """
    text: Optional[str] = None
    lang: Optional[str] = None
    highlight: Optional[str] = None

    model_config = ConfigDict(extra="ignore")


class BestLabel(RDFLiteral):
    """
    Best display label selected by the API.
    """
    source_field: Literal["pref", "alt", "description", "search_all"]


# ---------- Main models ----------

class Concept(BaseModel):
    """
    Full concept model for /search and /autocomplete.

    - 'pref' | 'alt' | 'description': List[RDFLiteral]
    - 'best_label': BestLabel (RDFLiteral + source_field)
    - 'broader' / 'narrower': List[str | Concept]
    """
    model_config = ConfigDict(extra="ignore")

    # Identity & provenance
    iri: str = Field(..., description="Concept IRI (global identifier)")
    scheme: Optional[str] = None
    vocab: Optional[str] = None
    identifier: Optional[str] = None
    top_concept: Optional[bool] = None
    lang_set: Optional[List[str]] = None

    # Scoring & display helpers
    score: Optional[float] = None
    best_label: Optional[BestLabel] = None

    # Multilingual fields
    pref: Optional[List[RDFLiteral]] = None
    alt: Optional[List[RDFLiteral]] = None
    description: Optional[List[RDFLiteral]] = None

    # Relations
    broader: List[Union[str, "Concept"]] = Field(default_factory=list)
    narrower: List[Union[str, "Concept"]] = Field(default_factory=list)

    @field_validator("lang_set", mode="before")
    @classmethod
    def _dedup_lang_set(cls, v: Optional[List[str]]):
        if v is None:
            return v
        return list(set(v))


class SearchResults(BaseModel):
    """
    Search results for /search and /autocomplete.
    """
    total: int
    items: List[Concept]
