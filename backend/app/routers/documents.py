import re

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app import crud, storage
from app.database import get_db
from app.models import Application, Document
from app.schemas import DocumentOut

router = APIRouter(prefix="/api/applications/{reference_id}/documents", tags=["documents"])

_UNSAFE_HEADER_CHARS = re.compile(r'[\r\n"]')


def _get_application_or_404(db: Session, reference_id: str) -> Application:
    application = crud.get_application_by_reference(db, reference_id)
    if application is None:
        # US-05 DoD: an upload can never be linked to a nonexistent application,
        # because there is no application to attach it to in the first place.
        raise HTTPException(status_code=404, detail="No application found with that reference ID.")
    return application


def _to_document_out(reference_id: str, document: Document) -> DocumentOut:
    return DocumentOut.model_validate(
        {
            "id": document.id,
            "original_filename": document.original_filename,
            "content_type": document.content_type,
            "size_bytes": document.size_bytes,
            "uploaded_at": document.uploaded_at,
            "preview_url": f"/api/applications/{reference_id}/documents/{document.id}/file",
        }
    )


@router.post("", response_model=DocumentOut, status_code=201)
def upload_document(
    reference_id: str, file: UploadFile = File(...), db: Session = Depends(get_db)
) -> DocumentOut:
    # A plain `def` (not `async def`) so FastAPI runs this in a threadpool —
    # storage.save_upload() does a blocking file read, which would otherwise
    # stall the event loop.
    application = _get_application_or_404(db, reference_id)
    stored = storage.save_upload(application.id, file)
    original_filename = file.filename or "document"
    document = crud.create_document(db, application, original_filename=original_filename, stored=stored)
    return _to_document_out(reference_id, document)


@router.get("", response_model=list[DocumentOut])
def list_documents(reference_id: str, db: Session = Depends(get_db)) -> list[DocumentOut]:
    application = _get_application_or_404(db, reference_id)
    documents = crud.list_documents(db, application.id)
    return [_to_document_out(reference_id, doc) for doc in documents]


@router.get("/{document_id}/file")
def get_document_file(reference_id: str, document_id: int, db: Session = Depends(get_db)) -> FileResponse:
    application = _get_application_or_404(db, reference_id)
    document = crud.get_document(db, application.id, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="No document found for this application.")

    absolute_path = storage.resolve_path(document.file_path)
    if not absolute_path.is_file():
        raise HTTPException(status_code=404, detail="The stored file could not be found.")

    safe_filename = _UNSAFE_HEADER_CHARS.sub("", document.original_filename)
    return FileResponse(
        path=absolute_path,
        media_type=document.content_type,
        # "inline" (not "attachment") is what lets the browser render the
        # file directly instead of forcing a download (US-06 AC).
        headers={"Content-Disposition": f'inline; filename="{safe_filename}"'},
    )
