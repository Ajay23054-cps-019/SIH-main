"""Consistent structured error responses.

Every failure — raised AppError, HTTPException, validation error, or an
unexpected crash — leaves through the same envelope:
``{"data": null, "meta": {...}, "errors": [{"code", "detail"}]}``.
"""
from __future__ import annotations

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.api.models import envelope, utc_now


class AppError(Exception):
    """An expected, explainable failure with an HTTP status."""

    status_code = 400
    code = "bad_request"

    def __init__(self, detail: str, status_code: Optional[int] = None,
                 code: Optional[str] = None):
        super().__init__(detail)
        self.detail = detail
        if status_code is not None:
            self.status_code = status_code
        if code is not None:
            self.code = code


class NotFound(AppError):
    status_code = 404
    code = "not_found"


def _error_response(status_code: int, code: str, detail: str) \
        -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=envelope(
            data=None,
            meta={"generated_at": utc_now()},
            errors=[{"code": code, "detail": detail}],
        ),
    )


def install_error_handlers(app) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError):
        return _error_response(exc.status_code, exc.code, exc.detail)

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(request: Request,
                                    exc: StarletteHTTPException):
        return _error_response(exc.status_code, "http_error",
                               str(exc.detail))

    @app.exception_handler(RequestValidationError)
    async def handle_validation(request: Request,
                                exc: RequestValidationError):
        return _error_response(
            422, "validation_error",
            "; ".join(f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}"
                      for e in exc.errors()))

    @app.exception_handler(Exception)
    async def handle_unexpected(request: Request, exc: Exception):
        return _error_response(
            500, "internal_error",
            f"unexpected failure: {type(exc).__name__}: {exc}")
