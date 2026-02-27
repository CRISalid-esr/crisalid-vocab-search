"""Main application module, defining the FastAPI app and its configuration."""
import sys

from fastapi import FastAPI
from loguru import logger
from pydantic import ValidationError

from app.config import get_app_settings
from app.errors.not_found_error import not_found_entity_error_handler, NotFoundError
from app.errors.validation_error import invalid_entity_error_handler
from app.routes.api import router as api_router
from app.routes.healthness import router as healthness_router
from app.settings.app_env_types import AppEnvTypes


class VocabSearch(FastAPI):
    """Main application, routing logic, middlewares and startup/shutdown events"""

    def __init__(self):
        super().__init__()
        settings = get_app_settings()

        self.include_router(
            api_router, prefix=f"{settings.api_prefix}/{settings.api_version}"
        )

        self.include_router(healthness_router, prefix="/health")

        if settings.app_env != AppEnvTypes.TEST:
            logger.remove()
            logger.add(
                settings.logger_sink,
                level=settings.loguru_level,
                **({"rotation": "100 MB"} if settings.logger_sink != sys.stderr else {}),
            )

        self.add_exception_handler(NotFoundError, not_found_entity_error_handler)
        self.add_exception_handler(ValidationError, invalid_entity_error_handler)
