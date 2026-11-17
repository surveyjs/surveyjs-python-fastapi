"""Lint JSON Schemas: PUT /api/forms/{id} linted by the SurveyJS service before it is stored.

app/main.py includes this file in place of creator_load_save.py when LINT_DEFINITIONS=true.
"""

import json
from contextlib import suppress
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, Response

from app.auth import CurrentUser, can
from app.db import Db
from app.integration.stored_json import JsonBody, put
from app.integration.surveyjs_service import SurveyJs

router = APIRouter()


# region sjs:lint-definition.server
# PUT /api/forms/{id} — lint the definition from Creator before storing it
@router.put("/api/forms/{id}", status_code=204, response_model=None)
async def save_linted_form(id: str, definition: JsonBody, user: CurrentUser, db: Db, surveyjs: SurveyJs) -> Response | None:
    if not can(user, "edit-forms"):
        raise HTTPException(403, "You don't have editor rights: only editors can change forms")
    # The raw body keeps {} as {} (see Load and Save Form JSON Schemas)
    lint = await surveyjs.post("/schema", definition, timeout=10)
    answer: Any = None
    with suppress(ValueError):   # not JSON: fails closed below
        answer = json.loads(lint.content)
    if lint.status_code == 422 and isinstance(answer, dict) and {"errors", "warnings"} <= answer.keys():
        return JSONResponse(answer, status_code=422)   # errors: refuse the save, report them as they are
    warnings_only = lint.status_code == 200 and isinstance(answer, dict) and list(answer) == ["warnings"]
    if not warnings_only and (lint.status_code != 200 or answer != {}):   # fail closed: nothing else is clean
        surveyjs.unexpected("/schema", lint)

    put(db, "forms", id, definition)   # stored as it arrived: 1.0 stays 1.0
    return JSONResponse({"warnings": answer["warnings"]}) if warnings_only else None   # warnings don't block it
# endregion
