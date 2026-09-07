from datetime import datetime, timedelta, timezone

from sqlalchemy import case
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import (
    Application,
    ApplicationStatus,
    AuditLogEntry,
    Decision,
    DecisionAction,
    Document,
    ExtractionResult,
    ExtractionStatus,
    MatchStatus,
    RiskAssessment,
    RiskLevel,
    VerificationResult,
)
from app.risk import RiskFactor
from app.schemas import ApplicationCreate, DecisionCreate
from app.storage import StoredFile

_DECISION_STATUS_MAP = {
    DecisionAction.APPROVE: ApplicationStatus.APPROVED,
    DecisionAction.REJECT: ApplicationStatus.REJECTED,
    DecisionAction.REQUEST_INFO: ApplicationStatus.INFO_REQUESTED,
}


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

    # US-27: SUBMITTED is the application's first status transition and
    # must produce a trail entry like every other one.
    db.add(
        AuditLogEntry(
            application_id=application.id,
            actor="applicant",
            action="APPLICATION_SUBMITTED",
            details=f"Application {application.reference_id} submitted by the applicant.",
            timestamp=submitted_at,
        )
    )

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


def get_decision(db: Session, application_id: int) -> Decision | None:
    return db.query(Decision).filter(Decision.application_id == application_id).first()


def create_decision(db: Session, application: Application, payload: DecisionCreate) -> Decision:
    """Writes the Decision row, the Application status transition, and the
    resulting audit entry as one transaction — a single db.commit() covers
    all three pending changes, so a failure partway through leaves nothing
    committed (US-23 DoD: atomic, no partial state).

    This is also the ONLY place in the entire codebase that may assign
    ApplicationStatus.APPROVED — see tests/test_no_auto_approval.py (US-24).
    Callers are responsible for checking application.status == PENDING_REVIEW
    before calling this (the API layer does, returning 409 otherwise), which
    is what makes a decision impossible to submit twice for the same review
    cycle (US-23 AC).
    """
    decision = Decision(
        application_id=application.id,
        reviewer_id=payload.reviewer_id,
        action=payload.action,
        reasoning=payload.reasoning,
        decided_at=datetime.now(timezone.utc),
    )
    db.add(decision)

    application.status = _DECISION_STATUS_MAP[payload.action]

    db.add(
        AuditLogEntry(
            application_id=application.id,
            actor=payload.reviewer_id,
            action=f"DECISION_{payload.action.value}",
            details=payload.reasoning or "Approved with no additional comments.",
            timestamp=decision.decided_at,
        )
    )

    db.commit()
    db.refresh(decision)
    return decision
