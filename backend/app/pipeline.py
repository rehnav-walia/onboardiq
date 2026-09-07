"""Orchestrates document extraction + cross-verification (US-09..US-14).

Triggered synchronously right after a document upload (US-09 AC: runs
automatically on submission, no manual trigger). Every branch below ends by
moving the application to PENDING_REVIEW and committing — nothing here ever
raises back to its caller; the one broad `except Exception` is deliberate
and is CLAUDE.md's graceful-degradation principle applied literally: an AI
failure (of any kind, including a bug in this module) must never turn into
an error response for the applicant, only a flag for a human reviewer.
"""

import logging

from sqlalchemy.orm import Session

from app import crud
from app.llm.client import run_extraction
from app.llm.errors import AIUnavailableError
from app.models import Application, ApplicationStatus, Document, ExtractionStatus, MatchStatus
from app.storage import resolve_path
from app.verification import FIELD_COMPARATORS

logger = logging.getLogger("onboardiq")

_FALLBACK_JUSTIFICATION = (
    "AI extraction is temporarily unavailable — this application has been routed for manual review."
)

_SUBMITTED_VALUES = {
    "full_name": lambda application: application.full_name,
    "date_of_birth": lambda application: application.date_of_birth.isoformat(),
    "id_number": lambda application: application.id_number,
}


def _record_unavailable(db: Session, application: Application, document: Document, reason: str) -> None:
    crud.create_extraction_result(
        db,
        document_id=document.id,
        status=ExtractionStatus.AI_UNAVAILABLE,
        extracted_fields={},
        field_confidences={},
        justification=_FALLBACK_JUSTIFICATION,
    )
    crud.create_audit_log_entry(
        db,
        application_id=application.id,
        actor="system",
        action="EXTRACTION_FAILED",
        details=reason,
    )
    application.status = ApplicationStatus.PENDING_REVIEW
    db.commit()


def process_document(db: Session, application: Application, document: Document) -> None:
    # US-09 DoD: idempotent. A prior SUCCESS or UNREADABLE result reflects an
    # actual look at this document and is not re-done; a prior
    # AI_UNAVAILABLE result reflects nothing having been learned, so a retry
    # is allowed to proceed.
    existing = crud.get_latest_extraction_result(db, document.id)
    if existing is not None and existing.status != ExtractionStatus.AI_UNAVAILABLE:
        return

    application.status = ApplicationStatus.PROCESSING
    # create_audit_log_entry commits — that single commit also covers the
    # status change above, so there's no separate db.commit() here.
    crud.create_audit_log_entry(
        db,
        application_id=application.id,
        actor="system",
        action="PROCESSING_STARTED",
        details="Document received; AI extraction started.",
    )

    try:
        file_bytes = resolve_path(document.file_path).read_bytes()
        llm_result = run_extraction(file_bytes, document.content_type, declared_document_type=None)
    except AIUnavailableError as exc:
        _record_unavailable(db, application, document, reason=str(exc))
        return
    except Exception as exc:  # belt-and-braces: a bug here must not break onboarding
        logger.exception("Unexpected error during extraction for application %s", application.reference_id)
        _record_unavailable(db, application, document, reason=f"Unexpected error: {exc}")
        return

    if not llm_result.readable:
        # US-10: no partial/invented values are persisted — extracted_fields stays empty.
        crud.create_extraction_result(
            db,
            document_id=document.id,
            status=ExtractionStatus.UNREADABLE,
            extracted_fields={},
            field_confidences={},
            justification=llm_result.overall_justification,
        )
        crud.create_audit_log_entry(
            db,
            application_id=application.id,
            actor="system",
            action="EXTRACTION_UNREADABLE",
            details=llm_result.overall_justification,
        )
        application.status = ApplicationStatus.PENDING_REVIEW
        db.commit()
        return

    extracted_fields = {}
    field_confidences = {}
    for field_name in ("full_name", "date_of_birth", "id_number", "document_type"):
        field_result = getattr(llm_result, field_name)
        extracted_fields[field_name] = {
            "value": field_result.value,
            "confidence": field_result.confidence,
            "justification": field_result.justification,
        }
        field_confidences[field_name] = field_result.confidence

    crud.create_extraction_result(
        db,
        document_id=document.id,
        status=ExtractionStatus.SUCCESS,
        extracted_fields=extracted_fields,
        field_confidences=field_confidences,
        justification=llm_result.overall_justification,
    )
    crud.create_audit_log_entry(
        db,
        application_id=application.id,
        actor="system",
        action="EXTRACTION_SUCCEEDED",
        details=llm_result.overall_justification,
    )

    flag_count = 0
    for field_name, comparator in FIELD_COMPARATORS.items():
        submitted_value = _SUBMITTED_VALUES[field_name](application)
        extracted_value = extracted_fields[field_name]["value"]
        match_status, justification = comparator(submitted_value, extracted_value)
        crud.create_verification_result(
            db,
            application_id=application.id,
            field_name=field_name,
            submitted_value=submitted_value,
            extracted_value=extracted_value,
            match_status=match_status,
            justification=justification,
        )
        if match_status == MatchStatus.MISMATCH:
            flag_count += 1

    crud.create_audit_log_entry(
        db,
        application_id=application.id,
        actor="system",
        action="VERIFICATION_COMPLETED",
        details=f"{flag_count} of {len(FIELD_COMPARATORS)} compared field(s) flagged as mismatched.",
    )

    application.flag_count = flag_count
    application.status = ApplicationStatus.PENDING_REVIEW
    db.commit()
