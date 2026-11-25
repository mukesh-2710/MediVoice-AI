"""Centralised exception handling: clients get stable JSON, never stack traces."""
from __future__ import annotations

import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

log = logging.getLogger("medivoice.http")


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str):
        self.status, self.code, self.message = status, code, message


def install(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError):
        return JSONResponse({"error": {"code": exc.code, "message": exc.message}}, status_code=exc.status)

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        rid = uuid.uuid4().hex[:8]
        log.exception("unhandled error request_id=%s path=%s", rid, request.url.path)
        return JSONResponse({"error": {"code": "internal_error", "message": "Unexpected server error.", "request_id": rid}},
                            status_code=500)
