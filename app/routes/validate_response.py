"""Validate Responses: POST /api/responses validated by the SurveyJS service before it is stored.

app/main.py includes this file in place of save_response.py when VALIDATE_RESPONSES=true. The service is
SurveyJS Server, next to this app: see docker-compose.yml and SURVEYJS_SERVICE_URL in app/settings.py.
"""

import json
from contextlib import suppress
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from app.db import Db
from app.integration.stored_json import JsonBody, insert_response
from app.integration.surveyjs_service import SurveyJs

router = APIRouter()


# region sjs:validate-response.server
# POST /api/responses — ask the SurveyJS service to validate, then store as usual
@router.post("/api/responses", status_code=201, response_model=None)
async def save_validated_response(body: JsonBody, db: Db, surveyjs: SurveyJs) -> dict[str, int] | JSONResponse:
    # The raw body, not a Pydantic model: the stored answers keep every key, {} and 1.0 (see Save Responses)
    if not isinstance(body, dict) or not isinstance(body.get("formId"), str) or not isinstance(body.get("data"), dict):
        raise HTTPException(400, "Expected { formId, data } with an answers object")
    form = db.execute("SELECT json FROM forms WHERE key = ?", (body["formId"],)).fetchone()
    if form is None:
        raise HTTPException(404, "Unknown form")

    check = await surveyjs.post("/response", {"schema": json.loads(form["json"]), "response": body["data"]}, timeout=10)
    answer: Any = None
    with suppress(ValueError):   # not JSON: fails closed below
        answer = json.loads(check.content)
    if check.status_code == 422 and isinstance(answer, dict) and "errors" in answer:
        if "warnings" in answer:   # the stored definition itself has errors
            surveyjs.unexpected("/response", check, "The stored definition has errors")
        return JSONResponse({"errors": answer["errors"]}, status_code=400)   # the answers don't fit the definition
    if check.status_code != 200 or answer != {}:   # fail closed: only exactly {} means valid
        surveyjs.unexpected("/response", check)

    return {"id": insert_response(db, body["formId"], body["data"])}   # stored as it arrived: 1.0 stays 1.0
# endregion
