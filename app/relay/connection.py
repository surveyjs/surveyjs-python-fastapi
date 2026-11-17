"""One participant's WebSocket in a relay room. Starlette doesn't allow two send_text() calls on one socket at
the same time, and a broadcast reaches many sockets at once, so each connection has a queue that one task
sends from, in order. Used by app/relay/fill_room.py and edit_room.py."""

import asyncio
import json
import logging
import secrets
from typing import Any

from fastapi import WebSocket

from app.integration.stored_json import dumps

log = logging.getLogger("app.relay")


class Connection:
    def __init__(self, websocket: WebSocket, name: str, slot: int) -> None:
        self.websocket = websocket
        self.id = secrets.token_hex(8)
        self.name = name
        self.slot = slot
        self.state: Any = None          # the last presence this participant shared (retained), or None
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._sender = asyncio.create_task(self._send_queued())

    def send(self, message: dict[str, Any]) -> None:
        """Queue a message; it goes out after everything queued before it."""
        self._queue.put_nowait(dumps(message))

    @property
    def backlog(self) -> int:
        """Messages queued but not sent yet: a slow peer's backlog grows."""
        return self._queue.qsize()

    async def _send_queued(self) -> None:
        try:
            while True:
                await self.websocket.send_text(await self._queue.get())
        except asyncio.CancelledError:
            raise
        except Exception as error:   # the socket closed under us: the route's finally block cleans up
            log.debug("relay: stopped sending to %s: %s", self.id, error)

    def close(self) -> None:
        self._sender.cancel()


def _reject_constant(name: str) -> Any:
    raise ValueError(name)


def parse(raw: str) -> Any:
    """A message as JSON, or None. Objects stay objects: {} is relayed as {}."""
    try:
        return json.loads(raw, parse_constant=_reject_constant)
    except (ValueError, RecursionError):
        return None


def display_name(name: str | None, fallback: str) -> str:
    """The name from ?name=, trimmed to 32 characters, or the user's name."""
    return (name or "").strip()[:32] or fallback
