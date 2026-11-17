"""Demo only: an hourly task, started in the app's lifespan in demo mode, that removes visitor sandboxes unused
for 24 hours. FastAPI has no scheduler; one asyncio task in the app's one process is enough here."""

import asyncio
import logging

from app.demo.sandbox import prune
from app.settings import Settings

log = logging.getLogger("app.demo")
INTERVAL_SECONDS = 3600


async def prune_hourly(settings: Settings) -> None:
    while True:
        try:
            removed = await asyncio.to_thread(prune, settings)
            if removed:
                log.info("Removed %d visitor sandboxes unused for 24 hours", removed)
        except OSError:
            log.exception("Pruning visitor sandboxes failed")
        await asyncio.sleep(INTERVAL_SECONDS)
