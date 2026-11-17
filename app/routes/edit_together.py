"""Edit Forms Together: the relay behind CollaborationPlugin from survey-creator-core/collaboration, a WebSocket
route at /ws/forms/{form_id}. Wire protocol: https://github.com/surveyjs/collaborative-form-editing
(PROTOCOL.md). The rooms are in app/relay/edit_room.py. Saving is unchanged: Creator's Save button calls
PUT /api/forms/{id} (creator-load-save).
"""

import json
from sqlite3 import Connection
from typing import Annotated, Any

from fastapi import APIRouter, Path, WebSocket, WebSocketDisconnect

from app.auth import CurrentUser, can
from app.db import Db
from app.relay.connection import display_name, parse
from app.relay.edit_room import Rooms
from app.relay.room_key import EditRoomKey

router = APIRouter()

FormId = Annotated[str, Path(pattern=r"^[A-Za-z0-9_-]{1,64}$")]


def saved_definition(db: Connection, form_id: str) -> Any:
    """The definition saved through creator-load-save, or an empty one for a new form."""
    form = db.execute("SELECT json FROM forms WHERE key = ?", (form_id,)).fetchone()
    return json.loads(form["json"]) if form else {}


# region sjs:edit-together.server
# The same kind of relay as Fill Forms Together, keeping an append-only log instead of a value map:
# Creator records must be replayed in order. It runs in this app's process, on its port.
@router.websocket("/ws/forms/{form_id}")
async def edit_together(websocket: WebSocket, form_id: FormId, user: CurrentUser, rooms: Rooms,
                        room_key: EditRoomKey, db: Db, name: str = "") -> None:
    if not can(user, "edit-forms") or room_key is None:   # like saving, editing together is for editors
        await websocket.close(code=1008)                  # before accept(): the browser sees a refused handshake
        return
    await websocket.accept()
    room = rooms.join(room_key, lambda: saved_definition(db, form_id))   # seed = the saved definition
    client = room.add(websocket, display_name(name, user.name))
    client.send({"type": "init", "clientId": client.id, "colorIndex": client.slot, "color": room.color(client),
                 "seed": room.seed, "log": room.log})   # init first
    if peers := room.roster(client):
        client.send({"type": "presence-sync", "peers": peers})
    try:
        async for raw in websocket.iter_text():
            message = parse(raw)   # records stay opaque: {} is relayed as {}
            if not isinstance(message, dict):
                continue
            if message.get("type") == "append" and message.get("payload") is not None:   # append, then fan out
                room.log.append(message["payload"])
                room.broadcast(client, {"type": "record", "from": client.id, "payload": message["payload"]})
            elif message.get("type") == "presence" and message.get("state") is not None and len(raw) <= 4096:
                client.state = message["state"]
                room.broadcast(client, {"type": "presence", "peer": room.peer(client)})
            # unknown types: ignore
    except WebSocketDisconnect:
        pass
    finally:
        rooms.leave(room_key, client)   # presence-leave to the others; the log lives until the room empties
# endregion
