"""Demo only: on the hosted demo (DEMO_MODE=true) a file over 5 MB answers 413, before any other check of the
batch, as the reference's middleware does. Off the demo, /api/files answers 422 and the scan 413, as the
contract says. app/main.py adds this dependency to the two upload routers. It reads the form with the same
limits as the handlers: Starlette keeps the parsed form, so the handler doesn't read the body again."""

from fastapi import HTTPException, Request
from starlette.datastructures import UploadFile

MAX_BYTES = 5 * 1024 * 1024


async def demo_upload_limit(request: Request) -> None:
    if not request.app.state.settings.demo_mode or not request.headers.get("content-type", "").startswith("multipart/"):
        return
    form = await request.form(max_files=20, max_fields=20)
    if any(isinstance(value, UploadFile) and (value.size or 0) > MAX_BYTES for _, value in form.multi_items()):
        await form.close()
        raise HTTPException(413, "Files over 5 MB are not accepted on the demo")
