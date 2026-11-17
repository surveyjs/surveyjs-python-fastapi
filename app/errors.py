"""The same error shape on every platform: under /api every error is JSON { error } with its HTTP status,
including FastAPI's and Starlette's own answers. FastAPI would write { "detail": … } and answer a bad
parameter with 422 { "detail": [...] }. Outside /api a short HTML page says what went wrong.

Handlers signal errors the usual FastAPI way: raise HTTPException(403, "…") or return a JSONResponse.
"""

import html
import logging
from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.routing import Match

log = logging.getLogger("app")

MESSAGES = {
    400: "Bad request", 401: "Unauthorized", 403: "Forbidden", 404: "Not found", 405: "Method not allowed",
    413: "The request body is too large", 415: "Unsupported media type", 422: "Unprocessable content",
    429: "Too many requests", 500: "Internal server error",
}


def _is_api(request: Request) -> bool:
    return request.url.path.startswith("/api/")


def _message(status: int, detail: object) -> str:
    """The handler's own text, or the contract's wording for a plain status phrase ("Not Found")."""
    phrase = HTTPStatus(status).phrase if status in HTTPStatus._value2member_map_ else ""
    if isinstance(detail, str) and detail and detail != phrase:
        return detail
    return MESSAGES.get(status, phrase or "Error")


def _allowed_methods(request: Request) -> str:
    """Every method the app answers on this path, for the 405's Allow header. Starlette names only the methods of
    the first route that matched, and each method here is its own route, often in another router."""
    allowed = []
    for method in ("DELETE", "GET", "PATCH", "POST", "PUT"):
        scope = {"type": "http", "path": request.url.path, "method": method, "root_path": "", "headers": [], "query_string": b""}
        if any(route.matches(scope)[0] == Match.FULL for route in request.app.router.routes):
            allowed.append(method)
    return ", ".join(allowed)


def _page(status: int, text: str) -> HTMLResponse:
    body = f'<!DOCTYPE html><html lang="en"><meta charset="utf-8"><title>{status}</title><p>{html.escape(text)}</p></html>'
    return HTMLResponse(body, status_code=status)


async def http_error(request: Request, exc: StarletteHTTPException) -> Response:
    headers = dict(exc.headers or {})
    if exc.status_code == 405:
        headers["Allow"] = _allowed_methods(request) or headers.get("Allow", "")
    if not _is_api(request):
        return _page(exc.status_code, _message(exc.status_code, exc.detail))
    return JSONResponse({"error": _message(exc.status_code, exc.detail)}, status_code=exc.status_code, headers=headers)


async def validation_error(request: Request, exc: RequestValidationError) -> Response:
    """A path or query parameter of the wrong type (limit=abc, /api/claims/abc/pdf): the client's mistake, 400."""
    first = exc.errors()[0] if exc.errors() else {}
    where = ".".join(str(part) for part in first.get("loc", ())[1:]) or "request"
    message = f"Invalid {where}: {first.get('msg', 'invalid value')}"
    if not _is_api(request):
        return _page(400, message)
    return JSONResponse({"error": message}, status_code=400)


async def server_error(request: Request, exc: Exception) -> Response:
    """Anything a handler didn't expect: log it with its traceback, answer 500 without details."""
    log.error("Unhandled error on %s %s", request.method, request.url.path, exc_info=exc)
    if not _is_api(request):
        return _page(500, MESSAGES[500])
    return JSONResponse({"error": MESSAGES[500]}, status_code=500)


def install(app: FastAPI) -> None:
    # StarletteHTTPException, not FastAPI's subclass: the router's own 404 and 405 are Starlette's
    app.add_exception_handler(StarletteHTTPException, http_error)
    app.add_exception_handler(RequestValidationError, validation_error)
    app.add_exception_handler(Exception, server_error)
