from datetime import datetime, timedelta, timezone

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import (
    Application,
    ApplicationStatus,
    AuditLogEntry,
    Decision,
    DecisionAction,
    Document,
    DocumentType,
    ExtractionResult,
    ExtractionStatus,
    MatchStatus,
    RiskAssessment,
    RiskLevel,
    VerificationResult,
)
from app.risk import RiskFactor
from app.schemas import ApplicationCreate, ApplicationDraftUpdate, DecisionCreate
from app.storage import StoredFile

_DECISION_STATUS_MAP = {
    DecisionAction.APPROVE: ApplicationStatus.APPROVED,
    DecisionAction.REJECT: ApplicationStatus.REJECTED,
    DecisionAction.REQUEST_INFO: ApplicationStatus.INFO_REQUESTED,
}


def _generate_reference_id(application: Application, at: datetime) -> str:
    settings = get_settings()
    return f"{settings.reference_id_prefix}-{at.year}-{application.id:05d}"


def create_application(db: Session, payload: ApplicationCreate) -> Application:
    """Creates the row, then derives the reference ID from the row's own
    primary key so uniqueness is guaranteed by the same DB-level constraint
    that guarantees the primary key is unique (US-01 DoD)."""
    now = datetime.now(timezone.utc)

    application = Application(
        status=ApplicationStatus.SUBMITTED,
        created_at=now,
        submitted_at=now,
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

    application.reference_id = _generate_reference_id(application, now)

    # US-27: SUBMITTED is the application's first status transition and
    # must produce a trail entry like every other one.
    db.add(
        AuditLogEntry(
            application_id=application.id,
            actor="applicant",
            action="APPLICATION_SUBMITTED",
            details=f"Application {application.reference_id} submitted by the applicant.",
            timestamp=now,
        )
    )

    db.commit()
    db.refresh(application)
    return application


def create_draft_application(db: Session, payload: ApplicationDraftUpdate) -> Application:
    """US-03: saves a partially completed application as DRAFT, with a
    reference ID handed back immediately so the applicant has something to
    resume with — same reference-ID-from-primary-key approach as
    create_application, just keyed off draft creation time since there is no
    submitted_at yet."""
    now = datetime.now(timezone.utc)

    application = Application(
        status=ApplicationStatus.DRAFT,
        created_at=now,
        submitted_at=None,
        reference_id="",
        **payload.model_dump(exclude_unset=True),
    )
    db.add(application)
    db.flush()

    application.reference_id = _generate_reference_id(application, now)
    db.commit()
    db.refresh(application)
    return application


def update_draft_application(db: Session, application: Application, payload: ApplicationDraftUpdate) -> Application:
    """US-03: overwrites only the fields actually sent, so saving after
    completing step 2 doesn't clobber step 1's already-saved values with
    nulls (the frontend always resends the whole form anyway, but the API
    contract shouldn't rely on that)."""
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(application, field, value)
    db.commit()
    db.refresh(application)
    return application


def submit_draft_application(db: Session, application: Application) -> Application:
    """US-03: the DRAFT -> SUBMITTED transition. Full validation of the now-
    complete field set already happened in the router (via ApplicationCreate)
    before this is called — this just performs the transition and writes the
    same SUBMITTED audit entry a direct submission gets, so the trail reads
    identically regardless of which path an application took to get here."""
    now = datetime.now(timezone.utc)
    application.status = ApplicationStatus.SUBMITTED
    application.submitted_at = now

    db.add(
        AuditLogEntry(
            application_id=application.id,
            actor="applicant",
            action="APPLICATION_SUBMITTED",
            details=f"Application {application.reference_id} submitted by the applicant (resumed from a saved draft).",
            timestamp=now,
        )
    )
    db.commit()
    db.refresh(application)
    return application


def get_application_by_reference(db: Session, reference_id: str) -> Application | None:
    return db.query(Application).filter(Application.reference_id == reference_id).first()


def create_document(
    db: Session,
    application: Application,
    original_filename: str,
    stored: StoredFile,
    declared_type: DocumentType | None,
) -> Document:
    """US-07: every prior document for this application is marked
    superseded (never deleted — they remain queryable for audit) and the new
    one gets the next version number. For a brand-new application this is a
    no-op loop over zero rows, so version 1 / superseded=False falls out
    naturally without a separate "is this the first upload" branch."""
    existing_documents = list_documents(db, application.id)
    for existing in existing_documents:
        existing.superseded = True

    document = Document(
        application_id=application.id,
        original_filename=original_filename,
        content_type=stored.content_type,
        file_path=stored.relative_path,
        size_bytes=stored.size_bytes,
        uploaded_at=datetime.now(timezone.utc),
        version=len(existing_documents) + 1,
        superseded=False,
        declared_type=declared_type,
    )
    db.add(document)

    if existing_documents:
        db.add(
            AuditLogEntry(
                application_id=application.id,
                actor="applicant",
                action="DOCUMENT_REPLACED",
                details=(
                    f"Replaced '{existing_documents[-1].original_filename}' (version "
                    f"{existing_documents[-1].version}) with '{original_filename}' (version "
                    f"{len(existing_documents) + 1}). The previous version is retained, not deleted."
                ),
                timestamp=datetime.now(timezone.utc),
            )
        )

    db.commit()
    db.refresh(document)
    return document


def record_document_type_check(db: Session, document: Document, detected_type: str | None) -> None:
    """US-15: compares the applicant's declared type against what the AI
    detected, once extraction has actually produced a value. Left at None
    (not False) when there's nothing to compare — see
    app.verification.compare_document_type."""
    from app.verification import compare_document_type

    document.detected_type = detected_type
    document.type_mismatch = compare_document_type(document.declared_type, detected_type)
    db.commit()


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
    document_id: int,
    field_name: str,
    submitted_value: str | None,
    extracted_value: str | None,
    match_status: MatchStatus,
    justification: str,
) -> VerificationResult:
    result = VerificationResult(
        application_id=application_id,
        document_id=document_id,
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


def get_verification_results_for_document(db: Session, document_id: int) -> list[VerificationResult]:
    """US-25: scoped to one document/round, not the whole application — a
    resubmission after INFO_REQUESTED produces a fresh round of results
    against the new document, and this must not return an earlier round's
    results alongside them (see the VerificationResult docstring)."""
    return (
        db.query(VerificationResult)
        .filter(VerificationResult.document_id == document_id)
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


_QUEUE_STATUSES = (ApplicationStatus.PENDING_REVIEW, ApplicationStatus.INFO_REQUESTED)

# Maps risk level to a sortable severity number — RiskLevel is stored as
# text, so a plain column sort would go alphabetically (HIGH, LOW, MEDIUM),
# not by actual severity. Unscored (NULL) applications sort as 0, i.e.
# lowest, on either sort direction's "low" end.
_RISK_SEVERITY = case(
    (Application.risk_level == RiskLevel.LOW, 1),
    (Application.risk_level == RiskLevel.MEDIUM, 2),
    (Application.risk_level == RiskLevel.HIGH, 3),
    else_=0,
)


def list_queue(
    db: Session,
    limit: int,
    offset: int,
    status: ApplicationStatus | None = None,
    risk_level: RiskLevel | None = None,
    sort_by: str = "submitted_at",
    sort_dir: str = "asc",
    overdue_only: bool = False,
) -> tuple[int, list[Application]]:
    """US-19/US-20/US-21: only PENDING_REVIEW/INFO_REQUESTED applications
    ever appear — DRAFT, SUBMITTED (not yet processed), and decided
    applications never do. `status`/`risk_level` narrow that further;
    `sort_by`/`sort_dir` order server-side (US-20 DoD); `overdue_only`
    filters to applications waiting longer than the configured threshold
    (US-21), computed fresh against the current time on every call, not
    against a stored, potentially-stale value (US-21 DoD).

    Paginated with LIMIT/OFFSET so it doesn't degrade with volume (US-19 DoD).
    """
    statuses = (status,) if status is not None else _QUEUE_STATUSES
    query = db.query(Application).filter(Application.status.in_(statuses))

    if risk_level is not None:
        query = query.filter(Application.risk_level == risk_level)

    if overdue_only:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=get_settings().overdue_threshold_hours)
        query = query.filter(
            Application.pending_review_since.isnot(None),
            Application.pending_review_since < cutoff,
        )

    total = query.count()

    order_column = _RISK_SEVERITY if sort_by == "risk_level" else Application.submitted_at
    order_expr = order_column.desc() if sort_dir == "desc" else order_column.asc()
    items = query.order_by(order_expr).offset(offset).limit(limit).all()
    return total, items


def get_queue_stats(db: Session) -> dict[str, int]:
    """Read-only aggregate counts for the reviewer queue summary bar
    (addition on top of the PRD). Status counts are a single GROUP BY over
    the whole applications table — not scoped to the queue's own
    PENDING_REVIEW/INFO_REQUESTED filter, since APPROVED/REJECTED never
    appear in crud.list_queue's results at all and this is the only place
    those totals are ever computed. `overdue` mirrors list_queue's own
    overdue_only cutoff logic (US-21) exactly, so the number shown here and
    the "Overdue only" filter on the queue itself never disagree."""
    status_counts = dict(db.query(Application.status, func.count(Application.id)).group_by(Application.status).all())

    cutoff = datetime.now(timezone.utc) - timedelta(hours=get_settings().overdue_threshold_hours)
    overdue = (
        db.query(Application)
        .filter(Application.status.in_(_QUEUE_STATUSES))
        .filter(Application.pending_review_since.isnot(None))
        .filter(Application.pending_review_since < cutoff)
        .count()
    )

    return {
        "pending_review": status_counts.get(ApplicationStatus.PENDING_REVIEW, 0),
        "info_requested": status_counts.get(ApplicationStatus.INFO_REQUESTED, 0),
        "approved": status_counts.get(ApplicationStatus.APPROVED, 0),
        "rejected": status_counts.get(ApplicationStatus.REJECTED, 0),
        "overdue": overdue,
    }


def create_risk_assessment(
    db: Session, application_id: int, risk_level: RiskLevel, factors: list[RiskFactor]
) -> RiskAssessment:
    assessment = RiskAssessment(
        application_id=application_id,
        risk_level=risk_level,
        contributing_factors=[{"code": f.code, "message": f.message, "points": f.points} for f in factors],
        computed_at=datetime.now(timezone.utc),
    )
    db.add(assessment)
    db.commit()
    db.refresh(assessment)
    return assessment


def get_latest_risk_assessment(db: Session, application_id: int) -> RiskAssessment | None:
    return (
        db.query(RiskAssessment)
        .filter(RiskAssessment.application_id == application_id)
        .order_by(RiskAssessment.computed_at.desc())
        .first()
    )


def get_latest_decision(db: Session, application_id: int) -> Decision | None:
    """US-25: an application can accumulate more than one decision over its
    lifetime (e.g. REQUEST_INFO, then a later APPROVE/REJECT once the
    applicant resubmits) — this is the one that currently applies. See
    list_decisions for the full history a reviewer needs to see prior
    review context (US-25 DoD)."""
    return (
        db.query(Decision)
        .filter(Decision.application_id == application_id)
        .order_by(Decision.decided_at.desc())
        .first()
    )


def list_decisions(db: Session, application_id: int) -> list[Decision]:
    return (
        db.query(Decision)
        .filter(Decision.application_id == application_id)
        .order_by(Decision.decided_at.asc())
        .all()
    )


def create_decision(db: Session, application: Application, payload: DecisionCreate, reviewer_id: str) -> Decision:
    """Writes the Decision row, the Application status transition, and the
    resulting audit entry as one transaction — a single db.commit() covers
    all three pending changes, so a failure partway through leaves nothing
    committed (US-23 DoD: atomic, no partial state).

    `reviewer_id` is the authenticated reviewer's username (see
    app/auth.py's require_reviewer and routers/applications.py's
    submit_decision) — never client-supplied free text, an addition on top
    of the PRD (US-24's own requirement, "attempting to approve without
    reviewer identity fails," is unchanged: it's just enforced by a login
    requirement now instead of a required request-body field).

    This is also the ONLY place in the entire codebase that may assign
    ApplicationStatus.APPROVED — see tests/test_no_auto_approval.py (US-24).
    Callers are responsible for checking application.status == PENDING_REVIEW
    before calling this (the API layer does, returning 409 otherwise), which
    is what makes a decision impossible to submit twice for the same review
    cycle (US-23 AC).
    """
    decision = Decision(
        application_id=application.id,
        reviewer_id=reviewer_id,
        action=payload.action,
        reasoning=payload.reasoning,
        decided_at=datetime.now(timezone.utc),
    )
    db.add(decision)

    application.status = _DECISION_STATUS_MAP[payload.action]

    db.add(
        AuditLogEntry(
            application_id=application.id,
            actor=reviewer_id,
            action=f"DECISION_{payload.action.value}",
            details=payload.reasoning or "Approved with no additional comments.",
            timestamp=decision.decided_at,
        )
    )

    db.commit()
    db.refresh(decision)
    return decision
