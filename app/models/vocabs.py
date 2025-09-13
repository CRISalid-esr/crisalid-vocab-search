"""Models for vocabulary information"""
from __future__ import annotations

from enum import Enum
from typing import List

from pydantic import BaseModel, Field


class VocabStatus(str, Enum):
    """Vocabulary backend status"""
    OK = "ok"
    UNAVAILABLE = "unavailable"


class Vocabulary(BaseModel):
    """Item returned by /vocabs"""
    identifier: str = Field(..., description="Vocabulary identifier (e.g., 'jel')")
    languages: List[str] = Field(
        default_factory=list,
        description="Languages available in this index (e.g., ['fr','en'])")
    doc_count: int = Field(
        default=0, description="Number of documents in the 'concepts' index")
    status: VocabStatus = Field(
        default=VocabStatus.OK, description="Backend availability status")
