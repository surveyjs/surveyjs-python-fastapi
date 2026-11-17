"""SQLite through the standard sqlite3 module: plain parameterized SQL, no ORM, so "a response is one
JSON document" stays visible. Handlers take a connection with the Db dependency and call its own
execute(); the helpers here wrap what the handlers shouldn't repeat.

One connection per request, closed after the response. FastAPI may run a yield dependency and a def
handler on different threads of its pool, hence check_same_thread=False (a connection is never used
by two threads at once). In demo mode app/demo/sandbox.py points the request at a visitor's copy.
"""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

from fastapi import Depends
from starlette.requests import HTTPConnection


@dataclass(frozen=True)
class Storage:
    """Where a request's data lives: the app's database and uploads folder, or a visitor sandbox's."""

    database: Path
    files: Path
    sandbox_id: str | None = None


def connect(path: Path) -> sqlite3.Connection:
    """Open a database: rows by column name, WAL so readers don't block the writer, 5 s to wait for a lock."""
    conn = sqlite3.connect(path, check_same_thread=False, autocommit=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """Everything inside commits together, or nothing does."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    conn.execute("COMMIT")


def get_storage(conn: HTTPConnection) -> Storage:
    """The request's storage: the visitor's sandbox in demo mode (set by app/demo/sandbox.py), else the app's."""
    storage = conn.scope.get("state", {}).get("storage")
    if isinstance(storage, Storage):
        return storage
    settings = conn.app.state.settings
    return Storage(settings.database_path, settings.files_dir)


def get_db(storage: Annotated[Storage, Depends(get_storage)]) -> Iterator[sqlite3.Connection]:
    conn = connect(storage.database)
    try:
        yield conn
    finally:
        conn.close()


def get_files_dir(storage: Annotated[Storage, Depends(get_storage)]) -> Path:
    return storage.files


Db = Annotated[sqlite3.Connection, Depends(get_db)]
"""The request's database connection."""

FilesDir = Annotated[Path, Depends(get_files_dir)]
"""The folder the request's uploads live in, named by id (store-files)."""
