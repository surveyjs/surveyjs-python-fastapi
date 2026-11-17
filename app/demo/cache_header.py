"""Demo only: adds X-Demo-Cache: hit / miss / fallback to GET /api/countries, so the requests log shows where
the list came from. It notes whether the cache held the list before the route ran, and looks at what the
cache holds when the answer starts: "fallback" wins whenever the bundled list is served, also while it is
cached. app/routes/choices_from_web.py stays as the docs show it. Pure ASGI, wrapped around the app in
app/main.py; delete it with app/demo/ when you copy an example."""

import json

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.integration.ttl_cache import TtlCache
from app.settings import ROOT

BUNDLED = json.loads((ROOT / "shared" / "seed" / "countries.json").read_text(encoding="utf-8"))


class DemoCacheHeader:
    def __init__(self, app: ASGIApp, cache: TtlCache) -> None:
        self.app = app
        self.cache = cache

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"] != "/api/countries":
            return await self.app(scope, receive, send)
        cached_before = self.cache.has("countries")

        async def send_with_header(message: Message) -> None:
            if message["type"] == "http.response.start" and message["status"] == 200:
                state = "fallback" if self.cache.get("countries") == BUNDLED else "hit" if cached_before else "miss"
                message["headers"] = [*message.get("headers", []), (b"x-demo-cache", state.encode())]
            await send(message)

        await self.app(scope, receive, send_with_header)
