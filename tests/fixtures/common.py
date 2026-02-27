"""Common fixtures and helper functions for tests."""
import json
import pathlib

import pytest


@pytest.fixture(name="_base_path")
def fixture_base_path() -> pathlib.Path:
    """Get the current folder of the test"""
    return pathlib.Path(__file__).parent.parent


def _json_data_from_file(base_path, file_path) -> dict:
    file = pathlib.Path(base_path / file_path)
    with open(file, encoding="utf-8") as json_file:
        input_data = json_file.read()
    return json.loads(input_data)


def os_json_data(base_path, filename: str) -> dict:
    """
    Load a JSON file from tests/fixtures/data/os/<filename>.
    """
    return _json_data_from_file(base_path, f"fixtures/data/os/{filename}")
