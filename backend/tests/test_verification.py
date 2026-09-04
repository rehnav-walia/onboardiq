from datetime import date

from app.models import MatchStatus
from app.verification import (
    compare_date_of_birth,
    compare_full_name,
    compare_id_number,
    normalize_text,
    parse_date_of_birth,
)


def test_parse_date_of_birth_resolves_ambiguous_dates_day_first():
    """US-14 AC's own worked example: 01/02/1998 must mean 1 Feb 1998, not
    2 Jan 1998 — the deterministic day-first tie-breaker rule."""
    assert parse_date_of_birth("01/02/1998") == date(1998, 2, 1)


def test_parse_date_of_birth_accepts_iso_format():
    assert parse_date_of_birth("1998-02-01") == date(1998, 2, 1)


def test_parse_date_of_birth_returns_none_for_garbage():
    assert parse_date_of_birth("not a date") is None


# --- Full name -----------------------------------------------------------


def test_name_case_difference_is_a_match():
    status, _ = compare_full_name("JOHN SMITH", "John Smith")
    assert status == MatchStatus.MATCH


def test_name_extra_whitespace_is_a_match():
    status, _ = compare_full_name("John   Smith", "John Smith")
    assert status == MatchStatus.MATCH


def test_name_exact_match():
    status, _ = compare_full_name("Jane Doe", "Jane Doe")
    assert status == MatchStatus.MATCH


def test_name_extra_middle_name_on_document_is_partial_match():
    status, justification = compare_full_name("John Smith", "John Michael Smith")
    assert status == MatchStatus.PARTIAL_MATCH
    assert "Michael" in justification


def test_name_extra_middle_name_on_submission_is_partial_match():
    status, _ = compare_full_name("John Michael Smith", "John Smith")
    assert status == MatchStatus.PARTIAL_MATCH


def test_name_genuinely_different_is_mismatch():
    status, _ = compare_full_name("John Smith", "Michael Jones")
    assert status == MatchStatus.MISMATCH


def test_name_same_length_different_token_is_mismatch():
    """Guards against the subsequence check being too lenient: same number
    of tokens but a different second name must not be waved through."""
    status, _ = compare_full_name("Robert Smith", "Robert Jones")
    assert status == MatchStatus.MISMATCH


def test_name_missing_extraction_is_mismatch():
    status, _ = compare_full_name("Jane Doe", None)
    assert status == MatchStatus.MISMATCH


# --- Date of birth ---------------------------------------------------------


def test_dob_same_date_different_format_is_match():
    """The PRD's own example (US-14 AC)."""
    status, _ = compare_date_of_birth("01/02/1998", "1998-02-01")
    assert status == MatchStatus.MATCH


def test_dob_same_date_dash_vs_slash_is_match():
    status, _ = compare_date_of_birth("15-05-1990", "1990-05-15")
    assert status == MatchStatus.MATCH


def test_dob_genuinely_different_dates_is_mismatch():
    status, _ = compare_date_of_birth("1990-05-15", "1990-06-20")
    assert status == MatchStatus.MISMATCH


def test_dob_unparseable_but_textually_equal_falls_back_to_match():
    status, _ = compare_date_of_birth("circa 1990", "circa 1990")
    assert status == MatchStatus.MATCH


def test_dob_missing_extraction_is_mismatch():
    status, _ = compare_date_of_birth("1990-05-15", None)
    assert status == MatchStatus.MISMATCH


# --- ID number ---------------------------------------------------------


def test_id_number_case_and_dash_difference_is_match():
    status, _ = compare_id_number("A-123456", "a123456")
    assert status == MatchStatus.MATCH


def test_id_number_whitespace_difference_is_match():
    status, _ = compare_id_number("A 123 456", "A123456")
    assert status == MatchStatus.MATCH


def test_id_number_different_values_is_mismatch():
    status, _ = compare_id_number("A123456", "B999999")
    assert status == MatchStatus.MISMATCH


def test_id_number_missing_extraction_is_mismatch():
    status, _ = compare_id_number("A123456", None)
    assert status == MatchStatus.MISMATCH


# --- normalize_text ---------------------------------------------------------


def test_normalize_text_handles_none():
    assert normalize_text(None) == ""


def test_normalize_text_collapses_internal_whitespace():
    assert normalize_text("John    Smith\t") == "JOHN SMITH"
