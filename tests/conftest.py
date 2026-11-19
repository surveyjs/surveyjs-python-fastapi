"""Shared test setup: a temporary DATA_DIR per test module, a seeded database, and TestClient(create_app(settings)).

Every test builds its Settings explicitly, so neither settings.env, .env nor the shell's environment changes
what runs.
"""

import sys

if sys.version_info < (3, 14):
    print(f"Python 3.14 or newer is required (this is {sys.version.split()[0]})", file=sys.stderr)
    raise SystemExit(1)

import json
import re
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.settings import Settings

CLOSED_PORT_URL = "http://127.0.0.1:9"   # nothing listens on the discard port: the service "isn't running"


def make_settings(data_dir: Path, **overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "data_dir": data_dir, "app_port": 8000, "app_host": "127.0.0.1",
        "surveyjs_service_url": CLOSED_PORT_URL, "validate_responses": False, "lint_definitions": False,
        "demo_mode": False, "relay_url": None, "edit_relay_url": None, "surveyjs_license_key": None,
        "ai_base_url": "http://127.0.0.1:9/v1", "ai_api_key": None, "ai_model": "stub",
        "surveyjs_ai_provider": None, "surveyjs_ai_model": None, "surveyjs_ollama_base_url": None,
        "openai_api_key": None, "anthropic_api_key": None, "surveyjs_build": None,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


class Api:
    """A TestClient that sends demo_user as a header, so every call says who it is (alice by default), and keeps
    the server's demo_sid as the browser would."""

    def __init__(self, client: TestClient, settings: Settings) -> None:
        self.client = client
        self.settings = settings
        self.sid: str | None = None
        self.app: Any = client.app

    def request(self, method: str, path: str, *, user: str | None = "alice", headers: dict[str, str] | None = None,
                **kwargs: Any) -> Any:
        cookies = [f"demo_sid={self.sid}"] if self.sid else []
        if user is not None:
            cookies.append(f"demo_user={user}")
        all_headers = {**({"Cookie": "; ".join(cookies)} if cookies else {}), **(headers or {})}
        response = self.client.request(method, path, headers=all_headers, **kwargs)
        self.client.cookies.clear()   # the next call says again who it is
        for line in response.headers.get_list("set-cookie"):
            if found := re.match(r"demo_sid=([0-9a-f]{32})", line):
                self.sid = found.group(1)
        return response

    def get(self, path: str, **kwargs: Any) -> Any:
        return self.request("GET", path, **kwargs)

    def post(self, path: str, **kwargs: Any) -> Any:
        return self.request("POST", path, **kwargs)

    def put(self, path: str, **kwargs: Any) -> Any:
        return self.request("PUT", path, **kwargs)

    def delete(self, path: str, **kwargs: Any) -> Any:
        return self.request("DELETE", path, **kwargs)

    def websocket(self, path: str, user: str | None = "alice") -> Any:
        cookies = ([f"demo_sid={self.sid}"] if self.sid else []) + ([f"demo_user={user}"] if user else [])
        return self.client.websocket_connect(path, headers={"Cookie": "; ".join(cookies)} if cookies else {})

    @contextmanager
    def db(self) -> Iterator[sqlite3.Connection]:
        """The app's database (outside demo mode), to read back what a request stored. Closed afterwards."""
        conn = sqlite3.connect(self.settings.database_path, autocommit=True)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def count(self, table: str, where: str = "1", *params: Any) -> int:
        with self.db() as conn:
            return conn.execute(f"SELECT COUNT(*) FROM {table} WHERE {where}", params).fetchone()[0]


@contextmanager
def start_app(data_dir: Path, **overrides: Any) -> Iterator[Api]:
    settings = make_settings(data_dir, **overrides)
    app = create_app(settings)
    with TestClient(app, base_url="http://testserver", raise_server_exceptions=False) as client:
        api = Api(client, settings)
        yield api


@pytest.fixture(scope="module")
def data_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("data")


@pytest.fixture(scope="module")
def api(data_dir: Path) -> Iterator[Api]:
    with start_app(data_dir) as api:
        yield api


def page_config(html: str) -> dict[str, Any]:
    """window.SURVEYJS_PAGE from a rendered page."""
    found = re.search(r"window\.SURVEYJS_PAGE = (.*?);</script>", html)
    assert found, "the page sets window.SURVEYJS_PAGE"
    return json.loads(found.group(1))


ROUNDTRIP = {"a": "  padded  ", "b": "", "c": None, "d": {}, "e": [{}], "f": [], "g": 1.5, "h": "naïve — 東京",
             "i": {"j": {"k": [1, "x", True]}}}
"""The contract test's round-trip document."""
