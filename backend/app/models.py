import enum
from datetime import date, datetime

from sqlalchemy import JSON, Date, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ApplicationStatus(str, enum.Enum):
    """Full status model from PRD section 8. Phase 1 only ever produces
    SUBMITTED — the remaining values exist here because they are part of the
    documented state machine, not because this phase implements the
    transitions into them."""

    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    PROCESSING = "PROCESSING"
    PENDING_REVIEW = "PENDING_REVIEW"
    INFO_REQUESTED = "INFO_REQUESTED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class AccountType(str, enum.Enum):
    SAVINGS = "SAVINGS"
    CURRENT = "CURRENT"


class ExtractionStatus(str, enum.Enum):
    """SUCCESS and UNREADABLE both mean the LLM call itself worked — the
    document was either legible or the model looked at it and correctly
    reported it wasn't (US-10). AI_UNAVAILABLE means we never got a usable
    answer at all: the API call failed/timed out, or its response couldn't
    be parsed into our expected shape (US-12). Keeping these distinct is
    what US-10's DoD calls "distinguishable from low-confidence success"."""

    SUCCESS = "SUCCESS"
    UNREADABLE = "UNREADABLE"
    AI_UNAVAILABLE = "AI_UNAVAILABLE"


class MatchStatus(str, enum.Enum):
    MATCH = "MATCH"
    PARTIAL_MATCH = "PARTIAL_MATCH"
    MISMATCH = "MISMATCH"


class DecisionAction(str, enum.Enum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    REQUEST_INFO = "REQUEST_INFO"


class RiskLevel(str, enum.Enum):
    """US-16: advisory only. Nothing in this codebase may use a RiskLevel to
    gate, block, or auto-decide anything — see app/risk.py and
    tests/test_no_auto_approval.py, which also covers risk never causing an
    approval/rejection on its own."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class Application(Base):
    __tablename__ = "applications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    reference_id: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    status: Mapped[ApplicationStatus] = mapped_column(
        Enum(ApplicationStatus), nullable=False, default=ApplicationStatus.SUBMITTED
    )
    submitted_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    date_of_birth: Mapped[date] = mapped_column(Date, nullable=False)
    id_number: Mapped[str] = mapped_column(String(64), nullable=False)
    address: Mapped[str] = mapped_column(Text, nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str] = mapped_column(String(32), nullable=False)
    account_type: Mapped[AccountType] = mapped_column(Enum(AccountType), nullable=False)

    # Count of MISMATCH verification results (US-13) — PARTIAL_MATCH and
    # MATCH are not "flags"; see app/verification.py.
    flag_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Latest computed risk level (US-16) — denormalized from the most recent
    # RiskAssessment row for cheap queue sorting/filtering, the same pattern
    # flag_count follows for VerificationResult. Null until the pipeline has
    # run once. Advisory only — see RiskLevel and app/risk.py.
    risk_level: Mapped[RiskLevel | None] = mapped_column(Enum(RiskLevel), nullable=True, default=None)

    # Set once, the first time status becomes PENDING_REVIEW (US-21 ageing).
    # Null for applications that haven't reached PENDING_REVIEW yet.
    pending_review_since: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, default=None)

    documents: Mapped[list["Document"]] = relationship(
        "Document", back_populates="application", cascade="all, delete-orphan"
    )
    verification_results: Mapped[list["VerificationResult"]] = relationship(
        "VerificationResult", back_populates="application", cascade="all, delete-orphan"
    )
    audit_log_entries: Mapped[list["AuditLogEntry"]] = relationship(
        "AuditLogEntry", back_populates="application", cascade="all, delete-orphan"
    )
    decisions: Mapped[list["Decision"]] = relationship(
        "Decision", back_populates="application", cascade="all, delete-orphan"
    )
    risk_assessments: Mapped[list["RiskAssessment"]] = relationship(
        "RiskAssessment", back_populates="application", cascade="all, delete-orphan"
    )


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    application_id: Mapped[int] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), nullable=False, index=True
    )
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(64), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    application: Mapped["Application"] = relationship("Application", back_populates="documents")
    extraction_results: Mapped[list["ExtractionResult"]] = relationship(
        "ExtractionResult", back_populates="document", cascade="all, delete-orphan"
    )


class ExtractionResult(Base):
    """One row per extraction attempt (US-09). A document may have more than
    one row over time (e.g. a retry after AI_UNAVAILABLE) — the latest by
    created_at is the current one; see crud.get_latest_extraction_result."""

    __tablename__ = "extraction_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Per-field {"value": str|None, "confidence": float, "justification": str}.
    extracted_fields: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    # Duplicates each field's confidence as a flat map, per the documented
    # schema (PRD section 9) — kept in sync with extracted_fields at write time.
    field_confidences: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    # Overall, human-readable summary — always populated, even on failure
    # (CLAUDE.md: no unexplained AI output).
    justification: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[ExtractionStatus] = mapped_column(Enum(ExtractionStatus), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    document: Mapped["Document"] = relationship("Document", back_populates="extraction_results")


class VerificationResult(Base):
    """One row per compared field (US-13) — never an aggregate blob, per DoD."""

    __tablename__ = "verification_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    application_id: Mapped[int] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), nullable=False, index=True
    )
    field_name: Mapped[str] = mapped_column(String(64), nullable=False)
    submitted_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    extracted_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    match_status: Mapped[MatchStatus] = mapped_column(Enum(MatchStatus), nullable=False)
    justification: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    application: Mapped["Application"] = relationship("Application", back_populates="verification_results")


class AuditLogEntry(Base):
    """Append-only (CLAUDE.md non-negotiable #3): deliberately, there is no
    update or delete function for this model anywhere in crud.py, and no
    route exposes one. Only US-27 (phase 3) adds a read endpoint; this
    model exists now because US-12 requires AI failures to be logged."""

    __tablename__ = "audit_log_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    application_id: Mapped[int] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), nullable=False, index=True
    )
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    actor: Mapped[str] = mapped_column(String(64), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    details: Mapped[str] = mapped_column(Text, nullable=False)

    application: Mapped["Application"] = relationship("Application", back_populates="audit_log_entries")


class Decision(Base):
    """The one and only place ApplicationStatus.APPROVED is ever assigned —
    see crud.create_decision and tests/test_no_auto_approval.py (US-24).

    No unique constraint on application_id: enforcement of "one decision per
    review cycle" (US-23 AC) is done by gating on Application.status being
    PENDING_REVIEW at decision time, not by a permanent DB constraint — a
    future resubmission loop (US-25, phase 6) will legitimately need a
    second decision after a second PENDING_REVIEW cycle.
    """

    __tablename__ = "decisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    application_id: Mapped[int] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), nullable=False, index=True
    )
    reviewer_id: Mapped[str] = mapped_column(String(128), nullable=False)
    action: Mapped[DecisionAction] = mapped_column(Enum(DecisionAction), nullable=False)
    reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    application: Mapped["Application"] = relationship("Application", back_populates="decisions")


class RiskAssessment(Base):
    """One row per risk computation (US-16). Like ExtractionResult, a given
    application may accumulate more than one row over time (e.g. a retried
    extraction re-triggers scoring) — the latest by computed_at is current;
    see crud.get_latest_risk_assessment. Advisory only: nothing reads
    risk_level to gate a status change — see RiskLevel and app/risk.py."""

    __tablename__ = "risk_assessments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    application_id: Mapped[int] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), nullable=False, index=True
    )
    risk_level: Mapped[RiskLevel] = mapped_column(Enum(RiskLevel), nullable=False)
    # List of {"code": str, "message": str, "points": int} — US-18 AC: shown
    # to reviewers as plain-language factors, never a bare score.
    contributing_factors: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    computed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    application: Mapped["Application"] = relationship("Application", back_populates="risk_assessments")
