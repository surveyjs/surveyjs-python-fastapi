"""Demo only: on the hosted demo (DEMO_MODE=true), /api/translate and /api/work-orders/extract allow 20 calls
per visitor (demo_sid) per UTC day. The counts live in this process (the app runs one, see README): with
several processes, keep them in a shared store such as Redis or a table. app/main.py adds this dependency to
the two routers; delete it with app/demo/ when you copy an example."""

from datetime import UTC, datetime

from fastapi import HTTPException, Request

from app.db import get_storage

LIMIT = 20
_calls: dict[str, int] = {}   # "<demo_sid>:<YYYY-MM-DD>" => count


def demo_ai_limit(request: Request) -> None:
    if not request.app.state.settings.demo_mode or request.method != "POST":
        return
    key = f"{get_storage(request).sandbox_id}:{datetime.now(UTC):%Y-%m-%d}"
    if _calls.get(key, 0) >= LIMIT:
        raise HTTPException(429, "The demo allows 20 AI calls per visitor per day")
    _calls[key] = _calls.get(key, 0) + 1
    if len(_calls) > 10_000:   # forget the oldest visitors first
        del _calls[next(iter(_calls))]
