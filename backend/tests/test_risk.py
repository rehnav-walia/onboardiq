from app.models import ExtractionStatus, MatchStatus, RiskLevel
from app.risk import RiskFactor, assess_risk


def _assess(**overrides):
    kwargs = dict(
        verification_results=[],
        extraction_status=ExtractionStatus.SUCCESS,
        field_confidences={},
        low_confidence_threshold=0.7,
        declared_type_mismatch=None,
        rule_flags=[],
    )
    kwargs.update(overrides)
    return assess_risk(**kwargs)


def test_no_issues_at_all_is_low_risk():
    level, factors = _assess(
        verification_results=[("full_name", MatchStatus.MATCH), ("id_number", MatchStatus.MATCH)],
    )
    assert level == RiskLevel.LOW
    assert factors == []


def test_is_deterministic_for_identical_inputs():
    """US-16 DoD: same input produces same output across runs."""
    args = dict(
        verification_results=[("id_number", MatchStatus.MISMATCH)],
        extraction_status=ExtractionStatus.SUCCESS,
        field_confidences={"full_name": 0.4},
        low_confidence_threshold=0.7,
        declared_type_mismatch=None,
        rule_flags=[RiskFactor(code="UNDER_MINIMUM_AGE", message="x", points=30)],
    )
    first = assess_risk(**args)
    second = assess_risk(**args)
    third = assess_risk(**args)
    assert first == second == third


def test_single_mismatch_alone_is_not_high_risk():
    level, factors = _assess(verification_results=[("id_number", MatchStatus.MISMATCH)])
    assert level != RiskLevel.HIGH
    assert len(factors) == 1
    assert factors[0].code == "MISMATCH_ID_NUMBER"


def test_partial_match_contributes_less_than_mismatch():
    _, mismatch_factors = _assess(verification_results=[("full_name", MatchStatus.MISMATCH)])
    _, partial_factors = _assess(verification_results=[("full_name", MatchStatus.PARTIAL_MATCH)])
    assert partial_factors[0].points < mismatch_factors[0].points


def test_match_contributes_no_factor():
    _, factors = _assess(verification_results=[("full_name", MatchStatus.MATCH)])
    assert factors == []


def test_unreadable_document_is_a_named_factor():
    level, factors = _assess(extraction_status=ExtractionStatus.UNREADABLE, verification_results=[])
    codes = [f.code for f in factors]
    assert "DOCUMENT_UNREADABLE" in codes


def test_ai_unavailable_is_a_named_factor():
    level, factors = _assess(extraction_status=ExtractionStatus.AI_UNAVAILABLE, verification_results=[])
    codes = [f.code for f in factors]
    assert "AI_UNAVAILABLE" in codes


def test_low_confidence_field_is_flagged_against_given_threshold():
    _, factors = _assess(
        extraction_status=ExtractionStatus.SUCCESS,
        field_confidences={"full_name": 0.5, "id_number": 0.95},
        low_confidence_threshold=0.7,
    )
    codes = [f.code for f in factors]
    assert "LOW_CONFIDENCE_FULL_NAME" in codes
    assert "LOW_CONFIDENCE_ID_NUMBER" not in codes


def test_declared_type_mismatch_is_a_named_factor_when_true():
    _, factors = _assess(declared_type_mismatch=True)
    assert any(f.code == "DECLARED_TYPE_MISMATCH" for f in factors)


def test_declared_type_mismatch_none_contributes_nothing():
    """Today this is always None — US-15 (declared type capture) isn't
    built — and that must not silently score as a mismatch."""
    _, factors = _assess(declared_type_mismatch=None)
    assert not any(f.code == "DECLARED_TYPE_MISMATCH" for f in factors)


def test_rule_flags_are_included_in_the_factor_list():
    flag = RiskFactor(code="UNDER_MINIMUM_AGE", message="Applicant is 12.", points=30)
    _, factors = _assess(rule_flags=[flag])
    assert flag in factors


def test_combining_enough_factors_reaches_high_risk():
    level, factors = _assess(
        extraction_status=ExtractionStatus.AI_UNAVAILABLE,
        rule_flags=[RiskFactor(code="UNDER_MINIMUM_AGE", message="x", points=30)],
    )
    assert level == RiskLevel.HIGH


def test_risk_level_never_appears_without_its_factors_being_inspectable():
    """US-18 AC: contributing factors, not just a bare level."""
    level, factors = _assess(verification_results=[("full_name", MatchStatus.MISMATCH)])
    assert level is not None
    assert all(isinstance(f, RiskFactor) and f.message for f in factors)
