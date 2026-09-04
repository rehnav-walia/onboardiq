from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Application, ApplicationStatus, Document
from app.schemas import ApplicationCreate
from app.storage import StoredFile


def create_application(db: Session, payload: ApplicationCreate) -> Application:
    """Creates the row, then derives the reference ID from the row's own
    primary key so uniqueness is guaranteed by the same DB-level constraint
    that guarantees the primary key is unique (US-01 DoD)."""
    settings = get_settings()
    submitted_at = datetime.now(timezone.utc)

    application = Application(
        status=ApplicationStatus.SUBMITTED,
        submitted_at=submitted_at,
        full_name=payload.full_name,
        date_of_birth=payload.date_of_birth,
        id_number=payload.id_number,
        address=payload.address,
        email=payload.email,
        phone=payload.phone,
        account_type=payload.account_type,
        reference_id="",  # placeholder until we have an id; overwritten below
    )
    db.add(application)
    db.flush()  # assigns application.id without committing

    application.reference_id = f"{settings.reference_id_prefix}-{submitted_at.year}-{application.id:05d}"
    db.commit()
    db.refresh(application)
    return application


def get_application_by_reference(db: Session, reference_id: str) -> Application | None:
    return db.query(Application).filter(Application.reference_id == reference_id).first()


def create_document(db: Session, application: Application, original_filename: str, stored: StoredFile) -> Document:
    document = Document(
        application_id=application.id,
        original_filename=original_filename,
        content_type=stored.content_type,
        file_path=stored.relative_path,
        size_bytes=stored.size_bytes,
        uploaded_at=datetime.now(timezone.utc),
    )
    db.add(document)
    db.commit()
    db.refresh(document)
    return document


def list_documents(db: Session, application_id: int) -> list[Document]:
    return (
        db.query(Document)
        .filter(Document.application_id == application_id)
        .order_by(Document.uploaded_at.asc())
        .all()
    )


def get_document(db: Session, application_id: int, document_id: int) -> Document | None:
    return (
        db.query(Document)
        .filter(Document.application_id == application_id, Document.id == document_id)
        .first()
    )
