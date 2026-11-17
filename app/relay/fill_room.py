"""Fill Forms Together rooms: the definition a room hands out, the latest value of every answer and the people
in it. app/routes/fill_together.py runs the relay; this file holds the rooms."""

import asyncio
import secrets
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends, WebSocket
from starlette.requests import HTTPConnection

from app.relay.connection import Connection
from app.relay.room_key import snapshot_path, write_snapshot

SLOW_PEER_BACKLOG = 64   # queued messages: a cursor move may be dropped for a peer this far behind


class FillRoom:
    def __init__(self, seed: Any, values: dict[str, Any], snapshot: Path | None) -> None:
        self.seed = seed
        self.values = dict(values)               # question key => latest value; last write wins
        self.clients: list[Connection] = []
        self.response_id: int | None = None      # the response saved in this room session, once someone completes
        self.session_id = secrets.token_hex(16)  # 32 random hex characters per room instance
        self.lock = asyncio.Lock()               # one complete at a time: the room saves once
        self.drop_timer: asyncio.TimerHandle | None = None
        self._snapshot = snapshot

    def add(self, websocket: WebSocket, name: str) -> Connection:
        """A new participant, on the lowest colour slot nobody in the room holds, from 1."""
        taken = {client.slot for client in self.clients}
        slot = next(slot for slot in range(1, len(self.clients) + 2) if slot not in taken)
        client = Connection(websocket, name, slot)
        self.clients.append(client)
        self._changed()
        return client

    @staticmethod
    def color_index(client: Connection) -> int:
        """Shown as 1..9 (0 means "unknown")."""
        return 1 + (client.slot - 1) % 9

    def peer(self, client: Connection, state: Any) -> dict[str, Any]:
        return {"clientId": client.id, "name": client.name, "colorIndex": self.color_index(client), "state": state}

    def roster(self, other_than: Connection) -> list[dict[str, Any]]:
        """Everyone else who has shared a retained presence."""
        return [self.peer(c, c.state) for c in self.clients if c is not other_than and c.state is not None]

    def broadcast(self, sender: Connection, message: dict[str, Any], droppable: bool = False) -> None:
        """Send to everyone in the room except the sender: nobody gets their own echo. A non-retained presence
        update (a cursor move) may be dropped for a peer that is falling behind."""
        for client in self.clients:
            if client is not sender and not (droppable and client.backlog > SLOW_PEER_BACKLOG):
                client.send(message)
        if message["type"] != "peer":
            self._changed()

    def send_all(self, message: dict[str, Any]) -> None:
        for client in self.clients:
            client.send(message)
        self._changed()

    def _changed(self) -> None:
        """Demo only: the room's state for the Data panel (DEMO_MODE=true)."""
        if self._snapshot is not None:
            write_snapshot(self._snapshot, {"participants": len(self.clients), "values": self.values,
                                            "responseId": self.response_id})


class FillRooms:
    """Every open room, by room key. One per app, created in app/main.py."""

    def __init__(self, snapshots: Path | None) -> None:
        self._rooms: dict[str, FillRoom] = {}
        self._snapshots = snapshots   # demo mode: storage/relay; otherwise None

    def join(self, key: str, seed: Callable[[], tuple[Any, dict[str, Any]]]) -> FillRoom:
        """The open room, or a new one seeded with the definition and the saved answers."""
        room = self._rooms.get(key)
        if room is None:
            snapshot = snapshot_path(self._snapshots, key) if self._snapshots else None
            room = self._rooms[key] = FillRoom(*seed(), snapshot=snapshot)
        if room.drop_timer is not None:   # back within 2 s: keep the room
            room.drop_timer.cancel()
            room.drop_timer = None
        return room

    def leave(self, key: str, client: Connection) -> None:
        """Tell the others, and drop the room 2 s after the last person leaves."""
        room = self._rooms.get(key)
        if room is None or client not in room.clients:
            return
        room.clients.remove(client)
        client.close()
        room.broadcast(client, {"type": "peer-left", "clientId": client.id})
        if not room.clients:
            room.drop_timer = asyncio.get_running_loop().call_later(2, self._drop_if_empty, key, room)

    def _drop_if_empty(self, key: str, room: FillRoom) -> None:
        if not room.clients and self._rooms.get(key) is room:
            del self._rooms[key]


def get_fill_rooms(conn: HTTPConnection) -> FillRooms:
    return conn.app.state.fill_rooms


Rooms = Annotated[FillRooms, Depends(get_fill_rooms)]
"""The app's fill-together rooms."""
