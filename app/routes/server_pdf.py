"""Generate PDFs: GET /api/claims/{id}/pdf, a claim filled into its definition by the SurveyJS service."""

import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from app.db import Db
from app.integration.surveyjs_service import SurveyJs
from app.settings import ROOT

router = APIRouter()

DEFINITIONS = ROOT / "shared" / "definitions"


# region sjs:server-pdf.server
# GET /api/claims/{id}/pdf — ask the SurveyJS service for the filled form and pass the PDF through
@router.get("/api/claims/{id}/pdf")
async def claim_pdf(id: int, db: Db, surveyjs: SurveyJs) -> Response:
    claim = db.execute("SELECT definition_version, data FROM responses WHERE form_id = 'claim' AND id = ?", (id,)).fetchone()
    if claim is None:
        raise HTTPException(404, "Unknown claim")
    match claim["definition_version"]:   # use the schema version recorded with the response
        case "v1" | "v2" as version:
            definition = (DEFINITIONS / f"relational-storage.{version}.json").read_text(encoding="utf-8")
        case None:
            definition = db.execute("SELECT json FROM forms WHERE key = 'claim'").fetchone()["json"]
        case _:
            raise HTTPException(409, "The schema version for this claim is unavailable")

    pdf = await surveyjs.post("/pdf", {"schema": json.loads(definition), "response": json.loads(claim["data"])}, timeout=60)
    if (pdf.status_code != 200 or not pdf.headers.get("content-type", "").startswith("application/pdf")
            or not pdf.content.startswith(b"%PDF-")):
        surveyjs.unexpected("/pdf", pdf)

    return Response(pdf.content, media_type="application/pdf", headers={
        "Content-Disposition": f'inline; filename="claim-{id}.pdf"', "Cache-Control": "private, no-store"})
# endregion
