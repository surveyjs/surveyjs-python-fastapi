"""Under /api every error is { error } with its status, including FastAPI's and Starlette's own answers, which
would otherwise be { "detail": … }. Outside /api the errors are small HTML pages."""

from pathlib import Path

import pytest

from app.db import get_db
from tests.conftest import Api, start_app


def error(r: object) -> tuple[int, object]:
    return r.status_code, r.json()


def test_400_bad_json_a_form_post_to_a_json_endpoint_and_a_bad_query_parameter(api: Api) -> None:
    assert error(api.post("/api/responses", content=b"{not json", headers={"Content-Type": "application/json"})) == \
        (400, {"error": "The request body is not valid JSON"})
    assert error(api.post("/api/responses", data={"formId": "contact", "data": "x"})) == \
        (400, {"error": "The request body is not valid JSON"})
    r = api.get("/api/responses?formId=feedback&limit=abc")
    assert r.status_code == 400 and r.json()["error"].startswith("Invalid limit")
    r = api.get("/api/claims/abc/pdf")
    assert r.status_code == 400 and r.json()["error"].startswith("Invalid id")
    assert error(api.post("/api/responses", json={"formId": "contact"})) == (400, {"error": "Expected { formId, data }"})


def test_401_and_403(api: Api) -> None:
    assert error(api.get("/api/progress/onboarding", user=None)) == (401, {"error": "Sign in to load progress"})
    assert error(api.put("/api/forms/support", json={}, user="bob")) == \
        (403, {"error": "You don't have editor rights: only editors can change forms"})


def test_404_and_405_with_allow(api: Api) -> None:
    assert error(api.get("/api/no-such-thing")) == (404, {"error": "Not found"})
    assert error(api.get("/api/forms/no-such-form")) == (404, {"error": "Unknown form"})
    r = api.request("PATCH", "/api/progress/onboarding")
    assert error(r) == (405, {"error": "Method not allowed"})
    assert r.headers["allow"] == "DELETE, GET, PUT"
    r = api.put("/api/offices")
    assert error(r) == (405, {"error": "Method not allowed"}) and r.headers["allow"] == "GET"


def test_413_body_limit(api: Api) -> None:
    r = api.post("/api/responses", content=b" " * (24 * 1024 * 1024 + 1), headers={"Content-Type": "application/json"})
    assert error(r) == (413, {"error": "The request body is too large"})

    def chunks():   # no Content-Length: the limit counts what arrives
        for _ in range(25):
            yield b" " * (1024 * 1024)
    r = api.post("/api/responses", content=chunks(), headers={"Content-Type": "application/json"})
    assert error(r) == (413, {"error": "The request body is too large"})


def test_422_store_files_without_files(api: Api) -> None:
    assert error(api.post("/api/files", files={"other": ("a.png", b"x", "image/png")})) == \
        (422, {"error": 'Upload one or more files in a field named "files[]"'})


def test_429_demo_ai_limit(tmp_path: Path) -> None:
    with start_app(tmp_path, demo_mode=True) as api:
        api.get("/up")
        api.get("/api/offices")   # takes demo_sid from the server
        for _ in range(20):
            assert api.post("/api/translate", json={"strings": [], "from": "en", "to": "de"}).status_code == 501
        assert error(api.post("/api/translate", json={"strings": [], "from": "en", "to": "de"})) == \
            (429, {"error": "The demo allows 20 AI calls per visitor per day"})


def test_500_logs_and_answers_without_details(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    def broken() -> None:
        raise RuntimeError("the database is on fire")

    with start_app(tmp_path) as api:
        api.app.dependency_overrides[get_db] = broken
        assert error(api.get("/api/offices")) == (500, {"error": "Internal server error"})
    assert "the database is on fire" in caplog.text


def test_pages_get_html_errors(api: Api) -> None:
    r = api.get("/examples/no-such-example")
    assert r.status_code == 404 and r.headers["content-type"].startswith("text/html")
    r = api.get("/examples/edit-together?form=bad%20id")
    assert r.status_code == 400 and "Invalid form ID" in r.text
