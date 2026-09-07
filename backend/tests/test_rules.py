import os
from datetime import date

import pytest

from app.config import get_settings
from app.rules import check_document_expiry, check_future_dated_dob, check_minimum_age


def test_minimum_age_check_flags_a_minor():
    dob = date(2015, 1, 1)
    reference_date = date(2026, 1, 1)  # exactly 11 years old
    flag = check_minimum_age(dob, reference_date)
    assert flag is not None
    assert flag.code == "UNDER_MINIMUM_AGE"
    assert "11" in flag.message


def test_minimum_age_check_passes_an_adult():
    dob = date(1990, 1, 1)
    reference_date = date(2026, 1, 1)
    assert check_minimum_age(dob, reference_date) is None


def test_minimum_age_check_is_exact_on_the_birthday():
    dob = date(2008, 6, 15)
    reference_date = date(2026, 6, 15)  # turns 18 exactly today
    assert check_minimum_age(dob, reference_date) is None


def test_minimum_age_check_flags_the_day_before_the_birthday():
    dob = date(2008, 6, 15)
    reference_date = date(2026, 6, 14)  # still 17
    flag = check_minimum_age(dob, reference_date)
    assert flag is not None


def test_minimum_age_is_configurable():
    """US-17 DoD: minimum age configurable."""
    original = os.environ.get("MINIMUM_APPLICANT_AGE")
    os.environ["MINIMUM_APPLICANT_AGE"] = "21"
    get_settings.cache_clear()
    try:
        dob = date(2007, 1, 1)
        reference_date = date(2026, 1, 1)  # 19 years old
        flag = check_minimum_age(dob, reference_date)
        assert flag is not None
        assert "21" in flag.message
    finally:
        if original is None:
            os.environ.pop("MINIMUM_APPLICANT_AGE", None)
        else:
            os.environ["MINIMUM_APPLICANT_AGE"] = original
        get_settings.cache_clear()


def test_future_dated_dob_is_flagged():
    flag = check_future_dated_dob(date(2027, 1, 1), date(2026, 1, 1))
    assert flag is not None
    assert flag.code == "FUTURE_DATED_DOB"


def test_past_dob_is_not_flagged():
    assert check_future_dated_dob(date(1990, 1, 1), date(2026, 1, 1)) is None


def test_dob_of_today_is_not_future():
    reference_date = date(2026, 1, 1)
    assert check_future_dated_dob(reference_date, reference_date) is None


def test_expired_document_is_flagged():
    flag = check_document_expiry("2020-01-01", date(2026, 1, 1))
    assert flag is not None
    assert flag.code == "DOCUMENT_EXPIRED"


def test_non_expired_document_is_not_flagged():
    assert check_document_expiry("2030-01-01", date(2026, 1, 1)) is None


def test_missing_expiry_is_not_flagged():
    """US-17 AC: "where extractable" — no expiry date at all is not itself a problem."""
    assert check_document_expiry(None, date(2026, 1, 1)) is None


def test_unparseable_expiry_is_not_flagged():
    assert check_document_expiry("not a date", date(2026, 1, 1)) is None


def test_expiry_check_uses_day_first_date_parsing():
    """Consistency with app.verification's deterministic day-first rule —
    01/02/2020 means 1 Feb 2020, which has already passed by 2026."""
    flag = check_document_expiry("01/02/2020", date(2026, 1, 1))
    assert flag is not None
