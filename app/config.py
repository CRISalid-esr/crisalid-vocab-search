"""
Settings loading module
"""
from functools import lru_cache
from typing import Dict
import importlib

from app.settings.app_env_types import AppEnvTypes
from app.settings.app_settings import AppSettings

environments: Dict[AppEnvTypes, str] = {
    AppEnvTypes.DEV: "app.settings.development_settings.DevAppSettings",
    AppEnvTypes.PROD: "app.settings.production_settings.ProdAppSettings",
    AppEnvTypes.TEST: "app.settings.test_settings.TestAppSettings",
}

@lru_cache()
def get_app_settings() -> AppSettings:
    """
    Main entry point for settings loading

    :return: Settings fitting current environment
    """
    config_path = environments[AppSettings().app_env]
    module_name, class_name = config_path.rsplit('.', 1)
    module = importlib.import_module(module_name)
    config_class = getattr(module, class_name)
    return config_class()
