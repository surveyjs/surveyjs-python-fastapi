"""JSON is stored exactly as it arrives: the contract's round-trip document through every storing endpoint, read
back from SQLite itself, and the JSON that Python accepts but JSON doesn't (NaN, Infinity) refused."""

import json

import httpx2
import pytest

from app.integration.stored_json import dumps
from app.integration.surveyjs_service import SurveyJsService, get_surveyjs_service
from tests.conftest import ROUNDTRIP, Api, start_app


def stored(api: Api, sql: str, *params: object) -> object:
    with api.db() as conn:
        return json.loads(conn.execute(sql, params).fetchone()[0])


def test_save_response(api: Api) -> None:
    r = api.post("/api/responses", json={"formId": "roundtrip", "data": ROUNDTRIP})
    assert r.status_code == 201
    assert isinstance(r.json()["id"], int) and r.json()["id"] >= 1
    assert stored(api, "SELECT data FROM responses WHERE id = ?", r.json()["id"]) == ROUNDTRIP


def test_stored_text_keeps_one_point_zero_and_readable_unicode(api: Api) -> None:
    r = api.post("/api/responses", content=b'{"formId":"roundtrip","data":{"n":1.0,"h":"na\\u00efve"}}',
                 headers={"Content-Type": "application/json"})
    with api.db() as conn:
        text = conn.execute("SELECT data FROM responses WHERE id = ?", (r.json()["id"],)).fetchone()[0]
    assert text == '{"n":1.0,"h":"naïve"}'


def test_resume_progress(api: Api) -> None:
    document = {"data": ROUNDTRIP, "uiState": {"currentPageName": "page2"}}
    assert api.put("/api/progress/roundtrip", json=document).status_code == 204
    assert stored(api, "SELECT json FROM progress WHERE key = '1:roundtrip'") == document
    assert api.get("/api/progress/roundtrip").json() == document


def test_relational_storage(api: Api) -> None:
    data = {**ROUNDTRIP, "customer_email": "a@example.com", "amount": 10.0}
    r = api.post("/api/claims", json={"data": data, "definitionVersion": "v2"})
    assert r.status_code == 201
    assert stored(api, "SELECT data FROM responses WHERE id = ?", r.json()["id"]) == data
    with api.db() as conn:
        row = conn.execute("SELECT customer_email, amount FROM claims WHERE response_id = ?", (r.json()["id"],)).fetchone()
    assert (row["customer_email"], row["amount"]) == ("a@example.com", 10.0)


def test_creator_load_save(api: Api) -> None:
    assert api.put("/api/forms/roundtrip", json=ROUNDTRIP).status_code == 204
    assert stored(api, "SELECT json FROM forms WHERE key = 'roundtrip'") == ROUNDTRIP
    assert api.get("/api/forms/roundtrip").json()["definition"] == ROUNDTRIP


def test_variable_presets(api: Api) -> None:
    presets = [{"name": "basic", "variables": {"extra": {}}}, {"name": "premium", "description": "", "variables": ROUNDTRIP}]
    assert api.put("/api/variable-presets/roundtrip", json=presets).status_code == 204
    assert stored(api, "SELECT json FROM variable_presets WHERE key = 'roundtrip'") == presets
    assert api.get("/api/variable-presets/roundtrip").json() == presets


def test_dashboard_returns_the_stored_documents(api: Api) -> None:
    api.post("/api/responses", json={"formId": "roundtrip-dashboard", "data": ROUNDTRIP})
    r = api.get("/api/responses?formId=roundtrip-dashboard")
    assert r.headers["content-type"].startswith("application/json")
    assert r.json() == [ROUNDTRIP]


def test_fill_together_saves_as_save_response_does(api: Api) -> None:
    with api.websocket("/ws/rooms/roundtrip?name=Ann") as ws:
        assert ws.receive_json()["type"] == "init"
        ws.send_json({"type": "complete", "data": ROUNDTRIP})
        completed = ws.receive_json()
    assert completed["type"] == "completed"
    assert stored(api, "SELECT data FROM responses WHERE id = ? AND form_id = 'job-sheet'", completed["id"]) == ROUNDTRIP


def test_validate_response_stores_what_it_validated(tmp_path_factory: pytest.TempPathFactory) -> None:
    def valid(request: httpx2.Request) -> httpx2.Response:
        assert json.loads(request.content)["response"] == ROUNDTRIP   # the service gets the answers as sent
        return httpx2.Response(200, json={})

    with start_app(tmp_path_factory.mktemp("validate"), validate_responses=True) as api:
        api.app.dependency_overrides[get_surveyjs_service] = lambda: SurveyJsService(
            httpx2.AsyncClient(transport=httpx2.MockTransport(valid)), "http://surveyjs")
        r = api.post("/api/responses", json={"formId": "claim", "data": ROUNDTRIP})
        assert r.status_code == 201
        assert stored(api, "SELECT data FROM responses WHERE id = ?", r.json()["id"]) == ROUNDTRIP


@pytest.mark.parametrize("body", [b'{"formId":"x","data":NaN}', b'{"formId":"x","data":Infinity}', b'{"formId":"x","data":-Infinity}',
                                  b"{not json", b"", "{\"formId\":\"x\",\"data\":\"\xe9\"}".encode("latin-1")])
def test_bodies_that_are_not_json_answer_400(api: Api, body: bytes) -> None:
    for method, path in (("POST", "/api/responses"), ("PUT", "/api/progress/x"), ("POST", "/api/claims"),
                         ("PUT", "/api/forms/x"), ("PUT", "/api/variable-presets/x")):
        r = api.request(method, path, content=body, headers={"Content-Type": "application/json"})
        assert (r.status_code, r.json()) == (400, {"error": "The request body is not valid JSON"}), f"{method} {path}"


def test_dumps_refuses_nan() -> None:
    with pytest.raises(ValueError):
        dumps(float("nan"))
