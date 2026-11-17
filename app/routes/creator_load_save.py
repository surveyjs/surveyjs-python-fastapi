"""Load and Save Form JSON Schemas: PUT /api/forms/{id} stores a definition from Survey Creator.

GET /api/forms/{id} is in load_definition_variables_data.py: Creator reads its .definition. This file holds
only the PUT, so app/main.py can include lint_definition.py in its place when LINT_DEFINITIONS=true.
"""

from fastapi import APIRouter, HTTPException

from app.auth import CurrentUser, can
from app.db import Db
from app.integration.stored_json import JsonBody, put

router = APIRouter()


# region sjs:creator-load-save.server
# PUT /api/forms/{id} — store the definition as-is: it's one JSON document
@router.put("/api/forms/{id}", status_code=204)
def save_form(id: str, definition: JsonBody, user: CurrentUser, db: Db) -> None:
    if not can(user, "edit-forms"):   # editing is an admin action: 403 otherwise
        raise HTTPException(403, "You don't have editor rights: only editors can change forms")
    # The raw body, not a Pydantic model: a model would drop the keys it doesn't declare
    put(db, "forms", id, definition)   # stored as it arrived: {} stays {}, 1.0 stays 1.0
    # 204: the next page load renders the new version
# endregion
