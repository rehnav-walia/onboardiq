"""Composite risk scoring (US-16).

ADVISORY ONLY. A RiskLevel exists purely to help a human reviewer prioritise
attention — nothing in this codebase may use it to gate, block, auto-approve,
or auto-reject an application (CLAUDE.md non-negotiable #1; see also
tests/test_no_auto_approval.py, which asserts this). The review screen shows
it alongside its contributing factors so a HIGH risk application can still be
approved by a human who disagrees with the score (US-18).

Deterministic (US-16 DoD): assess_risk is a pure function of its arguments —
no clock, no I/O, no LLM call. Given the same verification results,
extraction status, confidences, and rule flags, it always returns the same
level and the same factor list. Time-dependent inputs (e.g. the applicant's
current age) are computed by the caller (app/rules.py, given an explicit
reference_date) and passed in as already-evaluated RuleFlag objects — that
keeps this module itself free of hidden non-determinism.

Scoring is a simple additive point system, documented here rather than
scattered across the codebase: each contributing condition adds points,
and the total is bucketed into LOW/MEDIUM/HIGH by two thresholds. Changing
the weights changes the score; changing the thresholds changes the
bucketing — both are plain module constants, not magic numbers buried in
logic.
"""

from dataclasses import dataclass

from app.models import ExtractionStatus, MatchStatus, RiskLevel


@dataclass(frozen=True)
class RiskFactor:
    code: str
    message: str
    points: int


# --- Scoring weights ---------------------------------------------------

POINTS_PER_MISMATCH = 15
POINTS_PER_PARTIAL_MATCH = 5
POINTS_UNREADABLE_DOCUMENT = 40
POINTS_AI_UNAVAILABLE = 25
POINTS_LOW_CONFIDENCE_FIELD = 10
POINTS_DECLARED_TYPE_MISMATCH = 20

# --- Bucketing thresholds -----------------------------------------------

MEDIUM_THRESHOLD = 20
HIGH_THRESHOLD = 45


def _bucket(total_points: int) -> RiskLevel:
    if total_points >= HIGH_THRESHOLD:
        return RiskLevel.HIGH
    if total_points >= MEDIUM_THRESHOLD:
        return RiskLevel.MEDIUM
    return RiskLevel.LOW


def _field_label(field_name: str) -> str:
    return field_name.replace("_", " ").title()


def assess_risk(
    *,
    verification_results: list[tuple[str, MatchStatus]],
    extraction_status: ExtractionStatus | None,
    field_confidences: dict[str, float],
    low_confidence_threshold: float,
    declared_type_mismatch: bool | None,
    rule_flags: list[RiskFactor],
) -> tuple[RiskLevel, list[RiskFactor]]:
    """Combines mismatch severity, document readability, extraction
    confidence, declared-type mismatch, and pre-computed rule flags into one
    advisory RiskLevel plus the list of factors that produced it.

    declared_type_mismatch is None whenever there's nothing to compare yet
    (the applicant didn't declare a type, or extraction hasn't produced a
    detected one) — see app.verification.compare_document_type (US-15),
    which is what actually computes the True/False/None value this function
    receives.
    """
    factors: list[RiskFactor] = []

    for field_name, match_status in verification_results:
        if match_status == MatchStatus.MISMATCH:
            factors.append(
                RiskFactor(
                    code=f"MISMATCH_{field_name.upper()}",
                    message=f"{_field_label(field_name)} does not match between the application and the document.",
                    points=POINTS_PER_MISMATCH,
                )
            )
        elif match_status == MatchStatus.PARTIAL_MATCH:
            factors.append(
                RiskFactor(
                    code=f"PARTIAL_MATCH_{field_name.upper()}",
                    message=f"{_field_label(field_name)} only partially matches (e.g. an extra name component).",
                    points=POINTS_PER_PARTIAL_MATCH,
                )
            )

    if extraction_status == ExtractionStatus.UNREADABLE:
        factors.append(
            RiskFactor(
                code="DOCUMENT_UNREADABLE",
                message="The uploaded document could not be read by the AI, so identity could not be verified automatically.",
                points=POINTS_UNREADABLE_DOCUMENT,
            )
        )
    elif extraction_status == ExtractionStatus.AI_UNAVAILABLE:
        factors.append(
            RiskFactor(
                code="AI_UNAVAILABLE",
                message="AI extraction was unavailable, so identity could not be verified automatically and needs full manual review.",
                points=POINTS_AI_UNAVAILABLE,
            )
        )
    elif extraction_status == ExtractionStatus.SUCCESS:
        for field_name, confidence in field_confidences.items():
            if confidence < low_confidence_threshold:
                factors.append(
                    RiskFactor(
                        code=f"LOW_CONFIDENCE_{field_name.upper()}",
                        message=f"{_field_label(field_name)} was extracted from the document with low confidence.",
                        points=POINTS_LOW_CONFIDENCE_FIELD,
                    )
                )

    if declared_type_mismatch:
        factors.append(
            RiskFactor(
                code="DECLARED_TYPE_MISMATCH",
                message="The declared document type does not match the type detected by the AI.",
                points=POINTS_DECLARED_TYPE_MISMATCH,
            )
        )

    factors.extend(rule_flags)

    total_points = sum(factor.points for factor in factors)
    return _bucket(total_points), factors
