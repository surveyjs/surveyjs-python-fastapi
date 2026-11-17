"""Demo only: with DEMO_MODE=true each visitor works in a private copy of the seeded database and an uploads
folder, chosen by the demo_sid cookie. The example routes don't change: the Db and FilesDir dependencies
read the storage this middleware puts into scope["state"]. Delete this file (and its line in
app/main.py) when you copy an example into your app.

Pure ASGI, so it runs for the WebSocket relays too: they seed rooms from and save into the same copy.
"""

import os
import re
import secrets
import shutil
import sqlite3
import time
from http.cookies import SimpleCookie
from pathlib import Path

from starlette.concurrency import run_in_threadpool
from starlette.requests import HTTPConnection
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.db import Storage
from app.settings import Settings

TTL_HOURS = 24
_ID = re.compile(r"^[0-9a-f]{32}$")
_MONTH = 30 * 24 * 3600


def is_valid_id(value: object) -> bool:
    """128 random bits as 32 lowercase hex characters; nothing else ever reaches a file path."""
    return isinstance(value, str) and _ID.match(value) is not None


def new_id() -> str:
    return secrets.token_hex(16)


def _paths(settings: Settings, sandbox_id: str) -> Storage:
    return Storage(settings.sandbox_dir / f"{sandbox_id}.sqlite", settings.sandbox_dir / sandbox_id, sandbox_id)


def exists(settings: Settings, sandbox_id: object) -> bool:
    return is_valid_id(sandbox_id) and _paths(settings, str(sandbox_id)).database.is_file()


def resolve(settings: Settings, sandbox_id: str) -> Storage:
    """The visitor's sandbox, created from the seeded database on first use, and marked as used now."""
    if not is_valid_id(sandbox_id):
        raise ValueError("Invalid sandbox id")
    storage = _paths(settings, sandbox_id)
    if not storage.database.is_file():
        storage.files.mkdir(parents=True, exist_ok=True)
        # backup(), not a file copy: the seeded database is in WAL mode and may have pages in its -wal file
        source, target = sqlite3.connect(settings.database_path), sqlite3.connect(storage.database)
        try:
            source.backup(target)
        finally:
            target.close()
            source.close()
    os.utime(storage.database)   # last used: prune() removes sandboxes unused for 24 hours
    return storage


def prune(settings: Settings, now: float | None = None) -> int:
    """Remove sandboxes (and relay snapshots) unused for 24 hours. app/demo/pruner.py runs it hourly."""
    cutoff = (now or time.time()) - TTL_HOURS * 3600
    removed = 0
    for database in settings.sandbox_dir.glob("*.sqlite") if settings.sandbox_dir.is_dir() else []:
        if is_valid_id(database.stem) and database.stat().st_mtime < cutoff:
            for suffix in ("", "-wal", "-shm"):
                Path(f"{database}{suffix}").unlink(missing_ok=True)
            shutil.rmtree(settings.sandbox_dir / database.stem, ignore_errors=True)
            removed += 1
    for snapshot in settings.relay_dir.glob("*.json") if settings.relay_dir.is_dir() else []:
        if snapshot.stat().st_mtime < cutoff:
            snapshot.unlink(missing_ok=True)
    return removed


class DemoSandbox:
    """Resolves the visitor's sandbox from demo_sid, or from an invite link's ?join=<id>, on every request."""

    def __init__(self, app: ASGIApp, settings: Settings) -> None:
        self.app = app
        self.settings = settings

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if not self.settings.demo_mode or scope["type"] not in ("http", "websocket"):
            return await self.app(scope, receive, send)

        conn = HTTPConnection(scope)
        sandbox_id = conn.cookies.get("demo_sid")
        issue_cookie = join_failed = False

        # An invite link (?join=<id>) adopts the inviter's sandbox, after the same format check
        join = conn.query_params.get("join")
        if join is not None and scope["type"] == "http" and not conn.url.path.startswith("/api/"):
            if exists(self.settings, join):
                issue_cookie, sandbox_id = sandbox_id != join, join
            else:
                join_failed, sandbox_id = True, None   # the page header says the invite has expired

        state = scope.setdefault("state", {})
        state["demo_join_failed"] = join_failed
        if not is_valid_id(sandbox_id):
            if scope["type"] == "websocket":   # a relay can't set a cookie: no sandbox, so the route refuses
                return await self.app(scope, receive, send)
            sandbox_id, issue_cookie = new_id(), True   # never a file path built from client input
        state["storage"] = await run_in_threadpool(resolve, self.settings, str(sandbox_id))

        if not issue_cookie:
            return await self.app(scope, receive, send)

        cookie = SimpleCookie()
        cookie["demo_sid"] = str(sandbox_id)
        cookie["demo_sid"].update({"max-age": _MONTH, "path": "/", "samesite": "Lax", "httponly": True,
                                   "secure": conn.url.scheme == "https"})
        header = cookie["demo_sid"].OutputString().encode("latin-1")

        async def send_with_cookie(message: Message) -> None:
            if message["type"] == "http.response.start":
                message["headers"] = [*message.get("headers", []), (b"set-cookie", header)]
            await send(message)

        await self.app(scope, receive, send_with_cookie)
