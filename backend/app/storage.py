"""KYC document storage (US-05, US-06).

File type is determined by sniffing magic bytes, never by trusting the
client-supplied filename or extension (US-05 DoD). The on-disk filename is
always a server-generated UUID — the applicant's original filename is stored
only as display metadata, never used to build a filesystem path, so there is
no path-traversal surface (US-05 DoD).
"""

from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, UploadFile

from app.config import get_settings

# (magic bytes, MIME type, extension)
_SIGNATURES: list[tuple[bytes, str, str]] = [
    (b"\xff\xd8\xff", "image/jpeg", ".jpg"),
    (b"\x89PNG\r\n\x1a\n", "image/png", ".png"),
    (b"%PDF-", "application/pdf", ".pdf"),
]


def _detect_type(header: bytes) -> tuple[str, str] | None:
    for signature, mime_type, extension in _SIGNATURES:
        if header.startswith(signature):
            return mime_type, extension
    return None


@dataclass
class StoredFile:
    relative_path: str
    content_type: str
    size_bytes: int


def save_upload(application_id: int, upload_file: UploadFile) -> StoredFile:
    settings = get_settings()

    contents = upload_file.file.read(settings.max_upload_size_bytes + 1)
    if len(contents) > settings.max_upload_size_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds the {settings.max_upload_size_mb}MB limit. Please upload a smaller file.",
        )
    if not contents:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")

    detected = _detect_type(contents[:16])
    if detected is None:
        raise HTTPException(
            status_code=400,
            detail="Unsupported file type. Please upload a JPG, PNG, or PDF file.",
        )
    content_type, extension = detected

    storage_root = Path(settings.storage_root)
    application_dir = storage_root / str(application_id)
    application_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{uuid4().hex}{extension}"
    absolute_path = application_dir / filename
    absolute_path.write_bytes(contents)

    return StoredFile(
        relative_path=str(Path(str(application_id)) / filename),
        content_type=content_type,
        size_bytes=len(contents),
    )


def resolve_path(relative_path: str) -> Path:
    settings = get_settings()
    return Path(settings.storage_root) / relative_path
