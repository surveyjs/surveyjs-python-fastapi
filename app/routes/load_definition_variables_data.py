"""Load JSON Schemas, Variables, and Answers: GET /claim (Option A) and GET /api/forms/{id} (Option B).

Creator, the Dashboard and the other Creator examples read .definition from the same GET /api/forms/{id}.
"""

import json
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, Response

from app.auth import CurrentUser
from app.db import Db
from app.pages import render_example
from app.settings import ROOT

router = APIRouter()

DEFINITION = ROOT / "shared" / "definitions" / "load-definition-variables-data.json"


# region sjs:load-definition-variables-data.server
# Option A: Embed the schema and user variables in the HTML response
@router.get("/claim", response_class=HTMLResponse)
def claim_page(request: Request, user: CurrentUser) -> Response:
    definition = json.loads(DEFINITION.read_text(encoding="utf-8"))
    variables = {"user": {"name": user.name if user else None, "plan": user.plan if user else None}}
    # The template writes both with Jinja's tojson, which escapes them for an inline <script>
    return render_example(request, "load-definition-variables-data", form_definition=definition, form_variables=variables)


# Option B: Return the definition, variables, and previous answers in one response
@router.get("/api/forms/{id}")
def load_form(id: str, user: CurrentUser, db: Db, record: str = "") -> dict[str, Any]:
    if (form := db.execute("SELECT json FROM forms WHERE key = ?", (id,)).fetchone()) is None:
        raise HTTPException(404, "Unknown form")
    if id == "claim-request":   # only the signed-in customer's own claims
        saved = db.execute("SELECT data FROM responses WHERE id = ? AND form_id = 'claim' AND data ->> '$.customer_email' = ?",
                           (record, user.email if user else "")).fetchone()
    else:
        saved = db.execute("SELECT data FROM responses WHERE id = ?", (record,)).fetchone()
    return {
        "definition": json.loads(form["json"]),                       # the stored form definition
        "variables": {"user": {"name": user.name if user else None, "plan": user.plan if user else None}},
        "data": json.loads(saved["data"]) if saved else {},           # previous answers, or {} without them
    }
# endregion
