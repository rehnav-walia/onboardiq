from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import crud
from app.database import get_db
from app.models import ApplicationStatus
from app.schemas import (
    ApplicationCreate,
    ApplicationExtractionOut,
    ApplicationOut,
    AuditLogEntryOut,
    DecisionCreate,
    DecisionOut,
    ExtractionFieldOut,
    ExtractionSummaryOut,
    VerificationResultOut,
)

router = APIRouter(prefix="/api/applications", tags=["applications"])


def _get_application_or_404(db: Session, reference_id: str):
    application = crud.get_application_by_reference(db, reference_id)
    if application is None:
        raise HTTPException(status_code=404, detail="No application found with that reference ID.")
    return application


@router.post("", response_model=ApplicationOut, status_code=201)
def submit_application(payload: ApplicationCreate, db: Session = Depends(get_db)) -> ApplicationOut:
    """US-01: creates the Application as SUBMITTED and returns its reference ID.

    payload is an ApplicationCreate — the schema accepts only the fields an
    applicant is meant to set, so there is no way for a client to smuggle in
    a status, reference_id, or any other server-controlled value.
    """
    application = crud.create_application(db, payload)
    return ApplicationOut.model_validate(application)


@router.get("/{reference_id}", response_model=ApplicationOut)
def get_application(reference_id: str, db: Session = Depends(get_db)) -> ApplicationOut:
    application = _get_application_or_404(db, reference_id)
    return ApplicationOut.model_validate(application)


@router.get("/{reference_id}/extraction", response_model=ApplicationExtractionOut)
def get_extraction(reference_id: str, db: Session = Depends(get_db)) -> ApplicationExtractionOut:
    """Surfaces the AI extraction + cross-verification outcome (US-09..US-14)
    for an application's most recently uploaded document. This is the API
    contract the phase 3 reviewer screen will consume."""
    application = _get_application_or_404(db, reference_id)

    documents = crud.list_documents(db, application.id)
    extraction_out = None
    if documents:
        latest_document = documents[-1]
        extraction_result = crud.get_latest_extraction_result(db, latest_document.id)
        if extraction_result is not None:
            extraction_out = ExtractionSummaryOut(
                status=extraction_result.status,
                justification=extraction_result.justification,
                created_at=extraction_result.created_at,
                fields={
                    field_name: ExtractionFieldOut.from_stored(field_data)
                    for field_name, field_data in extraction_result.extracted_fields.items()
                },
            )

    if extraction_out is None:
        raise HTTPException(
            status_code=404,
            detail="No extraction result is available yet for this application.",
        )

    verification_results = crud.get_verification_results(db, application.id)
    return ApplicationExtractionOut(
        application_status=application.status,
        flag_count=application.flag_count,
        extraction=extraction_out,
        verification=[VerificationResultOut.model_validate(v) for v in verification_results],
    )


@router.get("/{reference_id}/audit-log", response_model=list[AuditLogEntryOut])
def get_audit_log(reference_id: str, db: Session = Depends(get_db)) -> list[AuditLogEntryOut]:
    """US-27: the full, append-only trail for one application, in
    chronological order. Read-only — there is no corresponding update or
    delete endpoint anywhere in this API."""
    application = _get_application_or_404(db, reference_id)
    entries = crud.list_audit_log_entries(db, application.id)
    return [AuditLogEntryOut.model_validate(e) for e in entries]


@router.get("/{reference_id}/decision", response_model=DecisionOut)
def get_decision(reference_id: str, db: Session = Depends(get_db)) -> DecisionOut:
    application = _get_application_or_404(db, reference_id)
    decision = crud.get_decision(db, application.id)
    if decision is None:
        raise HTTPException(status_code=404, detail="No decision has been recorded for this application yet.")
    return DecisionOut.model_validate(decision)


@router.post("/{reference_id}/decision", response_model=DecisionOut, status_code=201)
def submit_decision(reference_id: str, payload: DecisionCreate, db: Session = Depends(get_db)) -> DecisionOut:
    """US-23/US-24: the only route in the API that can move an application
    to APPROVED, REJECTED, or INFO_REQUESTED — and it always requires a
    reviewer_id (US-24 AC: "Attempting to approve via API without reviewer
    identity fails" — DecisionCreate.reviewer_id is a required, non-blank
    field, so a request without one is rejected by validation before this
    function body even runs).

    US-23 AC: "A decision cannot be submitted twice for the same
    application" — enforced here by requiring PENDING_REVIEW, which a first
    decision always moves the application out of (DoD: server-side, not
    just a disabled button).
    """
    application = _get_application_or_404(db, reference_id)
    if application.status != ApplicationStatus.PENDING_REVIEW:
        raise HTTPException(
            status_code=409,
            detail="This application is not awaiting a decision (it may already have been decided).",
        )
    decision = crud.create_decision(db, application, payload)
    return DecisionOut.model_validate(decision)
