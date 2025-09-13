"""Tests for the VocabService class."""
import pytest

from app.models.vocabs import VocabStatus
from app.services.vocab_service import VocabService


class _FakeSettings:
    """Minimal settings stub with a vocab_config attribute."""

    def __init__(self, vocab_config):
        self.vocab_config = vocab_config


@pytest.mark.asyncio
async def test_list_vocabs_probe_false(patch_build_proxies, proxies_ok):
    """When probe=False, the service should avoid network calls and return defaults."""
    # Patch service to use our fake proxies; config content won't matter at runtime here
    patch_build_proxies(proxies_ok)

    settings = _FakeSettings({"vocabularies": []})
    svc = VocabService(settings)

    items = await svc.list_vocabs(probe=False)
    assert len(items) == 2
    by_id = {i.id: i for i in items}

    # Defaults (no probe): empty langs/count, status OK
    assert by_id["jel"].languages == []
    assert by_id["jel"].doc_count == 0
    assert by_id["jel"].status == VocabStatus.OK

    assert by_id["mesh"].languages == []
    assert by_id["mesh"].doc_count == 0
    assert by_id["mesh"].status == VocabStatus.OK


@pytest.mark.asyncio
async def test_list_vocabs_probe_true_mixed_status(patch_build_proxies, proxies_mixed, caplog):
    """With probe=True, aggregate OK and UNAVAILABLE results from proxies and log unavailable."""
    patch_build_proxies(proxies_mixed)

    settings = _FakeSettings({"vocabularies": []})
    svc = VocabService(settings)

    items = await svc.list_vocabs(probe=True)
    assert len(items) == 2
    by_id = {i.id: i for i in items}

    assert by_id["jel"].status == VocabStatus.OK
    assert by_id["jel"].languages == ["en", "fr"]
    assert by_id["jel"].doc_count == 42

    assert by_id["mesh"].status == VocabStatus.UNAVAILABLE
    assert by_id["mesh"].languages == []
    assert by_id["mesh"].doc_count == 0

    # Ensure a warning was logged for the unavailable backend
    warning_msgs = [r.message for r in caplog.records if r.levelname in ("WARNING", "ERROR")]
    assert any("simulated backend down" in m for m in warning_msgs)


def test_validate_config_or_fail_ok():
    """
    A valid config should pass validation (constructor-based proxy validation only, no network).
    """
    cfg = {
        "vocabularies": [
            {
                "id": "jel", "type": "local_os",
                "config": {"host": "http://localhost", "port": 9200}
            },
            {"id": "mesh", "type": "local_os",
             "config": {"host": "http://localhost", "port": 9201}},
        ]
    }
    settings = _FakeSettings(cfg)
    # should not raise
    VocabService.validate_config_or_fail(settings)


def test_validate_config_or_fail_duplicate_id_raises():
    """Duplicate vocabulary ids must raise at validation time."""
    cfg = {
        "vocabularies": [
            {"id": "jel", "type": "local_os", "config": {"host": "http://localhost", "port": 9200}},
            {"id": "jel", "type": "local_os", "config": {"host": "http://localhost", "port": 9201}},
        ]
    }
    settings = _FakeSettings(cfg)

    with pytest.raises(RuntimeError):
        VocabService.validate_config_or_fail(settings)
