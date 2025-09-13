"""
Settings for test environment
"""
import logging
import os
import sys
from typing import ClassVar

from pydantic_settings import SettingsConfigDict
from pyparsing import TextIO

from app.settings.app_settings import AppSettings


class TestAppSettings(AppSettings):
    """
    Settings for test environment
    """

    @staticmethod
    def test_settings_file_path(filename: str) -> str:
        """
        Get the path of a settings file in the tests directory
        (override the method in the parent class)

        :param filename: The name of the settings file
        :return: The path of the settings file in the tests directory
        """
        return os.path.join(
            os.path.abspath(os.path.dirname(__file__)), "..", "..", "tests", filename
        )

    __test__ = False

    debug: bool = True

    logging_level: int = logging.DEBUG

    loguru_level: str = "DEBUG"

    logger_sink: ClassVar[str | TextIO] = sys.stderr

    model_config = SettingsConfigDict(env_file=".test.env", extra="ignore")

    vocab_config_file: str = test_settings_file_path(
        filename="vocab_config.yaml")
    vocab_config: dict = AppSettings.dct_from_yml(yml_file=vocab_config_file)
