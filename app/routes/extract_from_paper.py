"""Extract Responses from Documents: a blank, fillable work order, and the answers the SurveyJS service reads
from a completed one. Nothing is saved here: the visitor reviews the draft and the page posts it to
/api/responses."""

import base64
import json
from contextlib import suppress
from typing import Annotated, Any

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import Response

from app.db import Db
from app.integration.file_type import detect_type
from app.integration.surveyjs_service import SurveyJs

router = APIRouter()

MAX_BYTES = 5 * 1024 * 1024


# region sjs:extract-from-paper.template
# Generate a blank, fillable PDF using the same schema as extraction
@router.get("/api/work-orders/blank.pdf")
async def blank_work_order(db: Db, surveyjs: SurveyJs) -> Response:
    form = db.execute("SELECT json FROM forms WHERE key = 'work-order'").fetchone()
    if form is None:
        raise HTTPException(404, "Unknown work order form")
    pdf = await surveyjs.post("/pdf", {"schema": json.loads(form["json"])}, timeout=60)
    if (pdf.status_code != 200 or not pdf.headers.get("content-type", "").startswith("application/pdf")
            or not pdf.content.startswith(b"%PDF-")):
        surveyjs.unexpected("/pdf", pdf)

    return Response(pdf.content, media_type="application/pdf", headers={
        "Content-Disposition": 'attachment; filename="work-order.pdf"', "Cache-Control": "private, no-store"})
# endregion


# region sjs:extract-from-paper.server
# POST /api/work-orders/extract — send the uploaded scan to the SurveyJS service; return a draft response
@router.post("/api/work-orders/extract")
async def extract_work_order(db: Db, surveyjs: SurveyJs, scan: Annotated[UploadFile | str | None, File()] = None) -> Any:
    if scan is None:
        raise HTTPException(400, 'Upload the scan in a field named "scan"')
    if isinstance(scan, str) or len(raw := await scan.read(MAX_BYTES + 1)) > MAX_BYTES:   # a text field isn't a file
        raise HTTPException(413, "The scan must be a file of 5 MB or less")
    if detect_type(raw) is None:   # by the first bytes, never the client's Content-Type
        raise HTTPException(400, "The file is not a PDF, PNG, JPEG, WebP or GIF document")
    schema = json.loads(db.execute("SELECT json FROM forms WHERE key = 'work-order'").fetchone()["json"])
    out = await surveyjs.post("/extract", {"schema": schema, "document": base64.b64encode(raw).decode()}, timeout=120)
    result: Any = None
    with suppress(ValueError):   # JSON with base64 went out, not multipart; an answer that isn't JSON fails closed
        result = json.loads(out.content)
    match out.status_code, result:   # nothing is saved: a person reviews the draft
        case 200, {"data": dict() as answers}:
            return {"answers": answers, "confidence": result.get("confidence", []), "uniqueId": result.get("uniqueId")}
        case 400, {"error": "INVALID_DOCUMENT"}:
            raise HTTPException(400, "The file is not a PDF, PNG, JPEG, WebP or GIF document")
        case 503, {"error": "AI_NOT_CONFIGURED"}:
            raise HTTPException(503, "The SurveyJS service has no AI provider configured")
        case 502, {"error": "EXTRACTION_FAILED"}:
            raise HTTPException(502, "Could not extract the response from the document")
    surveyjs.unexpected("/extract", out, log_body=False)   # fail closed, logged by status only
# endregion
