"""Rule-based validity checks (US-17).

These are plain, deterministic functions over already-known data — no LLM
call, no network access. They run unconditionally in the pipeline, so they
still catch obvious problems even when AI extraction is unavailable
(US-17 AC: "Rule checks run independently of the LLM and still function if
AI is unavailable").

Every check takes an explicit reference_date rather than calling
date.today() itself, so each one is independently unit-testable and
reproducible for a fixed "now" (mirrors app/risk.py's determinism
requirement, US-16 DoD).

A flagged rule contributes to the advisory risk score (app/risk.py) exactly
like any other RiskFactor — a rule violation still never blocks submission
or decides anything on its own.
"""

from datetime import date

from app.config import get_settings
from app.risk import RiskFactor
from app.verification import parse_date

POINTS_UNDER_MINIMUM_AGE = 30
POINTS_FUTURE_DATED_DOB = 30
POINTS_EXPIRED_DOCUMENT = 20


def _age_in_years(date_of_birth: date, reference_date: date) -> int:
    had_birthday_this_year = (reference_date.month, reference_date.day) >= (date_of_birth.month, date_of_birth.day)
    return reference_date.year - date_of_birth.year - (0 if had_birthday_this_year else 1)


def check_minimum_age(date_of_birth: date, reference_date: date) -> RiskFactor | None:
    """US-17 AC: applicant under minimum age is flagged.
    DoD: minimum age is configurable (MINIMUM_APPLICANT_AGE), not hardcoded.
    """
    minimum_age = get_settings().minimum_applicant_age
    age = _age_in_years(date_of_birth, reference_date)
    if age < minimum_age:
        return RiskFactor(
            code="UNDER_MINIMUM_AGE",
            message=f"Applicant appears to be {age} years old, below the minimum age of {minimum_age}.",
            points=POINTS_UNDER_MINIMUM_AGE,
        )
    return None


def check_future_dated_dob(date_of_birth: date, reference_date: date) -> RiskFactor | None:
    """US-17 AC: future-dated date of birth is flagged.

    In practice, a future submitted DOB can never reach this point — US-01's
    intake validation already rejects it outright. This check exists for a
    date of birth read off the *document* by the AI, which intake validation
    has no way to touch, and as an explicit, documented safety net rather
    than relying solely on that earlier check.
    """
    if date_of_birth > reference_date:
        return RiskFactor(
            code="FUTURE_DATED_DOB",
            message=f"Date of birth ({date_of_birth.isoformat()}) is in the future.",
            points=POINTS_FUTURE_DATED_DOB,
        )
    return None


def check_document_expiry(expiry_date_text: str | None, reference_date: date) -> RiskFactor | None:
    """US-17 AC: expired document, where expiry is extractable, is flagged.
    "Where extractable" is literal — many ID documents (e.g. some national
    ID cards) don't show an expiry date at all, and the AI may not always
    find one; both show up as expiry_date_text being None/unparseable, which
    this treats as "nothing to flag," not as a problem in itself.
    """
    expiry_date = parse_date(expiry_date_text)
    if expiry_date is None:
        return None
    if expiry_date < reference_date:
        return RiskFactor(
            code="DOCUMENT_EXPIRED",
            message=f"The document's expiry date ({expiry_date.isoformat()}) has passed.",
            points=POINTS_EXPIRED_DOCUMENT,
        )
    return None
