import logging
import re

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app import crud, pipeline, storage
from app.database import get_db
from app.models import Application, ApplicationStatus, Document, DocumentType
from app.schemas import DocumentOut

logger = logging.getLogger("onboardiq")

router = APIRouter(prefix="/api/applications/{reference_id}/documents", tags=["documents"])

_UNSAFE_HEADER_CHARS = re.compile(r'[\r\n"]')

# US-07 AC: replace is only available while DRAFT or INFO_REQUESTED; the
# very first upload (SUBMITTED, before any document exists yet) must also be
# allowed since that's the normal intake flow. Anything else — PROCESSING,
# PENDING_REVIEW, or a final decision — blocks any new upload, whether it
# would be the first document or a replacement.
_UPLOAD_ALLOWED_STATUSES = (
    ApplicationStatus.DRAFT,
    ApplicationStatus.SUBMITTED,
    ApplicationStatus.INFO_REQUESTED,
)


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
            "version": document.version,
            "superseded": document.superseded,
            "declared_type": document.declared_type,
            "detected_type": document.detected_type,
            "type_mismatch": document.type_mismatch,
        }
    )


@router.post("", response_model=DocumentOut, status_code=201)
def upload_document(
    reference_id: str,
    file: UploadFile = File(...),
    declared_type: DocumentType | None = Form(default=None),
    db: Session = Depends(get_db),
) -> DocumentOut:
    # A plain `def` (not `async def`) so FastAPI runs this in a threadpool —
    # storage.save_upload() does a blocking file read, which would otherwise
    # stall the event loop.
    application = _get_application_or_404(db, reference_id)

    if application.status not in _UPLOAD_ALLOWED_STATUSES:
        # US-07 AC: "Replacement blocked once the application is under
        # review" — and, more generally, no new document (first or
        # replacement) is accepted once processing has started or a
        # decision has been recorded.
        raise HTTPException(
            status_code=409,
            detail=(
                "A document cannot be uploaded or replaced while this application is being processed, "
                "under review, or has already been decided."
            ),
        )

    stored = storage.save_upload(application.id, file)
    original_filename = file.filename or "document"
    document = crud.create_document(
        db, application, original_filename=original_filename, stored=stored, declared_type=declared_type
    )

    # US-09 AC: extraction runs on SUBMISSION. A document attached while
    # still DRAFT (US-07/US-08 allow uploading before the form is finished)
    # has nothing yet to cross-verify against — application fields may still
    # be unset — so the pipeline is deferred until crud.submit_draft_application
    # actually submits it (see routers/applications.py submit_draft).
    if application.status != ApplicationStatus.DRAFT:
        try:
            # US-25: this is also what re-triggers extraction/verification on
            # a resubmission after INFO_REQUESTED — process_document doesn't
            # distinguish a first attempt from a resubmission, it just always
            # processes whatever document it's given.
            pipeline.process_document(db, application, document)
        except Exception:
            # Outermost safety net: pipeline.process_document already
            # handles every AI/parsing failure internally, but a bug here
            # must still never turn document upload into a server error for
            # the applicant (CLAUDE.md: graceful degradation).
            logger.exception("Pipeline failed unexpectedly for application %s", reference_id)
            db.rollback()
            application.status = ApplicationStatus.PENDING_REVIEW
            db.commit()

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
