"""Common fixtures and helper functions for tests."""
import json
import pathlib

import pytest

# from app.models.concepts import Concept


@pytest.fixture(name="_base_path")
def fixture_base_path() -> pathlib.Path:
    """Get the current folder of the test"""
    return pathlib.Path(__file__).parent.parent


def _json_data_from_file(base_path, file_path) -> dict:
    file = pathlib.Path(base_path / file_path)
    with open(file, encoding="utf-8") as json_file:
        input_data = json_file.read()
    return json.loads(input_data)


# def _concept_json_data_from_file(base_path, concept) -> dict:
#     file_path = f"data/concepts/{concept}.json"
#     return _json_data_from_file(base_path, file_path)
#
#
# def _concept_from_json_data(input_data: dict) -> Concept:
#     return Concept(**input_data)
