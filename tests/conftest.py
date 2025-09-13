"""Pytest configuration file"""
from os import environ

from _pytest.logging import LogCaptureFixture
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.vocab_search import VocabSearch
from tests.fixtures.common import *  # pylint: disable=unused-import, wildcard-import, unused-wildcard-import
# from tests.fixtures.concepts_fixtures import *  # pylint: disable=unused-import, wildcard-import, unused-wildcard-import
from tests.fixtures.vocab_proxies_fixtures import *  # pylint: disable=unused-import, wildcard-import, unused-wildcard-import

environ["APP_ENV"] = "TEST"


@pytest.fixture(name="test_app")
def app() -> FastAPI:
    """Provide app as fixture"""
    # pylint: disable=import-outside-toplevel

    return VocabSearch()


@pytest.fixture(name="test_client")
def fixture_test_client(test_app: FastAPI) -> TestClient:
    """Provide test client as fixture"""
    return TestClient(test_app)


@pytest.fixture(autouse=True)
def caplog(caplog: LogCaptureFixture):  # pylint: disable=redefined-outer-name
    """
    Make pytest work with loguru. See:
    https://loguru.readthedocs.io/en/stable/resources/migration.html#making-things-work-with-pytest-and-caplog
    :param caplog: pytest fixture
    :return: loguru compatible caplog
    """
    handler_id = logger.add(
        caplog.handler,
        format="{message}",
        level=0,
        filter=lambda record: record["level"].no >= caplog.handler.level,
        enqueue=False,
    )
    yield caplog
    try:
        logger.remove(handler_id)
    except ValueError:
        pass
