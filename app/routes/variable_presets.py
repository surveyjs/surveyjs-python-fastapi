"""Variable Presets: GET and PUT /api/variable-presets/{form_id}, the presets Creator's Preview tab offers."""

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from app.auth import CurrentUser, can
from app.db import Db
from app.integration.stored_json import JsonBody, put

router = APIRouter()


# region sjs:variable-presets.server
# GET /api/variable-presets/{form_id} — return the stored preset list, or [] when none are saved
@router.get("/api/variable-presets/{form_id}")
def load_presets(form_id: str, db: Db) -> Response:
    row = db.execute("SELECT json FROM variable_presets WHERE key = ?", (form_id,)).fetchone()
    return Response(row["json"] if row else "[]", media_type="application/json")   # as stored


# PUT /api/variable-presets/{form_id} — store the variable presets as-is: it's one JSON document
@router.put("/api/variable-presets/{form_id}", status_code=204)
def save_presets(form_id: str, presets: JsonBody, user: CurrentUser, db: Db) -> None:
    if not can(user, "edit-forms"):   # editing is an admin action: 403 otherwise
        raise HTTPException(403, "You don't have editor rights: only editors can change forms")
    # The raw body, not a Pydantic model: the presets are stored as they arrived, {} stays {}
    put(db, "variable_presets", form_id, presets)
# endregion
