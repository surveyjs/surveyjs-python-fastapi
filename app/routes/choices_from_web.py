"""Load Choices from Web: GET /api/offices?region= and GET /api/countries, a proxy for restcountries.com."""

import json
import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.db import Db
from app.integration.http import HttpClient
from app.integration.ttl_cache import Cache
from app.settings import ROOT

router = APIRouter()
log = logging.getLogger("app")

BUNDLED_COUNTRIES = ROOT / "shared" / "seed" / "countries.json"
DAY = 24 * 3600


# region sjs:choices-from-web.server
# GET /api/offices?region= — {region} from the form arrives as a query parameter
@router.get("/api/offices")
def offices(db: Db, region: str = "") -> list[dict[str, str]]:
    return [dict(row) for row in db.execute("SELECT id, name FROM offices WHERE region = ? ORDER BY name", (region,))]


# GET /api/countries — a proxy: the browser can't call a service without CORS, your server can
@router.get("/api/countries")
async def countries(http: HttpClient, cache: Cache) -> JSONResponse:
    countries = cache.get("countries")
    if countries is None:
        try:
            answer = await http.get("https://restcountries.com/v3.1/all", params={"fields": "name,cca2"}, timeout=5)
            countries = sorted(({"code": c["cca2"], "name": c["name"]["common"]} for c in answer.raise_for_status().json()),
                               key=lambda country: country["name"])
            cache.set("countries", countries, DAY)
        except Exception as error:   # down, or a different answer: the bundled list for 10 minutes, not a timeout each
            log.warning("restcountries.com failed (%s); serving shared/seed/countries.json", error)
            countries = json.loads(BUNDLED_COUNTRIES.read_text(encoding="utf-8"))
            cache.set("countries", countries, 10 * 60)
    return JSONResponse(countries, headers={"Cache-Control": "public, max-age=86400"})
# endregion
