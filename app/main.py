"""The FastAPI app: settings, the lifespan, the middleware, JSON errors for everything under /api, the shared
files, the pages, then each example's router in the order of the integration docs.

`python serve.py` starts it (port check, build line); `uvicorn app.main:app` and `fastapi dev` work too.
Tests call create_app() with their own Settings.
"""

import asyncio
import logging
import mimetypes
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

import httpx2
from fastapi import Depends, FastAPI
from fastapi.staticfiles import StaticFiles

from app import errors, pages
from app.body_limit import BodyLimit
from app.demo import ai_limit, stored, upload_limit
from app.demo.cache_header import DemoCacheHeader
from app.demo.pruner import prune_hourly
from app.demo.sandbox import DemoSandbox
from app.integration.ttl_cache import TtlCache
from app.relay.edit_room import EditRooms
from app.relay.fill_room import FillRooms
from app.routes import (
    ai_translation,
    async_functions,
    choices_from_web,
    creator_load_save,
    dashboard,
    edit_together,
    extract_from_paper,
    fill_together,
    lint_definition,
    load_definition_variables_data,
    relational_storage,
    resume_progress,
    save_response,
    server_pdf,
    store_files,
    validate_response,
    variable_presets,
)
from app.seed import seed
from app.settings import ROOT, Settings

# Python reads MIME types from the Windows registry, where .js or .mjs can be text/plain: browsers refuse to
# run a module served that way. Set the ones the pages need before anything is mounted.
for _type, _extension in (("text/javascript", ".js"), ("text/javascript", ".mjs"), ("image/svg+xml", ".svg"),
                          ("font/woff2", ".woff2"), ("text/css", ".css"), ("application/json", ".json")):
    mimetypes.add_type(_type, _extension)

log = logging.getLogger("app")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
    if seed(settings.database_path):
        log.info("Created and seeded %s", settings.database_path)
    settings.files_dir.mkdir(parents=True, exist_ok=True)

    # One HTTP client for the SurveyJS service, the AI provider and restcountries.com: connections are reused
    async with httpx2.AsyncClient(follow_redirects=False) as http:
        app.state.http = http
        # Demo only: remove visitor sandboxes unused for 24 hours, hourly
        pruner = asyncio.create_task(prune_hourly(settings)) if settings.demo_mode else None
        try:
            yield
        finally:
            if pruner is not None:
                pruner.cancel()
                with suppress(asyncio.CancelledError):
                    await pruner


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    app = FastAPI(title="SurveyJS + FastAPI", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.settings = settings
    app.state.cache = TtlCache()   # the countries list (choices-from-web)
    snapshots = settings.relay_dir if settings.demo_mode else None   # Demo only: relay rooms for the Data panel
    app.state.fill_rooms = FillRooms(snapshots)
    app.state.edit_rooms = EditRooms(snapshots)

    # Outermost first: the body limit, then (demo only) the visitor's sandbox and the countries cache header
    app.add_middleware(DemoCacheHeader, cache=app.state.cache)
    app.add_middleware(DemoSandbox, settings=settings)
    app.add_middleware(BodyLimit)
    errors.install(app)

    # Health: answers without touching the database
    @app.get("/up", include_in_schema=False)
    def up() -> dict[str, str]:
        return {"status": "ok"}

    # Shared client modules, definitions, samples and the page UI: only these four folders of shared/
    for folder in ("client", "definitions", "samples", "ui"):
        app.mount(f"/shared/{folder}", StaticFiles(directory=ROOT / "shared" / folder), name=f"shared-{folder}")
    app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")

    # Demo only: the catalog, the example pages and the Data panel
    app.include_router(pages.router)
    app.include_router(stored.router)

    # Demo only: the 5 MB upload cap and the 20 AI calls a day of the hosted demo (DEMO_MODE=true)
    demo_uploads = [Depends(upload_limit.demo_upload_limit)]
    demo_ai = [Depends(ai_limit.demo_ai_limit)]

    # Run Forms
    app.include_router(validate_response.router if settings.validate_responses else save_response.router)  # POST /api/responses
    app.include_router(load_definition_variables_data.router)   # GET /claim, GET /api/forms/{id}
    app.include_router(resume_progress.router)                  # GET|PUT|DELETE /api/progress/{form_id}
    app.include_router(store_files.router, dependencies=demo_uploads)   # POST /api/files, GET /api/files/{id}
    app.include_router(choices_from_web.router)                 # GET /api/offices, GET /api/countries
    app.include_router(async_functions.router)                  # GET /api/customers/exists, GET /api/shipping
    app.include_router(relational_storage.router)               # POST /api/claims
    app.include_router(fill_together.router)                    # WebSocket /ws/rooms/{record_id}

    # Analyze Results with Dashboard
    app.include_router(dashboard.router)                        # GET /api/responses

    # Edit Forms in Survey Creator (creator-uploads reuses POST /api/files from store-files)
    app.include_router(lint_definition.router if settings.lint_definitions else creator_load_save.router)  # PUT /api/forms/{id}
    app.include_router(ai_translation.router, dependencies=demo_ai)   # POST /api/translate
    app.include_router(variable_presets.router)                 # GET|PUT /api/variable-presets/{form_id}
    app.include_router(edit_together.router)                    # WebSocket /ws/forms/{form_id}

    # Run Server-Side Workflows (validate-response and lint-definition are switched in above)
    app.include_router(server_pdf.router)                       # GET /api/claims/{id}/pdf
    app.include_router(extract_from_paper.router, dependencies=demo_uploads + demo_ai)   # GET /api/work-orders/blank.pdf, POST …/extract
    return app


app = create_app()
