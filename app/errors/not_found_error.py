""" Not found error handler. """

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.status import HTTP_404_NOT_FOUND


class NotFoundError(ValueError):
    """
    Conflict error
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)


async def not_found_entity_error_handler(
        _: Request,
        exc: NotFoundError,
) -> JSONResponse:
    """

    :param _: request
    :param exc: validation error
    :return: json response with the validation errors
    """
    return JSONResponse(
        {"error": str(exc)},
        status_code=HTTP_404_NOT_FOUND,
    )
