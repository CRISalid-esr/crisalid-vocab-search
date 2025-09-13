""" Invalid entity error handler """
import json

from pydantic import ValidationError
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.status import HTTP_422_UNPROCESSABLE_ENTITY


async def invalid_entity_error_handler(
        _: Request,
        exc: ValidationError,
) -> JSONResponse:
    """

    :param _: request
    :param exc: validation error
    :return: json response with the validation errors
    """
    return JSONResponse(
        {"errors": json.loads(exc.json())},
        status_code=HTTP_422_UNPROCESSABLE_ENTITY,
    )
