from datetime import date, datetime, timezone

from pydantic import BaseModel, ConfigDict, EmailStr, field_validator, model_validator

from app.config import get_settings
from app.models import (
    AccountType,
    ApplicationStatus,
    DecisionAction,
    DocumentType,
    ExtractionStatus,
    MatchStatus,
    RiskLevel,
)
from app.validators import require_non_blank, validate_date_of_birth, validate_phone


class ApplicationCreate(BaseModel):
    full_name: str
    date_of_birth: date
    id_number: str
    address: str
    email: EmailStr
    phone: str
    account_type: AccountType

    @field_validator("full_name")
    @classmethod
    def _full_name_not_blank(cls, v: str) -> str:
        return require_non_blank(v, "Full name")

    @field_validator("id_number")
    @classmethod
    def _id_number_not_blank(cls, v: str) -> str:
        return require_non_blank(v, "ID number")

    @field_validator("address")
    @classmethod
    def _address_not_blank(cls, v: str) -> str:
        return require_non_blank(v, "Address")

    @field_validator("date_of_birth")
    @classmethod
    def _dob_not_future(cls, v: date) -> date:
        return validate_date_of_birth(v)

    @field_validator("phone")
    @classmethod
    def _phone_valid(cls, v: str) -> str:
        return validate_phone(v)


class ApplicationDraftUpdate(BaseModel):
    """US-03: every field optional and unvalidated for required-ness — a
    draft is allowed to be incomplete by definition. Fields that ARE
    provided still get the same sanity checks as a real submission (a typo'd
    email shouldn't be saved silently), just not the "must be present" check.
    Only fields the client actually sent are applied (see
    crud.update_draft_application's use of exclude_unset) so saving after
    step 2 can't accidentally null out step 1's already-saved values.
    """

    full_name: str | None = None
    date_of_birth: date | None = None
    id_number: str | None = None
    address: str | None = None
    email: EmailStr | None = None
    phone: str | None = None
    account_type: AccountType | None = None

    @field_validator("full_name", "id_number", "address")
    @classmethod
    def _not_blank_if_provided(cls, v: str | None) -> str | None:
        if v is not None and not v.strip():
            raise ValueError("This field cannot be blank once provided — leave it unset instead.")
        return v.strip() if v is not None else v

    @field_validator("date_of_birth")
    @classmethod
    def _dob_not_future_if_provided(cls, v: date | None) -> date | None:
        return validate_date_of_birth(v) if v is not None else v

    @field_validator("phone")
    @classmethod
    def _phone_valid_if_provided(cls, v: str | None) -> str | None:
        return validate_phone(v) if v is not None else v


class ApplicationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    reference_id: str
    status: ApplicationStatus
    submitted_at: datetime | None
    full_name: str | None
    date_of_birth: date | None
    id_number: str | None
    address: str | None
    email: str | None
    phone: str | None
    account_type: AccountType | None
    flag_count: int
    risk_level: RiskLevel | None


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    original_filename: str
    content_type: str
    size_bytes: int
    uploaded_at: datetime
    preview_url: str
    version: int
    superseded: bool
    declared_type: DocumentType | None
    detected_type: str | None
    # None = not yet computed / not computable (see
    # app.verification.compare_document_type) — distinct from False.
    type_mismatch: bool | None


class ExtractionFieldOut(BaseModel):
    value: str | None
    confidence: float
    justification: str
    # Computed at read time against the *current* configured threshold
    # (US-11 AC: "Threshold configurable without a code change") — not
    # baked in when the extraction ran, so changing the threshold later
    # changes what's flagged without needing to re-run extraction.
    is_low_confidence: bool

    @classmethod
    def from_stored(cls, stored: dict) -> "ExtractionFieldOut":
        threshold = get_settings().low_confidence_threshold
        return cls(
            value=stored.get("value"),
            confidence=stored.get("confidence", 0.0),
            justification=stored.get("justification", ""),
            is_low_confidence=stored.get("confidence", 0.0) < threshold,
        )


class ExtractionSummaryOut(BaseModel):
    status: ExtractionStatus
    justification: str
    created_at: datetime
    fields: dict[str, ExtractionFieldOut]


class VerificationResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    field_name: str
    submitted_value: str | None
    extracted_value: str | None
    match_status: MatchStatus
    justification: str


class ApplicationExtractionOut(BaseModel):
    application_status: ApplicationStatus
    flag_count: int
    extraction: ExtractionSummaryOut | None
    verification: list[VerificationResultOut]


class AuditLogEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    timestamp: datetime
    actor: str
    action: str
    details: str


class QueueItemOut(BaseModel):
    reference_id: str
    full_name: str
    submitted_at: datetime
    flag_count: int
    status: ApplicationStatus
    risk_level: RiskLevel | None
    # US-21: computed fresh from pending_review_since at read time, never
    # stored — see app/crud.py list_queue and the DoD it's built to satisfy.
    hours_waiting: float | None
    is_overdue: bool

    @classmethod
    def from_application(cls, application, overdue_threshold_hours: float) -> "QueueItemOut":
        hours_waiting = None
        is_overdue = False
        if application.pending_review_since is not None:
            pending_since = application.pending_review_since
            if pending_since.tzinfo is None:
                # SQLite round-trips DateTime columns as naive, even though
                # every write in this codebase stores UTC — re-attach it
                # rather than let a naive/aware subtraction blow up or,
                # worse, silently compare the wrong instants.
                pending_since = pending_since.replace(tzinfo=timezone.utc)
            elapsed = datetime.now(timezone.utc) - pending_since
            hours_waiting = round(elapsed.total_seconds() / 3600, 2)
            is_overdue = hours_waiting > overdue_threshold_hours

        return cls(
            reference_id=application.reference_id,
            full_name=application.full_name,
            submitted_at=application.submitted_at,
            flag_count=application.flag_count,
            status=application.status,
            risk_level=application.risk_level,
            hours_waiting=hours_waiting,
            is_overdue=is_overdue,
        )


class QueueOut(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[QueueItemOut]


class RiskFactorOut(BaseModel):
    # No raw "points" here by design — US-18 DoD: no opaque numeric score
    # shown without accompanying explanation. Reviewers see the message,
    # never a bare number.
    code: str
    message: str


class RiskAssessmentOut(BaseModel):
    risk_level: RiskLevel
    factors: list[RiskFactorOut]
    computed_at: datetime


class DecisionCreate(BaseModel):
    """No `reviewer_id` field — the identity behind a decision comes from
    the authenticated reviewer session (app/auth.py), never from
    client-supplied free text (see routers/applications.py submit_decision).
    This is an addition on top of the PRD (US-23/US-24's own requirements —
    reasoning rules, no-auto-approval — are unchanged; only *how* reviewer
    identity is established has changed)."""

    action: DecisionAction
    reasoning: str | None = None

    @model_validator(mode="after")
    def _reasoning_required_for_reject_or_request_info(self) -> "DecisionCreate":
        # US-23 AC: reasoning is mandatory for Reject and Request More Information.
        if self.action in (DecisionAction.REJECT, DecisionAction.REQUEST_INFO):
            if not self.reasoning or not self.reasoning.strip():
                raise ValueError(
                    "Reasoning is required when rejecting or requesting more information."
                )
            self.reasoning = self.reasoning.strip()
        return self


class DecisionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    reviewer_id: str
    action: DecisionAction
    reasoning: str | None
    decided_at: datetime


class AuditExportEntryOut(BaseModel):
    record_type: str  # "AUDIT" or "DECISION" — see routers/applications.py export_audit_log
    timestamp: datetime
    actor: str
    action: str
    details: str


class AuditExportOut(BaseModel):
    """US-28: everything needed to reconstruct an application's history
    outside the system — the append-only audit trail plus every decision
    ever recorded against it, merged into one chronological view. Read-only:
    this is a GET, nothing here writes to the database (US-28 DoD)."""

    reference_id: str
    applicant_full_name: str | None
    final_status: ApplicationStatus
    exported_at: datetime
    entries: list[AuditExportEntryOut]


class AskQuestionRequest(BaseModel):
    question: str

    @field_validator("question")
    @classmethod
    def _question_not_blank(cls, v: str) -> str:
        return require_non_blank(v, "Question")


class CitationOut(BaseModel):
    source_document: str
    section_reference: str


class AskQuestionResponse(BaseModel):
    # status is a plain str (not the AssistantStatus enum) here deliberately
    # — keeping app/rag/ free of any dependency on the request/response
    # layer, consistent with how app/risk.py and app/rules.py stay decoupled
    # from FastAPI.
    status: str
    answer: str
    citations: list[CitationOut]
    retrieved_chunk_count: int
