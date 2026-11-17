"""Run Server-Side Workflows: every row of the meta prompt's status mapping, and the checks made before the service
is called. The service is httpx2.MockTransport, injected through app.dependency_overrides; each test asserts the
status, the body, what was stored, and that no answer reached the log."""

import json
from collections.abc import Callable, Iterator
from pathlib import Path

import httpx2
import pytest

from app.integration.surveyjs_service import SurveyJsService, get_surveyjs_service
from tests.conftest import Api, start_app

SERVICE = "http://surveyjs.test:3000"
PDF = b"%PDF-1.7\n% a filled claim\n%%EOF\n"
PNG = (Path(__file__).parent.parent / "shared" / "samples" / "work-order-scan.png").read_bytes()
SECRET = "Answer written on the paper form"   # must never reach the log
Handler = Callable[[httpx2.Request], httpx2.Response]


@pytest.fixture(scope="module")
def api(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Api]:
    with start_app(tmp_path_factory.mktemp("service"), validate_responses=True, lint_definitions=True) as api:
        yield api


class Service:
    """The mocked SurveyJS service: answers with the handler, counts the calls."""

    def __init__(self, api: Api, handler: Handler) -> None:
        self.calls: list[httpx2.Request] = []

        def record(request: httpx2.Request) -> httpx2.Response:
            self.calls.append(request)
            return handler(request)
        api.app.dependency_overrides[get_surveyjs_service] = lambda: SurveyJsService(
            httpx2.AsyncClient(transport=httpx2.MockTransport(record)), SERVICE)


def answer(status: int, body: object = None, *, content: bytes | None = None, content_type: str = "application/json") -> Handler:
    data = content if content is not None else json.dumps(body).encode()
    return lambda request: httpx2.Response(status, content=data, headers={"Content-Type": content_type})


def timeout(request: httpx2.Request) -> httpx2.Response:
    raise httpx2.ReadTimeout("timed out", request=request)


def refused(request: httpx2.Request) -> httpx2.Response:
    raise httpx2.ConnectError("connection refused", request=request)


UNEXPECTED = [
    answer(200, {"error": "schema is required"}),        # a 2xx alone never means success
    answer(200, content=b"{not json"),
    answer(500, {"error": "boom"}),
    answer(422, {"warnings": []}),
    answer(400, {"error": "INVALID_JSON"}),
]

FAILURES = [(timeout, 504, "SurveyJS service timed out"), (refused, 503, f"SurveyJS service is not running at {SERVICE}")]


# ---------- validate-response

CLAIM = {"customer_email": "valid@example.com", "amount": 120, "incident": "theft", "details": SECRET}


def post_claim(api: Api, data: object = CLAIM) -> object:
    return api.post("/api/responses", json={"formId": "claim", "data": data})


def test_validate_valid_answers_are_saved(api: Api) -> None:
    service = Service(api, answer(200, {}))
    before = api.count("responses")
    r = post_claim(api)
    assert r.status_code == 201 and isinstance(r.json()["id"], int)
    assert api.count("responses") == before + 1
    sent = json.loads(service.calls[0].content)
    assert service.calls[0].url.path == "/response" and sent["response"] == CLAIM and "elements" in json.dumps(sent["schema"])


def test_validate_errors_answer_400_and_save_nothing(api: Api) -> None:
    errors = [{"name": "incident", "text": "Unknown choice"}]
    Service(api, answer(422, {"errors": errors}))
    before = api.count("responses")
    assert (post_claim(api).status_code, post_claim(api).json()) == (400, {"errors": errors})
    assert api.count("responses") == before


def test_validate_a_broken_definition_answers_502(api: Api, caplog: pytest.LogCaptureFixture) -> None:
    Service(api, answer(422, {"errors": [{"rule": "x"}], "warnings": []}))
    before = api.count("responses")
    r = post_claim(api)
    assert (r.status_code, r.json()) == (502, {"error": "The stored definition has errors"})
    assert api.count("responses") == before
    assert "unexpected answer from /response: 422" in caplog.text and SECRET not in caplog.text


@pytest.mark.parametrize("handler", UNEXPECTED)
def test_validate_anything_else_answers_502(api: Api, handler: Handler) -> None:
    Service(api, handler)
    before = api.count("responses")
    r = post_claim(api)
    assert (r.status_code, r.json()) == (502, {"error": "SurveyJS service error"})
    assert api.count("responses") == before


@pytest.mark.parametrize(("handler", "status", "message"), FAILURES)
def test_validate_timeout_and_refused(api: Api, handler: Handler, status: int, message: str) -> None:
    Service(api, handler)
    before = api.count("responses")
    assert (post_claim(api).status_code, post_claim(api).json()) == (status, {"error": message})
    assert api.count("responses") == before


def test_validate_prechecks_never_call_the_service(api: Api) -> None:
    service = Service(api, answer(200, {}))
    before = api.count("responses")
    for body in ([], {"formId": 1, "data": CLAIM}, {"formId": "claim", "data": "answers"}, {"formId": "claim"}):
        r = api.post("/api/responses", json=body)
        assert (r.status_code, r.json()) == (400, {"error": "Expected { formId, data } with an answers object"})
    r = api.post("/api/responses", json={"formId": "no-such-form", "data": {}})
    assert (r.status_code, r.json()) == (404, {"error": "Unknown form"})
    assert service.calls == [] and api.count("responses") == before


# ---------- lint-definition

DEFINITION = {"elements": [{"type": "text", "name": "q1", "title": SECRET}]}


def stored_form(api: Api, key: str) -> object:
    with api.db() as conn:
        row = conn.execute("SELECT json FROM forms WHERE key = ?", (key,)).fetchone()
    return json.loads(row["json"]) if row else None


def test_lint_clean_saves_and_answers_204(api: Api) -> None:
    service = Service(api, answer(200, {}))
    r = api.put("/api/forms/lint-clean", json=DEFINITION)
    assert r.status_code == 204 and r.content == b""
    assert stored_form(api, "lint-clean") == DEFINITION
    assert service.calls[0].url.path == "/schema" and json.loads(service.calls[0].content) == DEFINITION


def test_lint_warnings_save_and_answer_200(api: Api) -> None:
    warnings = [{"rule": "property/unknown", "message": "someproperty"}]
    Service(api, answer(200, {"warnings": warnings}))
    r = api.put("/api/forms/lint-warned", json=DEFINITION)
    assert (r.status_code, r.json()) == (200, {"warnings": warnings})
    assert stored_form(api, "lint-warned") == DEFINITION


def test_lint_errors_answer_422_and_keep_the_previous_version(api: Api) -> None:
    Service(api, answer(200, {}))
    api.put("/api/forms/lint-kept", json={"title": "previous"})
    findings = {"errors": [{"rule": "expression/unknown-variable"}], "warnings": []}
    Service(api, answer(422, findings))
    r = api.put("/api/forms/lint-kept", json=DEFINITION)
    assert (r.status_code, r.json()) == (422, findings)
    assert stored_form(api, "lint-kept") == {"title": "previous"}


@pytest.mark.parametrize("handler", [*UNEXPECTED, answer(422, {"errors": []}), answer(400, {"error": "INVALID_SCHEMA"}),
                                     answer(200, {"warnings": [], "extra": 1})])
def test_lint_anything_else_answers_502_and_saves_nothing(api: Api, handler: Handler) -> None:
    Service(api, handler)
    r = api.put("/api/forms/lint-refused", json=DEFINITION)
    assert (r.status_code, r.json()) == (502, {"error": "SurveyJS service error"})
    assert stored_form(api, "lint-refused") is None


@pytest.mark.parametrize(("handler", "status", "message"), FAILURES)
def test_lint_timeout_and_refused(api: Api, handler: Handler, status: int, message: str) -> None:
    Service(api, handler)
    r = api.put("/api/forms/lint-failed", json=DEFINITION)
    assert (r.status_code, r.json()) == (status, {"error": message})
    assert stored_form(api, "lint-failed") is None


# ---------- server-pdf and the blank work order

def first_claim(api: Api) -> int:
    with api.db() as conn:
        return conn.execute("SELECT id FROM responses WHERE form_id = 'claim' AND definition_version = 'v1'").fetchone()[0]


def test_pdf_bytes_pass_through_with_the_contract_headers(api: Api) -> None:
    service = Service(api, answer(200, content=PDF, content_type="application/pdf"))
    claim = first_claim(api)
    r = api.get(f"/api/claims/{claim}/pdf")
    assert r.status_code == 200 and r.content == PDF
    assert r.headers["content-type"] == "application/pdf"
    assert r.headers["content-disposition"] == f'inline; filename="claim-{claim}.pdf"'
    assert r.headers["cache-control"] == "private, no-store"
    sent = json.loads(service.calls[0].content)
    assert service.calls[0].url.path == "/pdf" and set(sent) == {"schema", "response"}

    r = api.get("/api/work-orders/blank.pdf")
    assert r.status_code == 200 and r.content == PDF
    assert r.headers["content-disposition"] == 'attachment; filename="work-order.pdf"'
    assert r.headers["cache-control"] == "private, no-store"
    assert set(json.loads(service.calls[1].content)) == {"schema"}


@pytest.mark.parametrize("handler", [*UNEXPECTED, answer(200, content=b"not a pdf", content_type="application/pdf"),
                                     answer(200, content=PDF, content_type="application/octet-stream"),
                                     answer(422, {"errors": [], "warnings": []})])
def test_pdf_anything_else_answers_502(api: Api, handler: Handler) -> None:
    Service(api, handler)
    for path in (f"/api/claims/{first_claim(api)}/pdf", "/api/work-orders/blank.pdf"):
        r = api.get(path)
        assert (r.status_code, r.json()) == (502, {"error": "SurveyJS service error"}), path


@pytest.mark.parametrize(("handler", "status", "message"), FAILURES)
def test_pdf_timeout_and_refused(api: Api, handler: Handler, status: int, message: str) -> None:
    Service(api, handler)
    for path in (f"/api/claims/{first_claim(api)}/pdf", "/api/work-orders/blank.pdf"):
        assert (api.get(path).status_code, api.get(path).json()) == (status, {"error": message}), path


def test_pdf_prechecks_never_call_the_service(api: Api) -> None:
    service = Service(api, answer(200, content=PDF, content_type="application/pdf"))
    assert (api.get("/api/claims/999999/pdf").status_code, api.get("/api/claims/999999/pdf").json()) == \
        (404, {"error": "Unknown claim"})
    with api.db() as conn:
        claim = conn.execute("INSERT INTO responses (form_id, definition_version, data, created_at)"
                             " VALUES ('claim', 'v9', '{}', '2026-11-16T09:00:00Z')").lastrowid
    r = api.get(f"/api/claims/{claim}/pdf")
    assert (r.status_code, r.json()) == (409, {"error": "The schema version for this claim is unavailable"})
    assert service.calls == []


def test_blank_work_order_of_an_unknown_form_answers_404(tmp_path: Path) -> None:
    with start_app(tmp_path) as api:
        service = Service(api, answer(200, content=PDF, content_type="application/pdf"))
        with api.db() as conn:
            conn.execute("DELETE FROM forms WHERE key = 'work-order'")
        r = api.get("/api/work-orders/blank.pdf")
        assert (r.status_code, r.json()) == (404, {"error": "Unknown work order form"})
        assert service.calls == []


# ---------- extract-from-paper

EXTRACTED = {"data": {"customer": SECRET, "hours": None}, "confidence": [{"fieldName": "customer", "value": SECRET,
             "confidence": 0.42, "flagged": True}], "uniqueId": "WO-1001"}


def extract(api: Api, content: bytes = PNG, field: str = "scan") -> object:
    return api.post("/api/work-orders/extract", files={field: ("scan.png", content, "image/png")})


def rows(api: Api) -> list[int]:
    return [api.count(table) for table in ("forms", "responses", "progress", "files", "claims", "variable_presets")]


def test_extract_answers_the_draft_and_saves_nothing(api: Api, caplog: pytest.LogCaptureFixture) -> None:
    service = Service(api, answer(200, EXTRACTED))
    before = rows(api)
    r = extract(api)
    assert (r.status_code, r.json()) == (200, {"answers": EXTRACTED["data"], "confidence": EXTRACTED["confidence"],
                                               "uniqueId": "WO-1001"})
    assert rows(api) == before and SECRET not in caplog.text
    sent = json.loads(service.calls[0].content)   # JSON with base64, never multipart
    assert service.calls[0].headers["content-type"] == "application/json" and set(sent) == {"schema", "document"}
    assert isinstance(sent["document"], str) and sent["document"].startswith("iVBOR")


@pytest.mark.parametrize(("status", "code", "message"), [
    (400, "INVALID_DOCUMENT", "The file is not a PDF, PNG, JPEG, WebP or GIF document"),
    (503, "AI_NOT_CONFIGURED", "The SurveyJS service has no AI provider configured"),
    (502, "EXTRACTION_FAILED", "Could not extract the response from the document"),
])
def test_extract_recognized_failures(api: Api, status: int, code: str, message: str) -> None:
    Service(api, answer(status, {"error": code}))
    before = rows(api)
    assert (extract(api).status_code, extract(api).json()) == (status, {"error": message})
    assert rows(api) == before


@pytest.mark.parametrize("handler", [*UNEXPECTED, answer(200, {"data": [SECRET]}), answer(200, {"confidence": []}),
                                     answer(422, {"errors": [], "warnings": []}), answer(400, {"error": "EXTRACTION_FAILED"})])
def test_extract_anything_else_answers_502_logged_by_status_only(api: Api, handler: Handler,
                                                                  caplog: pytest.LogCaptureFixture) -> None:
    Service(api, handler)
    before = rows(api)
    r = extract(api)
    assert (r.status_code, r.json()) == (502, {"error": "SurveyJS service error"})
    assert rows(api) == before
    assert "unexpected answer from /extract" in caplog.text and SECRET not in caplog.text


@pytest.mark.parametrize(("handler", "status", "message"), FAILURES)
def test_extract_timeout_and_refused(api: Api, handler: Handler, status: int, message: str) -> None:
    Service(api, handler)
    assert (extract(api).status_code, extract(api).json()) == (status, {"error": message})


def test_extract_prechecks_never_call_the_service(api: Api) -> None:
    service = Service(api, answer(200, EXTRACTED))
    r = extract(api, field="document")
    assert (r.status_code, r.json()) == (400, {"error": 'Upload the scan in a field named "scan"'})
    r = api.post("/api/work-orders/extract", data={"scan": "not a file"})
    assert (r.status_code, r.json()) == (413, {"error": "The scan must be a file of 5 MB or less"})
    r = extract(api, PNG + b"\0" * (5 * 1024 * 1024))
    assert (r.status_code, r.json()) == (413, {"error": "The scan must be a file of 5 MB or less"})
    r = extract(api, b"Not a scan: plain text in a file named .png\n")
    assert (r.status_code, r.json()) == (400, {"error": "The file is not a PDF, PNG, JPEG, WebP or GIF document"})
    assert service.calls == []
