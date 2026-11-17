"""Demo only: in demo mode a room belongs to one visitor sandbox, so its key is "<demo_sid>:<id>", and visitors
in different sandboxes never share a room. Outside demo mode the key is the plain record or form id. The
relays get their key from these dependencies, outside their regions; the Data panel names snapshots with the
same helper."""

import hashlib
import json
from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends, WebSocket

from app.db import get_storage
from app.integration.stored_json import timestamp


def room_key(sandbox_id: str | None, id: str) -> str:
    """The room key for a record or form id, in a sandbox (demo mode) or not."""
    return f"{sandbox_id}:{id}" if sandbox_id else id


def _for_connection(websocket: WebSocket, id: str) -> str | None:
    """The connection's room key, or None in demo mode without a valid demo_sid (the relay then refuses it)."""
    if not websocket.app.state.settings.demo_mode:
        return id
    sandbox_id = get_storage(websocket).sandbox_id
    return room_key(sandbox_id, id) if sandbox_id else None


def for_record(websocket: WebSocket, record_id: str) -> str | None:
    return _for_connection(websocket, record_id)


def for_form(websocket: WebSocket, form_id: str) -> str | None:
    return _for_connection(websocket, form_id)


FillRoomKey = Annotated[str | None, Depends(for_record)]
EditRoomKey = Annotated[str | None, Depends(for_form)]


def snapshot_path(relay_dir: Path, key: str, relay: str = "fill") -> Path:
    """Where a relay writes a room snapshot for the Data panel (app/demo/stored.py reads it). Room keys contain
    ":" (invalid in Windows file names) and ids from the URL, so the file is named by the key's SHA-256."""
    name = f"{hashlib.sha256(key.encode()).hexdigest()}.json"
    return relay_dir / (name if relay == "fill" else f"{relay}-{name}")


def write_snapshot(path: Path, snapshot: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({**snapshot, "updatedAt": timestamp()}, indent=4, ensure_ascii=False), encoding="utf-8")
