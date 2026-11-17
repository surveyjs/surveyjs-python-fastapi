"""Analyze Results with Dashboard: GET /api/responses, the stored documents of one form, filtered and paged."""

import json
from typing import Annotated

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse, Response

from app.db import Db

router = APIRouter()


# region sjs:dashboard.server
# GET /api/responses?formId=&includeCreatedAt=&from=&to=&limit=&offset=
@router.get("/api/responses")
def responses(
    db: Db,
    form_id: Annotated[str, Query(alias="formId")] = "",
    include_created_at: Annotated[bool, Query(alias="includeCreatedAt")] = False,
    since: Annotated[str, Query(alias="from")] = "1970-01-01",
    to: str = "",
    limit: int = 500,
    offset: int = 0,
) -> Response:
    rows = db.execute(   # ISO 8601 UTC strings compare as dates; `to` includes that whole day
        "SELECT data, created_at FROM responses WHERE form_id = ? AND created_at >= ?"
        " AND (? = '' OR substr(created_at, 1, 10) <= ?) ORDER BY created_at, id LIMIT ? OFFSET ?",
        (form_id, since, to, to, min(max(limit, 1), 5000), max(offset, 0)),   # page on the server for large volumes
    ).fetchall()

    # Include submission dates separately when requested by Dashboard
    if include_created_at:
        return JSONResponse([{"data": json.loads(row["data"]), "createdAt": row["created_at"]} for row in rows])
    return Response("[" + ",".join(row["data"] for row in rows) + "]", media_type="application/json")   # as stored
# endregion
