"""Creates the tables and seeds them from shared/seed/*.json, the files every platform seeds from.

Idempotent: an existing database keeps its data and only gains the forms it is missing. The app's
lifespan runs it at every start, so a fresh DATA_DIR is ready on the first request.
"""

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from app.db import connect, transaction
from app.integration.stored_json import dumps, timestamp
from app.settings import ROOT

# The tables the integration docs name. Definitions, responses, progress and presets are JSON documents
# kept as text, exactly as they arrived. created_at is ISO 8601 UTC, so `created_at >= ?` compares dates.
SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY, key TEXT NOT NULL UNIQUE, name TEXT NOT NULL, email TEXT NOT NULL UNIQUE,
    plan TEXT NOT NULL DEFAULT 'basic', is_editor INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS forms (key TEXT PRIMARY KEY, json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS responses (
    id INTEGER PRIMARY KEY AUTOINCREMENT, form_id TEXT NOT NULL, definition_version TEXT, data TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS responses_form_id ON responses (form_id, created_at);
CREATE TABLE IF NOT EXISTS progress (key TEXT PRIMARY KEY, json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS files (id TEXT PRIMARY KEY, name TEXT NOT NULL, type TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS offices (id TEXT PRIMARY KEY, name TEXT NOT NULL, region TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS offices_region ON offices (region);
CREATE TABLE IF NOT EXISTS customers (email TEXT PRIMARY KEY);
CREATE TABLE IF NOT EXISTS shipping_rates (postcode_prefix TEXT PRIMARY KEY, price REAL NOT NULL);
CREATE TABLE IF NOT EXISTS claims (
    id INTEGER PRIMARY KEY AUTOINCREMENT, response_id INTEGER NOT NULL REFERENCES responses (id),
    customer_email TEXT, amount REAL
);
CREATE TABLE IF NOT EXISTS variable_presets (key TEXT PRIMARY KEY, json TEXT NOT NULL);
"""


def _shared(path: str) -> Any:
    return json.loads((ROOT / "shared" / path).read_text(encoding="utf-8"))


def _days_ago(days: int) -> str:
    """The reference's times: `days` back, at 09:00 + days % 9 hours and (days * 7) % 60 minutes, UTC."""
    moment = datetime.now(UTC) - timedelta(days=days)
    return timestamp(moment.replace(hour=9 + days % 9, minute=(days * 7) % 60, second=0, microsecond=0))


def seed(path: Path) -> bool:
    """Create and seed the database at path. Returns True when it seeded an empty one."""
    path.parent.mkdir(parents=True, exist_ok=True)
    db = connect(path)
    try:
        db.executescript(SCHEMA)

        # Every form in seed/forms.json, also into an existing database that lacks one
        for key, file in _shared("seed/forms.json").items():
            db.execute("INSERT OR IGNORE INTO forms (key, json) VALUES (?, ?)", (key, dumps(_shared(f"definitions/{file}"))))

        if db.execute("SELECT COUNT(*) FROM users").fetchone()[0] > 0:
            return False

        with transaction(db):
            _seed_rows(db)
        return True
    finally:
        db.close()


def _seed_rows(db: sqlite3.Connection) -> None:
    # Demo only: Alice (premium, editor) and Bob (basic, viewer); app/demo/users.py signs them in from a cookie
    db.executemany(
        "INSERT INTO users (id, key, name, email, plan, is_editor) VALUES (?, ?, ?, ?, ?, ?)",
        [(1, "alice", "Alice Martin", "alice@example.com", "premium", 1), (2, "bob", "Bob Fischer", "bob@example.com", "basic", 0)],
    )
    db.executemany("INSERT INTO offices (id, name, region) VALUES (?, ?, ?)",
                   [(o["id"], o["name"], o["region"]) for o in _shared("seed/offices.json")])
    db.executemany("INSERT INTO customers (email) VALUES (?)", [(email,) for email in _shared("seed/customers.json")])
    db.executemany("INSERT INTO shipping_rates (postcode_prefix, price) VALUES (?, ?)",
                   [(r["postcode_prefix"], r["price"]) for r in _shared("seed/shipping-rates.json")])

    def response(form_id: str, data: Any, created_at: str, version: str | None = None) -> int:
        cursor = db.execute(
            "INSERT INTO responses (form_id, definition_version, data, created_at) VALUES (?, ?, ?, ?)",
            (form_id, version, dumps(data), created_at),
        )
        return int(cursor.lastrowid or 0)

    for claim in _shared("seed/claims.json"):
        response_id = response("claim", claim["data"], _days_ago(claim["daysAgo"]), claim["definitionVersion"])
        db.execute("INSERT INTO claims (response_id, customer_email, amount) VALUES (?, ?, ?)",
                   (response_id, claim["data"]["customer_email"], claim["data"]["amount"]))
    for sheet in _shared("seed/job-sheets.json"):
        response("job-sheet", sheet["data"], _days_ago(sheet["daysAgo"]))
    for row in _shared("seed/feedback-responses.json"):
        response("feedback", row["data"], _days_ago(row["daysAgo"]))

    for form_id, presets in _shared("seed/variable-presets.json").items():
        db.execute("INSERT INTO variable_presets (key, json) VALUES (?, ?)", (form_id, dumps(presets)))

    # load-definition-variables-data: one claim request per demo user, saved now
    for data in _shared("seed/claim-requests.json"):
        response("claim", data, timestamp())
