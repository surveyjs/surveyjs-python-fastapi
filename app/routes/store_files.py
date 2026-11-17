"""Store Files Separately: POST /api/files stores uploads, GET /api/files/{id} serves them after an access check.

Creator's uploads (creator-uploads) post to the same endpoint.
"""

import uuid

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from starlette.datastructures import UploadFile

from app.auth import CurrentUser, can_read_file
from app.db import Db, FilesDir
from app.integration.file_type import detect_type

router = APIRouter()

TYPES = {"image/png", "image/jpeg", "image/webp", "image/gif", "application/pdf"}
MAX_BYTES = 5 * 1024 * 1024


# region sjs:store-files.server
# POST /api/files — store uploads, return their ids in the same order
@router.post("/api/files")
async def store_files(request: Request, db: Db, files_dir: FilesDir) -> list[str]:
    async with request.form(max_files=20, max_fields=20) as form:   # closes the spooled uploads afterwards
        # Field "files[]", the name on every platform: PHP keeps only the last of several fields named "files"
        files = [f for f in form.getlist("files[]") if isinstance(f, UploadFile)]
        if not files:
            raise HTTPException(422, 'Upload one or more files in a field named "files[]"')
        uploads = [(f, await f.read(MAX_BYTES + 1)) for f in files]   # check the whole batch before storing any
        for file, content in uploads:
            if len(content) > MAX_BYTES:
                raise HTTPException(422, "Each file must be 5 MB or less")
            if detect_type(content) not in TYPES:                        # by the bytes, never the client's type
                raise HTTPException(422, f"{file.filename} is not a PNG, JPEG, WebP, GIF or PDF file")

    ids = []
    for file, content in uploads:
        id = str(uuid.uuid4())                                           # named by id, never by the client
        (files_dir / id).write_bytes(content)
        db.execute("INSERT INTO files (id, name, type) VALUES (?, ?, ?)", (id, file.filename, detect_type(content)))
        ids.append(id)
    return ids
# endregion


# region sjs:store-files.download
# GET /api/files/{id} — the content, for private files only; check access first
@router.get("/api/files/{id}")
def download_file(id: str, user: CurrentUser, db: Db, files_dir: FilesDir) -> FileResponse:
    file = db.execute("SELECT id, name, type FROM files WHERE id = ?", (id,)).fetchone()
    if file is None or not can_read_file(user, file):
        raise HTTPException(404)   # 404, not 403: don't confirm the file exists

    # nosniff and sandbox: an uploaded HTML or SVG never runs as this site
    return FileResponse(files_dir / file["id"], media_type=file["type"],
                        headers={"X-Content-Type-Options": "nosniff", "Content-Security-Policy": "sandbox"})
# endregion
