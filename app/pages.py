"""Demo only: the catalog and the example pages around the examples. The integration code is in
app/routes/<snake_slug>.py; these routes only show it running.

The reference's Blade views compute a few things in @php blocks (the records to pick from, the
edit-together form check and its 400, server-pdf's claims, ?form, ?version). Here PAGE_DATA does that
work before the template renders: templates neither query nor set a status.
"""

import json
import re
import sqlite3
from collections.abc import Callable
from itertools import groupby
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates

from app.auth import User, find_user
from app.db import connect, get_storage
from app.demo import users
from app.demo.code_panel import code_definitions, code_panel
from app.demo.manifest import docs_url, find_step, read_manifest
from app.frontend import FONTS, HIGHLIGHT_THEME, import_map, stylesheets
from app.settings import ROOT, Settings

TITLE = "Python Backend Integration with FastAPI"
"""The catalog's browser title, and the example pages' header next to the SurveyJS pill"""
HEADER = "Step-by-Step Python Backend Integration with FastAPI"
"""The catalog header, next to the logo"""

templates = Jinja2Templates(directory=ROOT / "templates")
# The page config and the definitions keep their key order; tojson still escapes <, > and & for inline scripts
templates.env.policies["json.dumps_kwargs"] = {"sort_keys": False}
# The catalog's section anchors: "Run Forms" -> "run-forms"
templates.env.filters["slug"] = lambda text: re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")

router = APIRouter()


def _settings(request: Request) -> Settings:
    return request.app.state.settings


def _site(request: Request) -> dict[str, Any]:
    """What the catalog, the PDF loading page and the example pages all read."""
    settings = _settings(request)
    url = request.url
    return {
        "title": TITLE,
        "header": HEADER,
        "settings": settings,
        "build": settings.surveyjs_build,
        "docs": docs_url(settings.surveyjs_docs),
        "canonical": f"{url.scheme}://{url.netloc}{url.path}",   # https behind a TLS proxy (X-Forwarded-Proto)
        "fonts": FONTS,
    }


@router.get("/", response_class=HTMLResponse)
def catalog(request: Request) -> Response:
    manifest = read_manifest()
    groups = {section: list(steps) for section, steps in groupby(manifest["steps"], key=lambda step: step["section"])}
    return templates.TemplateResponse(request, "catalog.html", {**_site(request), "manifest": manifest, "groups": groups})


@router.get("/examples/server-pdf/loading", response_class=HTMLResponse)
def pdf_loading(request: Request) -> Response:
    return templates.TemplateResponse(request, "examples/pdf-loading.html", _site(request))


@router.get("/examples/{slug}", response_class=HTMLResponse)
def example(request: Request, slug: str) -> Response:
    if not re.fullmatch(r"[a-z0-9-]+", slug) or find_step(slug) is None:
        raise HTTPException(404)
    return render_example(request, slug)


def render_example(request: Request, slug: str, **context: Any) -> Response:
    """An example page: signs in the page's demo user, adds the page config, runs PAGE_DATA, renders the template.
    /claim (Option A of load-definition-variables-data) calls it with the definition and the variables."""
    step = find_step(slug)
    if step is None:
        raise HTTPException(404)
    cookies = Response()   # collects the demo_user cookie, if the page changes it
    users.sign_in_for_page(slug, request, cookies)
    db = connect(get_storage(request).database)
    try:
        user = find_user(db, users.demo_user_key(request))
        page_data = PAGE_DATA.get(slug, lambda *_: {})(request, db, user)
        page = page_config(request, step, db, user)
    finally:
        db.close()
    settings = _settings(request)
    theme_users = users.for_page(slug)
    response = templates.TemplateResponse(request, f"examples/{slug}.html", {
        **_site(request),
        "step": step,
        "page": page,
        "users": theme_users,
        "labels": users.LABELS,
        "user": user,
        "commercial": step["licence"].startswith("Commercial"),
        "needs_ai": "needs an AI provider" in step["licence"],
        "step_docs": docs_url(settings.surveyjs_docs, step),
        "join_failed": request.scope.get("state", {}).get("demo_join_failed", False),
        "code_definitions": code_definitions(settings.surveyjs_github, step),
        "code_panel": code_panel(settings.surveyjs_github, step),
        "import_map": import_map(),
        "styles": stylesheets(),
        "highlight_theme": HIGHLIGHT_THEME,
        **page_data,
        **context,
    })
    response.headers.raw.extend(header for header in cookies.headers.raw if header[0] == b"set-cookie")
    return response


def _read_json(path: str) -> Any:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def page_config(request: Request, step: dict[str, Any], db: sqlite3.Connection, user: User | None) -> dict[str, Any]:
    """window.SURVEYJS_PAGE: what shared/client/host.js and the example modules read."""
    settings = _settings(request)
    definitions = {role: _read_json(path) for role, path in step["files"].items() if role.startswith("definition")}
    if step["slug"] == "extract-from-paper":
        form = db.execute("SELECT json FROM forms WHERE key = 'work-order'").fetchone()
        if form is None:
            raise HTTPException(404, "Unknown work order form")
        definitions["definition"] = json.loads(form["json"])
    # The relays run in this app: the page's own origin, ws or wss as the visitor sees it (X-Forwarded-Proto)
    origin = f"{'wss' if request.url.scheme == 'https' else 'ws'}://{request.url.netloc}"
    return {
        "slug": step["slug"],
        "version": read_manifest()["surveyjsVersion"],
        "licenseKey": settings.surveyjs_license_key,
        "demoUser": user.key if user else "none",
        "user": {"key": user.key, "name": user.name, "plan": user.plan, "isEditor": user.is_editor} if user else None,
        "relay": {
            "fill": {"url": settings.relay_url or origin, "port": settings.app_port},
            "edit": {"url": settings.edit_relay_url or origin, "port": settings.app_port},
        },
        "demoMode": settings.demo_mode,
        "sandboxId": get_storage(request).sandbox_id,
        "switches": {"validateResponses": settings.validate_responses, "lintDefinitions": settings.lint_definitions},
        **definitions,
    }


# What some example pages compute before they render: the reference does this in the views' @php blocks.

def _records(db: sqlite3.Connection, form_id: str, label_key: str, customer_email: str | None = None) -> list[dict[str, str]]:
    sql = "SELECT id, data FROM responses WHERE form_id = ?"
    params: list[Any] = [form_id]
    if customer_email is not None:
        sql += " AND data ->> '$.customer_email' = ?"
        params.append(customer_email)
    rows = db.execute(sql + " ORDER BY id LIMIT 10", params).fetchall()
    return [{"id": str(row["id"]), "label": f"#{row['id']} · {_label(json.loads(row['data']), label_key)}"} for row in rows]


def _label(data: Any, key: str) -> str:
    value = data.get(key) if isinstance(data, dict) else None
    return "" if value is None else str(value)


def _query(request: Request, name: str, fallback: str) -> str:
    return request.query_params.get(name, fallback)


def _fill_together(request: Request, db: sqlite3.Connection, user: User | None) -> dict[str, Any]:
    records = _records(db, "job-sheet", "customer")
    record = _query(request, "record", records[0]["id"] if records else "new")
    return {"records": records, "record": record, "known": any(r["id"] == record for r in records)}


def _edit_together(request: Request, db: sqlite3.Connection, user: User | None) -> dict[str, Any]:
    form_id = _query(request, "form", "support-team")
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", form_id):
        raise HTTPException(400, "Invalid form ID")
    forms = []
    for row in db.execute("SELECT key, json FROM forms WHERE key LIKE '%-team' OR key LIKE 'team-%' ORDER BY key"):
        title = json.loads(row["json"]).get("title")
        label = title if isinstance(title, str) else title.get("default") if isinstance(title, dict) else None
        forms.append({"id": row["key"], "label": label or "Untitled form"})
    return {"forms": forms, "form_id": form_id, "known": any(f["id"] == form_id for f in forms)}


def _server_pdf(request: Request, db: sqlite3.Connection, user: User | None) -> dict[str, Any]:
    claims = []
    for row in db.execute("SELECT id, data FROM responses WHERE form_id = 'claim' ORDER BY id DESC LIMIT 10"):
        answers = json.loads(row["data"])
        email = answers.get("customer_email") if isinstance(answers, dict) else None
        label = email if isinstance(email, (str, int, float)) else "No email provided"
        claims.append({"id": row["id"], "label": label, "json": json.dumps(answers, indent=4, ensure_ascii=False)})
    return {"claims": claims}


PAGE_DATA: dict[str, Callable[[Request, sqlite3.Connection, User | None], dict[str, Any]]] = {
    "load-definition-variables-data": lambda request, db, user: {
        "record": _query(request, "record", ""),
        "records": _records(db, "claim", "customer_email", user.email if user else ""),
    },
    "fill-together": _fill_together,
    "edit-together": _edit_together,
    "relational-storage": lambda request, db, user: {"version": "v2" if request.query_params.get("version") == "v2" else "v1"},
    "server-pdf": _server_pdf,
    "creator-load-save": lambda request, db, user: {"form_mode": "form" in request.query_params},
    "creator-uploads": lambda request, db, user: {"form_mode": "form" in request.query_params},
}
