"""Who is asking, and may they? The examples call these and nothing else, so this is where your real checks go."""

import sqlite3
from dataclasses import dataclass
from typing import Annotated, Literal

from fastapi import Depends
from starlette.requests import HTTPConnection

from app.db import Db
from app.demo.users import demo_user_key


@dataclass(frozen=True)
class User:
    id: int
    key: str
    name: str
    email: str
    plan: str        # "basic" or "premium": a variable the forms read as {user.plan}
    is_editor: bool  # editors may save definitions and variable presets (can(user, "edit-forms"))


def find_user(db: sqlite3.Connection, key: str | None) -> User | None:
    row = db.execute("SELECT id, key, name, email, plan, is_editor FROM users WHERE key = ?", (key or "",)).fetchone()
    return User(row["id"], row["key"], row["name"], row["email"], row["plan"], bool(row["is_editor"])) if row else None


def get_current_user(conn: HTTPConnection, db: Db) -> User | None:
    """The signed-in user, or None. HTTPConnection, not Request, so the WebSocket relays use it too.

    Demo only: the demo_user cookie picks Alice, Bob or nobody (app/demo/users.py). A real app reads its
    session here, or uses an OAuth2PasswordBearer / JWT dependency, and returns its own user.
    """
    return find_user(db, demo_user_key(conn))


CurrentUser = Annotated[User | None, Depends(get_current_user)]


def can(user: User | None, ability: Literal["edit-forms"]) -> bool:
    """May this user do it? Saving definitions (creator-load-save, lint-definition) and variable presets is an
    admin action. Your real permission check goes here: roles, teams, form ownership…"""
    if ability == "edit-forms":
        return user is not None and user.is_editor
    raise ValueError(f"Unknown ability {ability}")


def can_read_file(user: User | None, file: sqlite3.Row) -> bool:
    """May this user read this uploaded file (store-files)? Any signed-in user may here; real apps check
    ownership, for example file["owner_id"] == user.id. A denial answers 404, so it doesn't confirm the file exists."""
    return user is not None and file is not None
