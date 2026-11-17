"""Use Relational Storage: POST /api/claims keeps the original JSON and its version, then copies the stable
answer keys (valueName) into the claims columns, in one transaction."""

from fastapi import APIRouter, HTTPException

from app.db import Db, transaction
from app.integration.stored_json import JsonBody, insert_response

router = APIRouter()


# region sjs:relational-storage.server
# POST /api/claims — original JSON first, then the columns you query
@router.post("/api/claims", status_code=201)
def save_claim(body: JsonBody, db: Db) -> dict[str, int]:
    # The raw body, not a Pydantic model: the stored answers keep every key, {} and 1.0 as they arrived
    if not isinstance(body, dict) or body.get("data") is None or body.get("definitionVersion") is None:
        raise HTTPException(400, "Expected { data, definitionVersion }")
    data = body["data"]

    with transaction(db):
        id = insert_response(db, "claim", data, body["definitionVersion"])   # the original and its version
        db.execute(                                                          # keys come from valueName
            "INSERT INTO claims (response_id, customer_email, amount) VALUES (?, ?, ?)",
            (id, data.get("customer_email") if isinstance(data, dict) else None,
             data.get("amount") if isinstance(data, dict) else None),
        )

    return {"id": id}
# endregion
