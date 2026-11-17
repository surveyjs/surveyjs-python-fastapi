"""Edit Forms Together rooms: the saved definition a room started from, every Creator record since (in arrival
order) and the people in it. app/routes/edit_together.py runs the relay; this file holds the rooms."""

import asyncio
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends, WebSocket
from starlette.requests import HTTPConnection

from app.relay.connection import Connection
from app.relay.room_key import snapshot_path, write_snapshot

SLOTS = [1, 2, 3, 4, 6, 7, 8, 9]
"""Colour slots, skipping 5 (yellow is unreadable with white text); 0 is gray and never assigned."""

PALETTE = ["#808080", "#1570EF", "#CA4FFB", "#19B35C", "#19B394", "#F9C50B", "#F99130", "#F1529C", "#02ADEB", "#4E6198"]
"""The colour of each slot: the same values as survey-core's --sjs2-color-utility-user-bg-color-N."""


class EditRoom:
    def __init__(self, seed: Any, snapshot: Path | None) -> None:
        self.seed = seed
        self.log: list[Any] = []        # append-only: never deduplicated, replayed in this order
        self.clients: list[Connection] = []
        self.drop_timer: asyncio.TimerHandle | None = None
        self._snapshot = snapshot

    def add(self, websocket: WebSocket, name: str) -> Connection:
        taken = {client.slot for client in self.clients}
        slot = next((slot for slot in SLOTS if slot not in taken), SLOTS[len(self.clients) % len(SLOTS)])
        client = Connection(websocket, name, slot)
        self.clients.append(client)
        self._changed()
        return client

    @staticmethod
    def color(client: Connection) -> str:
        return PALETTE[client.slot]

    def peer(self, client: Connection) -> dict[str, Any]:
        """Creator's plugin paints rings and cursors from `color`, so each peer carries it next to colorIndex."""
        return {"clientId": client.id, "name": client.name, "colorIndex": client.slot, "color": self.color(client),
                "state": client.state}

    def roster(self, other_than: Connection) -> list[dict[str, Any]]:
        """Everyone else who has shared their presence."""
        return [self.peer(c) for c in self.clients if c is not other_than and c.state is not None]

    def broadcast(self, sender: Connection, message: dict[str, Any]) -> None:
        """Send to everyone in the room except the sender."""
        for client in self.clients:
            if client is not sender:
                client.send(message)
        if message["type"] != "presence":
            self._changed()

    def _changed(self) -> None:
        """Demo only: the room's state for the Data panel (DEMO_MODE=true)."""
        if self._snapshot is not None:
            title = self.seed.get("title") if isinstance(self.seed, dict) else None
            write_snapshot(self._snapshot, {"participants": len(self.clients), "seed title": title,
                                            "records in the log": len(self.log)})


class EditRooms:
    """Every open room, by room key. One per app, created in app/main.py."""

    def __init__(self, snapshots: Path | None) -> None:
        self._rooms: dict[str, EditRoom] = {}
        self._snapshots = snapshots   # demo mode: storage/relay; otherwise None

    def join(self, key: str, seed: Callable[[], Any]) -> EditRoom:
        """The open room, or a new one seeded with the saved definition."""
        room = self._rooms.get(key)
        if room is None:
            snapshot = snapshot_path(self._snapshots, key, "edit") if self._snapshots else None
            room = self._rooms[key] = EditRoom(seed(), snapshot=snapshot)
        if room.drop_timer is not None:   # back within 2 s: keep the room
            room.drop_timer.cancel()
            room.drop_timer = None
        return room

    def leave(self, key: str, client: Connection) -> None:
        """Tell the others; the log lives until the room empties, and 2 s more."""
        room = self._rooms.get(key)
        if room is None or client not in room.clients:
            return
        room.clients.remove(client)
        client.close()
        room.broadcast(client, {"type": "presence-leave", "clientId": client.id})
        if not room.clients:
            room.drop_timer = asyncio.get_running_loop().call_later(2, self._drop_if_empty, key, room)

    def _drop_if_empty(self, key: str, room: EditRoom) -> None:
        if not room.clients and self._rooms.get(key) is room:
            del self._rooms[key]


def get_edit_rooms(conn: HTTPConnection) -> EditRooms:
    return conn.app.state.edit_rooms


Rooms = Annotated[EditRooms, Depends(get_edit_rooms)]
"""The app's edit-together rooms."""
