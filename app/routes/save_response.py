"""Save Responses: POST /api/responses stores submitted answers as one JSON document.

app/main.py includes validate_response.py in place of this file when VALIDATE_RESPONSES=true.
"""

from fastapi import APIRouter, HTTPException

from app.db import Db
from app.integration.stored_json import JsonBody, insert_response

router = APIRouter()


# region sjs:save-response.server
# POST /api/responses: Store submitted answers as one JSON document
@router.post("/api/responses", status_code=201)
def save_response(body: JsonBody, db: Db) -> dict[str, int]:
    # The raw body, not a Pydantic model: a model would drop unknown keys and coerce values in the answers
    if not isinstance(body, dict) or "formId" not in body or "data" not in body:
        raise HTTPException(400, "Expected { formId, data }")

    id = insert_response(db, body["formId"], body["data"])   # stored as it arrived: {} stays {}, 1.0 stays 1.0

    return {"id": id}
# endregion
