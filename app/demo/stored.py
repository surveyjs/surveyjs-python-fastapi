"""Demo only: GET /demo/stored/{slug}, the Data panel ("What the server stored"). A fixed, whitelisted read per
example, never arbitrary SQL. The section names and row fields are the reference's: the contract test and
the browser tests read them."""

import json
import re
import sqlite3
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from app.auth import CurrentUser, User
from app.db import Db, get_storage
from app.integration.ttl_cache import Cache
from app.relay.room_key import room_key, snapshot_path

router = APIRouter()

_ROOM = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_ID = re.compile(r"^\s*\+?\d+\s*$")


def _responses(db: sqlite3.Connection, form_id: str | None, id: int | None, limit: int = 5,
               customer_email: str | None = None) -> list[dict[str, Any]]:
    where, params = [], []
    for clause, value in (("form_id = ?", form_id), ("id = ?", id)):
        if value:
            where.append(clause)
            params.append(value)
    if customer_email is not None:
        where.append("data ->> '$.customer_email' = ?")
        params.append(customer_email)
    sql = ("SELECT id, form_id, definition_version, data, created_at FROM responses"
           + (f" WHERE {' AND '.join(where)}" if where else "") + " ORDER BY id DESC LIMIT ?")
    return [{"data": json.loads(row["data"]), "id": row["id"], "form_id": row["form_id"],
             "definition_version": row["definition_version"], "created_at": row["created_at"]}
            for row in db.execute(sql, (*params, limit))]


def _document(db: sqlite3.Connection, table: str, key: str) -> dict[str, Any] | None:
    row = db.execute(f"SELECT json FROM {table} WHERE key = ?", (key,)).fetchone()
    return {"key": key, "json": json.loads(row["json"])} if row else None


def _claims(db: sqlite3.Connection, id: int | None, limit: int = 3) -> dict[str, list[dict[str, Any]]]:
    rows = db.execute(
        "SELECT claims.id AS claim_id, claims.response_id, claims.customer_email, claims.amount,"
        " responses.form_id, responses.definition_version, responses.created_at, responses.data"
        " FROM claims JOIN responses ON responses.id = claims.response_id"
        + (" WHERE responses.id = ?" if id else "") + " ORDER BY claims.id DESC LIMIT ?",
        (*([id] if id else []), limit),
    ).fetchall()
    return {
        "claims": [{"claim_id": r["claim_id"], "response_id": r["response_id"], "customer_email": r["customer_email"],
                    "amount": r["amount"]} for r in rows],
        "responses": [{"id": r["response_id"], "form_id": r["form_id"], "definition_version": r["definition_version"],
                       "created_at": r["created_at"], "data": json.loads(r["data"])} for r in rows],
    }


def _files(db: sqlite3.Connection, limit: int) -> list[dict[str, Any]]:
    return [dict(row) for row in db.execute("SELECT id, name, type FROM files ORDER BY rowid DESC LIMIT ?", (limit,))]


def _row_counts(db: sqlite3.Connection) -> dict[str, int]:
    tables = ("forms", "responses", "progress", "files", "claims", "variable_presets")
    return {table: db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in tables}


def _relay_room(request: Request, relay: str) -> Any:
    settings = request.app.state.settings
    room = request.query_params.get("room", "")
    if not _ROOM.match(room):
        return None
    if not settings.demo_mode:
        return "The relay writes room snapshots in demo mode only (DEMO_MODE=true)"
    path = snapshot_path(settings.relay_dir, room_key(get_storage(request).sandbox_id, room), relay)
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else "No room data"


def stored(slug: str, request: Request, db: sqlite3.Connection, user: User | None, countries_cached: bool) -> dict[str, Any] | None:
    """The Data panel's sections for an example, or None for an unknown slug."""
    raw_id = request.query_params.get("id", "")
    id = int(raw_id) or None if _ID.match(raw_id) else None
    key = request.query_params.get
    email = user.email if user else ""
    match slug:
        case "save-response":
            return {"responses": _responses(db, None if id else "contact", id)}
        case "load-definition-variables-data":
            return {"responses": _responses(db, "claim", id, customer_email=None if id else email)}
        case "resume-progress":
            return {"progress": _document(db, "progress", f"{user.id if user else ''}:{key('key', 'onboarding')}"),
                    "responses": _responses(db, "onboarding", id)}
        case "store-files":
            return {"responses": _responses(db, "expenses", id, 3), "files": _files(db, 10)}
        case "choices-from-web":
            return {
                "responses": _responses(db, "visit", id, 3),
                "offices": [dict(row) for row in db.execute("SELECT id, name, region FROM offices ORDER BY region, name")],
                "countries cache": "cached for 24 hours" if countries_cached else "empty: the next request fetches restcountries.com",
            }
        case "async-functions":
            return {"customers": [row["email"] for row in db.execute("SELECT email FROM customers")],
                    "shipping_rates": [dict(row) for row in db.execute(
                        "SELECT postcode_prefix, price FROM shipping_rates ORDER BY postcode_prefix")]}
        case "relational-storage":
            return _claims(db, id)
        case "fill-together":
            return {"relay room": _relay_room(request, "fill"), "responses": _responses(db, "job-sheet", id, 3)}
        case "dashboard":
            return {"responses": db.execute("SELECT COUNT(*) FROM responses WHERE form_id = 'feedback'").fetchone()[0]}
        case "creator-load-save":
            return {"forms": _document(db, "forms", key("key", "support"))}
        case "ai-translation":
            return {"forms": _document(db, "forms", "support-translations")}
        case "creator-uploads":
            return {"forms": _document(db, "forms", "support-assets"), "files": _files(db, 5)}
        case "variable-presets":
            return {"variable_presets": _document(db, "variable_presets", key("key", "support"))}
        case "edit-together":
            return {"relay room": _relay_room(request, "edit"), "forms": _document(db, "forms", key("key", "support-team"))}
        case "validate-response":
            return {"responses": _responses(db, "claim", id)}
        case "lint-definition":
            return {"forms": _document(db, "forms", "support-lint")}
        case "server-pdf":
            return {"responses": _responses(db, "claim", id, 10)}
        case "extract-from-paper":
            return {"row counts": _row_counts(db), "responses": _responses(db, "work-order", id, 3)}
    return None


@router.get("/demo/stored/{slug}")
def stored_route(slug: str, request: Request, db: Db, user: CurrentUser, cache: Cache) -> dict[str, Any]:
    sections = stored(slug, request, db, user, cache.has("countries"))
    if sections is None:
        raise HTTPException(404)
    return sections
