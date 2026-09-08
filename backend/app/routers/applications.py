import csv
import io
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app import crud, pipeline
from app.auth import require_reviewer
from app.database import get_db
from app.models import ApplicationStatus
from app.schemas import (
    ApplicationCreate,
    ApplicationDraftUpdate,
    ApplicationExtractionOut,
    ApplicationOut,
    AuditExportEntryOut,
    AuditExportOut,
    AuditLogEntryOut,
    DecisionCreate,
    DecisionOut,
    ExtractionFieldOut,
    ExtractionSummaryOut,
    RiskAssessmentOut,
    RiskFactorOut,
    VerificationResultOut,
)

logger = logging.getLogger("onboardiq")

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


@router.post("/draft", response_model=ApplicationOut, status_code=201)
def create_draft(payload: ApplicationDraftUpdate, db: Session = Depends(get_db)) -> ApplicationOut:
    """US-03: saves a partially completed application and hands back a
    reference ID immediately, before any required field is even complete —
    that's the whole point of a draft. Nothing here can produce a SUBMITTED
    application: see submit_draft below for the only path that transition
    can happen through."""
    application = crud.create_draft_application(db, payload)
    return ApplicationOut.model_validate(application)


@router.patch("/draft/{reference_id}", response_model=ApplicationOut)
def update_draft(reference_id: str, payload: ApplicationDraftUpdate, db: Session = Depends(get_db)) -> ApplicationOut:
    """US-03: saves further progress against an existing draft. Only fields
    present in the request body are changed (see ApplicationDraftUpdate),
    so resuming and re-saving step 1 alone can't wipe out step 2's values."""
    application = _get_application_or_404(db, reference_id)
    if application.status != ApplicationStatus.DRAFT:
        raise HTTPException(
            status_code=409,
            detail="This application has already been submitted and can no longer be edited as a draft.",
        )
    application = crud.update_draft_application(db, application, payload)
    return ApplicationOut.model_validate(application)


@router.post("/draft/{reference_id}/submit", response_model=ApplicationOut, status_code=201)
def submit_draft(reference_id: str, db: Session = Depends(get_db)) -> ApplicationOut:
    """US-03: the DRAFT -> SUBMITTED transition. Re-validates the complete
    field set with the exact same rules a direct submission goes through
    (ApplicationCreate) — a draft can be saved incomplete or invalid-looking
    at every intermediate step, but it cannot be submitted without becoming
    a fully valid application, same as US-01's DoD requires for any other
    submission path."""
    application = _get_application_or_404(db, reference_id)
    if application.status != ApplicationStatus.DRAFT:
        raise HTTPException(status_code=409, detail="This application is not a draft awaiting submission.")

    try:
        validated = ApplicationCreate.model_validate(
            {
                "full_name": application.full_name,
                "date_of_birth": application.date_of_birth,
                "id_number": application.id_number,
                "address": application.address,
                "email": application.email,
                "phone": application.phone,
                "account_type": application.account_type,
            }
        )
    except ValidationError as exc:
        # main.py's HTTPException handler renders `detail` as a plain string
        # message (unlike RequestValidationError, which gets a per-field
        # `errors` map) — so, consistent with every other HTTPException in
        # this API, this stays a single readable string rather than a
        # nested structure that handler isn't built to unwrap.
        messages = []
        for error in exc.errors():
            field = str(error["loc"][-1]) if error.get("loc") else "form"
            message = error.get("msg", "Invalid value.")
            message = message[len("Value error, ") :] if message.startswith("Value error, ") else message
            messages.append(f"{field}: {message}")
        raise HTTPException(
            status_code=422,
            detail="This application is incomplete and cannot be submitted yet — " + "; ".join(messages),
        ) from exc

    for field, value in validated.model_dump().items():
        setattr(application, field, value)

    application = crud.submit_draft_application(db, application)

    # US-09 AC: extraction runs on submission. If a document was already
    # attached while this was still a DRAFT (US-07/US-08 allow that), this
    # is the first moment submitted values actually exist to verify it
    # against — so the pipeline runs here instead, exactly once.
    current_document = next((d for d in crud.list_documents(db, application.id) if not d.superseded), None)
    if current_document is not None:
        try:
            pipeline.process_document(db, application, current_document)
        except Exception:
            logger.exception("Pipeline failed unexpectedly for application %s", reference_id)
            db.rollback()
            application.status = ApplicationStatus.PENDING_REVIEW
            db.commit()

    return ApplicationOut.model_validate(application)


@router.get("/{reference_id}", response_model=ApplicationOut)
def get_application(reference_id: str, db: Session = Depends(get_db)) -> ApplicationOut:
    application = _get_application_or_404(db, reference_id)
    return ApplicationOut.model_validate(application)


@router.get("/{reference_id}/extraction", response_model=ApplicationExtractionOut)
def get_extraction(
    reference_id: str, _reviewer: str = Depends(require_reviewer), db: Session = Depends(get_db)
) -> ApplicationExtractionOut:
    """Surfaces the AI extraction + cross-verification outcome (US-09..US-14)
    for an application's most recently uploaded (current, non-superseded —
    US-07) document. This is the API contract the reviewer screen consumes —
    reviewer login required (addition on top of the PRD, see app/auth.py):
    this data (mismatch details, confidence scores) is only ever surfaced
    on the reviewer detail screen, never to the applicant."""
    application = _get_application_or_404(db, reference_id)

    documents = crud.list_documents(db, application.id)
    extraction_out = None
    verification_results = []
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
            # US-25: scoped to THIS document only, so a resubmission's fresh
            # round of results never mixes with an earlier round's.
            verification_results = crud.get_verification_results_for_document(db, latest_document.id)

    if extraction_out is None:
        raise HTTPException(
            status_code=404,
            detail="No extraction result is available yet for this application.",
        )

    return ApplicationExtractionOut(
        application_status=application.status,
        flag_count=application.flag_count,
        extraction=extraction_out,
        verification=[VerificationResultOut.model_validate(v) for v in verification_results],
    )


@router.get("/{reference_id}/audit-log", response_model=list[AuditLogEntryOut])
def get_audit_log(
    reference_id: str, _reviewer: str = Depends(require_reviewer), db: Session = Depends(get_db)
) -> list[AuditLogEntryOut]:
    """US-27: the full, append-only trail for one application, in
    chronological order. Read-only — there is no corresponding update or
    delete endpoint anywhere in this API. Reviewer login required (addition
    on top of the PRD — see app/auth.py): the audit trail names reviewer
    identities and internal system actions, not something an anonymous
    applicant should be able to browse for any reference ID."""
    application = _get_application_or_404(db, reference_id)
    entries = crud.list_audit_log_entries(db, application.id)
    return [AuditLogEntryOut.model_validate(e) for e in entries]


@router.get("/{reference_id}/risk", response_model=RiskAssessmentOut)
def get_risk(
    reference_id: str, _reviewer: str = Depends(require_reviewer), db: Session = Depends(get_db)
) -> RiskAssessmentOut:
    """US-16/US-18: the latest advisory risk assessment plus its
    contributing factors in plain language — never a bare score (US-18
    DoD). Nothing about this level gates a decision; see app/risk.py and
    tests/test_no_auto_approval.py. Reviewer login required (addition on
    top of the PRD — see app/auth.py): risk factors are reviewer-facing
    triage information, never shown to the applicant."""
    application = _get_application_or_404(db, reference_id)
    assessment = crud.get_latest_risk_assessment(db, application.id)
    if assessment is None:
        raise HTTPException(status_code=404, detail="No risk assessment is available yet for this application.")
    return RiskAssessmentOut(
        risk_level=assessment.risk_level,
        factors=[RiskFactorOut(code=f["code"], message=f["message"]) for f in assessment.contributing_factors],
        computed_at=assessment.computed_at,
    )


@router.get("/{reference_id}/decision", response_model=DecisionOut)
def get_decision(reference_id: str, db: Session = Depends(get_db)) -> DecisionOut:
    """The decision that currently applies — for a resubmission loop
    (US-25) this is the LATEST one, not necessarily the first (e.g. an
    earlier REQUEST_INFO followed by a later APPROVE). See
    /{reference_id}/decisions for the full history."""
    application = _get_application_or_404(db, reference_id)
    decision = crud.get_latest_decision(db, application.id)
    if decision is None:
        raise HTTPException(status_code=404, detail="No decision has been recorded for this application yet.")
    return DecisionOut.model_validate(decision)


@router.get("/{reference_id}/decisions", response_model=list[DecisionOut])
def get_decisions(
    reference_id: str, _reviewer: str = Depends(require_reviewer), db: Session = Depends(get_db)
) -> list[DecisionOut]:
    """US-25 DoD: "Prior review context retained and visible on the second
    review" — the full decision history in chronological order, e.g. an
    earlier REQUEST_INFO followed by a later APPROVE/REJECT once the
    applicant resubmits. Reviewer login required (addition on top of the
    PRD — see app/auth.py): this is the reviewer screen's own history view;
    the applicant-facing equivalent is the unprotected GET .../decision
    (singular — the one currently-applicable decision, e.g. to show a
    Request More Information note), which is unaffected by this change."""
    application = _get_application_or_404(db, reference_id)
    decisions = crud.list_decisions(db, application.id)
    return [DecisionOut.model_validate(d) for d in decisions]


@router.post("/{reference_id}/decision", response_model=DecisionOut, status_code=201)
def submit_decision(
    reference_id: str,
    payload: DecisionCreate,
    current_reviewer: str = Depends(require_reviewer),
    db: Session = Depends(get_db),
) -> DecisionOut:
    """US-23/US-24: the only route in the API that can move an application
    to APPROVED, REJECTED, or INFO_REQUESTED — and it always has a reviewer
    identity attached (US-24 AC: "Attempting to approve via API without
    reviewer identity fails"). That identity now comes from `current_reviewer`
    (an authenticated reviewer session — see app/auth.py), an addition on
    top of the PRD: a request with no valid login is rejected with 401
    before this function body even runs, the same guarantee US-24 always
    had, just enforced by login instead of a required free-text field.

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
    decision = crud.create_decision(db, application, payload, reviewer_id=current_reviewer)
    return DecisionOut.model_validate(decision)


def _build_audit_export(db: Session, application) -> AuditExportOut:
    """US-28: merges the append-only audit trail with every decision ever
    recorded, into one chronological view — a pure read (no state written),
    so this can be called freely from either export format below."""
    audit_entries = [
        AuditExportEntryOut(
            record_type="AUDIT",
            timestamp=e.timestamp,
            actor=e.actor,
            action=e.action,
            details=e.details,
        )
        for e in crud.list_audit_log_entries(db, application.id)
    ]
    decision_entries = [
        AuditExportEntryOut(
            record_type="DECISION",
            timestamp=d.decided_at,
            actor=d.reviewer_id,
            action=d.action.value,
            details=d.reasoning or "Approved with no additional comments.",
        )
        for d in crud.list_decisions(db, application.id)
    ]
    entries = sorted(audit_entries + decision_entries, key=lambda e: e.timestamp)
    return AuditExportOut(
        reference_id=application.reference_id,
        applicant_full_name=application.full_name,
        final_status=application.status,
        exported_at=datetime.now(timezone.utc),
        entries=entries,
    )


@router.get("/{reference_id}/audit-log/export", response_model=None)
def export_audit_log(
    reference_id: str,
    format: str = Query(default="csv", pattern="^(csv|json)$"),
    _reviewer: str = Depends(require_reviewer),
    db: Session = Depends(get_db),
):
    """US-28: exports the audit trail plus every recorded decision for one
    application, in either CSV or JSON. Read-only — a GET that touches
    nothing (US-28 DoD). Distinct AUDIT and DECISION record types (see
    _build_audit_export) let a spreadsheet reader filter to just the
    decisions, while still shipping the full append-only trail in the same
    file. Reviewer login required — the same reviewer-only data as
    GET .../audit-log, just in export form; not requested by name when the
    reviewer-auth gap was flagged, but the same category of data, so
    closed alongside it."""
    application = _get_application_or_404(db, reference_id)
    export = _build_audit_export(db, application)

    if format == "json":
        return export

    # csv.writer (not manual string joining) is what correctly handles
    # commas, quotes, and embedded newlines in reasoning/details text
    # (US-28 DoD) — that's exactly the class of bug hand-rolled CSV writing
    # gets wrong.
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["record_type", "timestamp", "actor", "action", "details"])
    for entry in export.entries:
        writer.writerow([entry.record_type, entry.timestamp.isoformat(), entry.actor, entry.action, entry.details])

    filename = f"{application.reference_id}_audit_export.csv"
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
