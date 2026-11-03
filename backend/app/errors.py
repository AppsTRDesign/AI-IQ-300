"""Coded application errors. The API returns {"code", "message"}; the UI translates the code (err_<code> in
languages/*.json) and falls back to the English message, so every error is shown in the user's language."""
from __future__ import annotations

from fastapi import HTTPException


class AppError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def fail(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status, {"code": code, "message": message})


def to_http(e: Exception, status: int = 400) -> HTTPException:
    """Wrap any error for the API, keeping its code when it has one."""
    code = getattr(e, "code", None)
    if isinstance(e, PermissionError):
        status, code = 403, code or "path_escape"
    return HTTPException(status, {"code": code or "error", "message": str(e)})
