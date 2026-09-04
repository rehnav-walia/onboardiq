from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import (
    Application,
    ApplicationStatus,
    AuditLogEntry,
    Document,
    ExtractionResult,
    ExtractionStatus,
    MatchStatus,
    VerificationResult,
)
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


def get_latest_extraction_result(db: Session, document_id: int) -> ExtractionResult | None:
    return (
        db.query(ExtractionResult)
        .filter(ExtractionResult.document_id == document_id)
        .order_by(ExtractionResult.created_at.desc())
        .first()
    )


def create_extraction_result(
    db: Session,
    document_id: int,
    status: ExtractionStatus,
    extracted_fields: dict,
    field_confidences: dict,
    justification: str,
) -> ExtractionResult:
    result = ExtractionResult(
        document_id=document_id,
        status=status,
        extracted_fields=extracted_fields,
        field_confidences=field_confidences,
        justification=justification,
        created_at=datetime.now(timezone.utc),
    )
    db.add(result)
    db.commit()
    db.refresh(result)
    return result


def create_verification_result(
    db: Session,
    application_id: int,
    field_name: str,
    submitted_value: str | None,
    extracted_value: str | None,
    match_status: MatchStatus,
    justification: str,
) -> VerificationResult:
    result = VerificationResult(
        application_id=application_id,
        field_name=field_name,
        submitted_value=submitted_value,
        extracted_value=extracted_value,
        match_status=match_status,
        justification=justification,
        created_at=datetime.now(timezone.utc),
    )
    db.add(result)
    db.commit()
    db.refresh(result)
    return result


def get_verification_results(db: Session, application_id: int) -> list[VerificationResult]:
    return (
        db.query(VerificationResult)
        .filter(VerificationResult.application_id == application_id)
        .order_by(VerificationResult.id.asc())
        .all()
    )


def create_audit_log_entry(db: Session, application_id: int, actor: str, action: str, details: str) -> AuditLogEntry:
    """Append-only by construction: this module has no matching update/delete
    function, and no route exposes one (CLAUDE.md non-negotiable #3)."""
    entry = AuditLogEntry(
        application_id=application_id,
        actor=actor,
        action=action,
        details=details,
        timestamp=datetime.now(timezone.utc),
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def list_audit_log_entries(db: Session, application_id: int) -> list[AuditLogEntry]:
    return (
        db.query(AuditLogEntry)
        .filter(AuditLogEntry.application_id == application_id)
        .order_by(AuditLogEntry.timestamp.asc())
        .all()
    )
