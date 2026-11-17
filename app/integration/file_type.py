"""The type of an upload by its first bytes, never by the client's Content-Type or file name: PNG, JPEG, GIF,
WebP or PDF, the formats SurveyJS Server's isSupportedDocument() accepts (it finds %PDF in the first 4 KB,
as here). Used by store-files and extract-from-paper."""


def detect_type(head: bytes) -> str | None:
    """"image/png", "image/jpeg", "image/gif", "image/webp", "application/pdf", or None for anything else."""
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if head.startswith(b"RIFF") and head[8:12] == b"WEBP":
        return "image/webp"
    if b"%PDF" in head[:4096]:
        return "application/pdf"
    return None
