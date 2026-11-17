"""Calls the SurveyJS service (SurveyJS Server, SURVEYJS_SERVICE_URL) for Run Server-Side Workflows:
validate-response validates, lint-definition lints, server-pdf prints a PDF and extract-from-paper
extracts. It turns what isn't an answer (a timeout, a refused connection) into the same { error } on
every platform, so the routes only match the answers they recognize. When you copy one of those
examples, copy this file too.

httpx2 doesn't raise on 4xx or 5xx, and the service answers some errors with 200 { error }: a status
alone never means success, so each route compares the answer itself (fail closed).
"""

import logging
from typing import Annotated, Any, NoReturn

import httpx2
from fastapi import Depends, HTTPException
from starlette.requests import HTTPConnection

from app.integration.stored_json import dumps

log = logging.getLogger("app.surveyjs")


class SurveyJsService:
    def __init__(self, http: httpx2.AsyncClient, base_url: str) -> None:
        self.http = http
        self.base_url = base_url.rstrip("/")

    async def post(self, path: str, body: Any, timeout: float) -> httpx2.Response:
        """POST JSON to the service and return its answer, whatever the status. When nothing answers, the
        request ends here: 504 when the service timed out, 503 when it isn't running."""
        try:
            return await self.http.post(
                self.base_url + path,
                content=dumps(body).encode(),   # 1.0 stays 1.0, "naïve" stays readable
                headers={"Content-Type": "application/json"},
                timeout=httpx2.Timeout(timeout),
            )
        except httpx2.TimeoutException:
            log.error("SurveyJS service: %s timed out after %s s", path, timeout)
            raise HTTPException(504, "SurveyJS service timed out") from None
        except httpx2.ConnectError:
            log.error("SurveyJS service: nothing answers at %s", self.base_url)
            raise HTTPException(503, f"SurveyJS service is not running at {self.base_url}") from None
        except httpx2.TransportError as error:   # the connection broke mid-answer
            log.error("SurveyJS service: %s failed: %s", path, type(error).__name__)
            raise HTTPException(502, "SurveyJS service error") from None

    @staticmethod
    def unexpected(path: str, answer: httpx2.Response, message: str = "SurveyJS service error", *,
                   log_body: bool = True) -> NoReturn:
        """An answer the route doesn't recognize: log it and end the request with 502 { error }. Extraction
        answers are logged by status only, never by body: it may hold the answers written on the form."""
        if log_body:
            log.error("SurveyJS service: unexpected answer from %s: %s %s", path, answer.status_code, answer.text[:2000])
        else:
            log.error("SurveyJS service: unexpected answer from %s: %s", path, answer.status_code)
        raise HTTPException(502, message)


def get_surveyjs_service(conn: HTTPConnection) -> SurveyJsService:
    return SurveyJsService(conn.app.state.http, conn.app.state.settings.surveyjs_service_url)


SurveyJs = Annotated[SurveyJsService, Depends(get_surveyjs_service)]
"""The SurveyJS service client. Tests replace get_surveyjs_service through app.dependency_overrides."""
