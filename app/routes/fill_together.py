"""Fill Forms Together: the relay behind CollaborationPlugin from survey-core/collaboration, a WebSocket route at
/ws/rooms/{record_id}. Wire protocol: https://github.com/surveyjs/collaborative-form-filling (PROTOCOL.md).
The rooms are in app/relay/fill_room.py. The relay saves the finished job sheet itself, once per room session.
"""

import json
import logging
from sqlite3 import Connection
from typing import Annotated, Any

from fastapi import APIRouter, Path, WebSocket, WebSocketDisconnect
from starlette.concurrency import run_in_threadpool

from app.auth import CurrentUser
from app.db import Db
from app.integration.stored_json import insert_response
from app.relay.connection import Connection as Participant
from app.relay.connection import display_name, parse
from app.relay.fill_room import FillRoom, Rooms
from app.relay.room_key import FillRoomKey

router = APIRouter()
log = logging.getLogger("app.relay")

RecordId = Annotated[str, Path(pattern=r"^[A-Za-z0-9_-]{1,64}$")]   # the ids the reference relay accepts


def seed(db: Connection, record_id: str) -> tuple[Any, dict[str, Any]]:
    """The job sheet definition, and the saved answers when the record exists (otherwise a blank sheet)."""
    form = db.execute("SELECT json FROM forms WHERE key = 'job-sheet'").fetchone()
    saved = db.execute("SELECT data FROM responses WHERE form_id = 'job-sheet' AND id = ?", (record_id,)).fetchone()
    values = json.loads(saved["data"]) if saved else {}
    return json.loads(form["json"]) if form else {}, values if isinstance(values, dict) else {}


# region sjs:fill-together.server
# The relay runs in this app's process, on its port, and relays JSON: it never parses the definition
@router.websocket("/ws/rooms/{record_id}")
async def fill_together(websocket: WebSocket, record_id: RecordId, user: CurrentUser, rooms: Rooms,
                        room_key: FillRoomKey, db: Db, name: str = "") -> None:
    if user is None or room_key is None:   # the demo_user cookie stands in for your real session check
        await websocket.close(code=1008)   # before accept(): the browser sees a refused handshake
        return
    await websocket.accept()
    room = rooms.join(room_key, lambda: seed(db, record_id))   # the definition + the saved answers
    client = room.add(websocket, display_name(name, user.name))
    client.send({"type": "init", "clientId": client.id, "name": client.name, "colorIndex": room.color_index(client),
                 "seed": room.seed, "values": room.values, "peers": room.roster(client),
                 "sessionId": room.session_id, "responseId": room.response_id})
    try:
        async for raw in websocket.iter_text():
            message = parse(raw)   # objects stay objects: {} is relayed as {}
            if not isinstance(message, dict):
                continue
            kind = message.get("type")
            if kind == "complete" and isinstance(message.get("data"), dict):
                await complete(room, client, message["data"], db)
            elif kind == "value" and isinstance(message.get("key"), str) and room.response_id is None:
                room.values[message["key"]] = message.get("value")   # last write wins
                room.broadcast(client, {"type": "value", "from": client.id, "key": message["key"],
                                        "value": message.get("value")})
            elif kind == "presence" and message.get("state") is not None and len(raw) <= 4096:
                retain = message.get("retain") is not False   # stamp identity, relay
                if retain:
                    client.state = message["state"]
                room.broadcast(client, {"type": "peer", "retain": retain, "peer": room.peer(client, message["state"])},
                               droppable=not retain)
            # unknown types: ignore
    except WebSocketDisconnect:
        pass
    finally:
        rooms.leave(room_key, client)   # peer-left to the others; the room is dropped 2 s after the last leaves
# endregion


# region sjs:fill-together.complete
# Save once per room session and send the same confirmation to every participant
async def complete(room: FillRoom, sender: Participant, data: dict[str, Any], db: Connection) -> None:
    async with room.lock:   # two completes at once: the second waits, then finds the saved id
        if room.response_id is None:
            try:
                room.response_id = await run_in_threadpool(insert_response, db, "job-sheet", data)   # as save-response does
            except Exception:
                log.exception("fill-together: couldn't save the job sheet")
                sender.send({"type": "save-error", "error": "Couldn't save the job sheet. Please try again."})
                return
            room.values = dict(data)
    room.send_all({"type": "completed", "id": room.response_id, "data": room.values})
# endregion
