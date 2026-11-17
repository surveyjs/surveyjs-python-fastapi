"""The app's one outbound HTTP client, created in the lifespan (app/main.py) and closed at shutdown, so
connections to the SurveyJS service, the AI provider and restcountries.com are reused. Async: a request
that waits on one of them doesn't stop the app from serving anyone else."""

from typing import Annotated

import httpx2
from fastapi import Depends
from starlette.requests import HTTPConnection


def get_http_client(conn: HTTPConnection) -> httpx2.AsyncClient:
    return conn.app.state.http


HttpClient = Annotated[httpx2.AsyncClient, Depends(get_http_client)]
