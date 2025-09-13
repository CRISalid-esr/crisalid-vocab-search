"""Tests for the Vocabulary model."""
import pytest
from pydantic import ValidationError

from app.models.vocabs import Vocabulary


def test_vocab_item_minimal_defaults():
    """Test creating a Vocabulary item with only the required id field."""
    item = Vocabulary(identifier="jel")
    assert item.identifier == "jel"
    assert item.languages == []
    assert item.doc_count == 0

    d = item.model_dump()
    assert d["identifier"] == "jel"
    assert d["languages"] == []
    assert d["doc_count"] == 0


def test_vocab_item_full_values():
    """Test creating a Vocabulary item with all fields set."""
    item = Vocabulary(
        identifier="mesh",
        languages=["en", "fr", "de"],
        doc_count=1234,
    )
    assert item.identifier == "mesh"
    assert item.languages == ["en", "fr", "de"]
    assert item.doc_count == 1234

    d = item.model_dump()
    assert d == {
        "identifier": "mesh",
        "languages": ["en", "fr", "de"],
        "doc_count": 1234,
        'status': 'ok',
    }


def test_vocab_item_id_required():
    """Test that creating a Vocabulary item without an id raises ValidationError."""
    with pytest.raises(ValidationError):
        Vocabulary()  # type: ignore[call-arg]
