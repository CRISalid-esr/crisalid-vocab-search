"""
App settings base class
"""
import logging
import os
from typing import ClassVar, TextIO

import yaml
from pydantic_settings import BaseSettings

from app.settings.app_env_types import AppEnvTypes


class AppSettings(BaseSettings):
    """
    App settings main class with parameters definition
    """

    @staticmethod
    def settings_file_path(filename: str) -> str:
        """
        Get the path of a settings file

        :param filename: The name of the settings file
        :return: The path of the settings file
        """
        return os.path.join(
            os.path.abspath(os.path.dirname(__file__)), "..", "..", filename
        )

    @staticmethod
    def dct_from_yml(yml_file: str) -> dict:
        """
        Load settings from yml file
        """
        with open(yml_file, encoding="utf8") as file:
            return yaml.load(file, Loader=yaml.FullLoader)

    app_env: AppEnvTypes = AppEnvTypes.PROD
    debug: bool = False
    logging_level: int = logging.INFO
    loguru_level: str = "INFO"
    logger_sink: ClassVar[str | TextIO] = "logs/app.log"

    api_prefix: str = "/api"
    api_version: str = "v0"

    git_commit: str = "-"
    git_branch: str = "-"
    docker_digest: str = "-"

    vocab_config_file: str = settings_file_path(
        filename="vocab_config.yaml")
    vocab_config: dict = dct_from_yml(yml_file=vocab_config_file)
