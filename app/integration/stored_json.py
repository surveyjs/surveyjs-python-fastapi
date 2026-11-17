"""Stores SurveyJS JSON (responses, definitions, saved progress, variable presets) exactly as it arrived.

A response or a definition is one JSON document: store it as text, never as columns. Used by
save-response, resume-progress, relational-storage, creator-load-save, variable-presets,
validate-response, lint-definition and the fill-together relay. When you copy one of them, copy this
file too.

Why a raw body and not a Pydantic model: a model (data: dict) answers 422 { detail } for a
non-object, drops keys it doesn't declare and may coerce values. json.loads keeps every key,
{}, [{}], None, "" and 1.0 as they were sent.
"""

import json
import sqlite3
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from fastapi import Depends, HTTPException, Request


def _reject_constant(name: str) -> Any:
    raise ValueError(f"{name} is not JSON")


async def json_body(request: Request) -> Any:
    """The request body as parsed JSON, or 400. Python accepts NaN and Infinity; JSON doesn't, so neither do we."""
    raw = await request.body()
    try:
        return json.loads(raw, parse_constant=_reject_constant)
    except (ValueError, RecursionError):   # JSONDecodeError and UnicodeDecodeError are ValueErrors
        raise HTTPException(400, "The request body is not valid JSON") from None


JsonBody = Annotated[Any, Depends(json_body)]
"""Any JSON value, as sent: each handler checks its own envelope."""


def dumps(value: Any) -> str:
    """JSON text for storage: ensure_ascii=False keeps "naïve — 東京" readable, compact separators, 1.0 stays 1.0."""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def timestamp(moment: datetime | None = None) -> str:
    """ISO 8601 UTC without fractions, 2026-11-16T09:00:00Z: dates filter as string comparisons. isoformat()
    would write +00:00 and microseconds, which break them."""
    return (moment or datetime.now(UTC)).astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def insert_response(db: sqlite3.Connection, form_id: Any, data: Any, definition_version: Any = None) -> int:
    """Insert one response, its answers as one JSON document, and return its id. Each route validates its own input."""
    cursor = db.execute(
        "INSERT INTO responses (form_id, definition_version, data, created_at) VALUES (?, ?, ?, ?)",
        (form_id, definition_version, dumps(data), timestamp()),
    )
    return int(cursor.lastrowid or 0)


DocumentTable = Literal["forms", "progress", "variable_presets"]


def put(db: sqlite3.Connection, table: DocumentTable, key: str, document: Any) -> None:
    """Insert or replace the JSON document stored under a key. The table name is always one of these three."""
    if table not in ("forms", "progress", "variable_presets"):
        raise ValueError(f"Not a document table: {table}")
    db.execute(
        f"INSERT INTO {table} (key, json) VALUES (?, ?) ON CONFLICT (key) DO UPDATE SET json = excluded.json",
        (key, dumps(document)),
    )
