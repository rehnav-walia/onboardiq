"""Orchestrates document extraction, cross-verification, and risk scoring
(US-09..US-18).

Triggered synchronously right after a document upload (US-09 AC: runs
automatically on submission, no manual trigger). Every branch below ends by
computing an advisory risk assessment, moving the application to
PENDING_REVIEW, and committing — nothing here ever raises back to its
caller; the one broad `except Exception` is deliberate and is CLAUDE.md's
graceful-degradation principle applied literally: an AI failure (of any
kind, including a bug in this module) must never turn into an error
response for the applicant, only a flag for a human reviewer.

Risk scoring (US-16) and the rule checks (US-17) run in EVERY branch,
including when AI extraction failed entirely — they don't depend on the LLM
having succeeded, by design.
"""

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app import crud
from app.config import get_settings
from app.llm.client import run_extraction
from app.llm.errors import AIUnavailableError
from app.models import Application, ApplicationStatus, Document, ExtractionStatus, MatchStatus
from app.risk import RiskFactor, assess_risk
from app.rules import check_document_expiry, check_future_dated_dob, check_minimum_age
from app.storage import resolve_path
from app.verification import FIELD_COMPARATORS, parse_date

logger = logging.getLogger("onboardiq")

_FALLBACK_JUSTIFICATION = (
    "AI extraction is temporarily unavailable — this application has been routed for manual review."
)

_EXTRACTED_FIELD_NAMES = ("full_name", "date_of_birth", "id_number", "document_type", "expiry_date")

_SUBMITTED_VALUES = {
    "full_name": lambda application: application.full_name,
    "date_of_birth": lambda application: application.date_of_birth.isoformat(),
    "id_number": lambda application: application.id_number,
}


def _mark_pending_review(application: Application, now: datetime) -> None:
    application.status = ApplicationStatus.PENDING_REVIEW
    # Only set on the FIRST time this application needed review — a retry
    # after AI_UNAVAILABLE shouldn't reset the clock a reviewer is waiting
    # against (US-21 ageing).
    if application.pending_review_since is None:
        application.pending_review_since = now


def _compute_rule_flags(
    application: Application, extracted_fields: dict | None, reference_date
) -> list[RiskFactor]:
    """US-17: independent of the LLM — check_minimum_age always runs against
    the submitted date of birth. The other two only ever produce a flag when
    extraction actually succeeded and yielded a usable value."""
    flags = []

    age_flag = check_minimum_age(application.date_of_birth, reference_date)
    if age_flag:
        flags.append(age_flag)

    future_dob_flag = check_future_dated_dob(application.date_of_birth, reference_date)
    if future_dob_flag:
        flags.append(future_dob_flag)

    if extracted_fields:
        extracted_dob = parse_date(extracted_fields.get("date_of_birth", {}).get("value"))
        if extracted_dob is not None:
            extracted_future_flag = check_future_dated_dob(extracted_dob, reference_date)
            if extracted_future_flag:
                flags.append(extracted_future_flag)

        expiry_flag = check_document_expiry(extracted_fields.get("expiry_date", {}).get("value"), reference_date)
        if expiry_flag:
            flags.append(expiry_flag)

    return flags


def _compute_and_persist_risk(
    db: Session,
    application: Application,
    extraction_status: ExtractionStatus,
    extracted_fields: dict | None,
    field_confidences: dict,
) -> None:
    """US-16/US-18: always runs, regardless of how extraction went — risk is
    advisory and computed from whatever is actually known right now."""
    settings = get_settings()
    now = datetime.now(timezone.utc)
    reference_date = now.date()

    verification_results = []
    if extraction_status == ExtractionStatus.SUCCESS:
        verification_results = [
            (result.field_name, result.match_status) for result in crud.get_verification_results(db, application.id)
        ]

    rule_flags = _compute_rule_flags(application, extracted_fields, reference_date)

    risk_level, factors = assess_risk(
        verification_results=verification_results,
        extraction_status=extraction_status,
        field_confidences=field_confidences,
        low_confidence_threshold=settings.low_confidence_threshold,
        declared_type_mismatch=None,  # US-15 not implemented yet — see app/risk.py
        rule_flags=rule_flags,
    )

    crud.create_risk_assessment(db, application_id=application.id, risk_level=risk_level, factors=factors)
    crud.create_audit_log_entry(
        db,
        application_id=application.id,
        actor="system",
        action="RISK_ASSESSED",
        details=f"Risk level: {risk_level.value} ({len(factors)} contributing factor(s)). Advisory only.",
    )
    application.risk_level = risk_level


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
    _compute_and_persist_risk(db, application, ExtractionStatus.AI_UNAVAILABLE, None, {})
    _mark_pending_review(application, datetime.now(timezone.utc))
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
        _compute_and_persist_risk(db, application, ExtractionStatus.UNREADABLE, None, {})
        _mark_pending_review(application, datetime.now(timezone.utc))
        db.commit()
        return

    extracted_fields = {}
    field_confidences = {}
    for field_name in _EXTRACTED_FIELD_NAMES:
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
    _compute_and_persist_risk(db, application, ExtractionStatus.SUCCESS, extracted_fields, field_confidences)
    _mark_pending_review(application, datetime.now(timezone.utc))
    db.commit()
