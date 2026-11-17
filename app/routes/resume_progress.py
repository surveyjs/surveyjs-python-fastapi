"""Resume Progress: GET, PUT and DELETE /api/progress/{form_id}, a draft per user and form."""

from fastapi import APIRouter, HTTPException, Response

from app.auth import CurrentUser
from app.db import Db
from app.integration.stored_json import JsonBody, put

router = APIRouter()


# region sjs:resume-progress.server
# Return the current user's saved answers and UI state, or null when there is no draft
@router.get("/api/progress/{form_id}")
def load_progress(form_id: str, user: CurrentUser, db: Db) -> Response:
    if user is None:
        raise HTTPException(401, "Sign in to load progress")
    row = db.execute("SELECT json FROM progress WHERE key = ?", (f"{user.id}:{form_id}",)).fetchone()
    return Response(row["json"] if row else "null", media_type="application/json")   # as stored


# Store progress under a key containing both the user ID and form ID
@router.put("/api/progress/{form_id}", status_code=204)
def save_progress(form_id: str, body: JsonBody, user: CurrentUser, db: Db) -> None:
    if user is None:
        raise HTTPException(401, "Sign in to save progress")
    # The raw body, not a Pydantic model: { data, uiState } is stored as it arrived, {} stays {}
    put(db, "progress", f"{user.id}:{form_id}", body)
# endregion


# region sjs:resume-progress.delete
# Remove only the current user's draft
@router.delete("/api/progress/{form_id}", status_code=204)
def clear_progress(form_id: str, user: CurrentUser, db: Db) -> None:
    if user is None:
        raise HTTPException(401, "Sign in to clear progress")
    db.execute("DELETE FROM progress WHERE key = ?", (f"{user.id}:{form_id}",))
# endregion
