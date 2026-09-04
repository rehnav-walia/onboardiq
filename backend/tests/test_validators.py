from datetime import date, timedelta

import pytest

from app.validators import require_non_blank, validate_date_of_birth, validate_phone


def test_require_non_blank_accepts_and_trims():
    assert require_non_blank("  Jane Doe  ", "Full name") == "Jane Doe"


@pytest.mark.parametrize("value", ["", "   ", None])
def test_require_non_blank_rejects_blank(value):
    with pytest.raises(ValueError, match="is required"):
        require_non_blank(value, "Full name")


def test_dob_today_is_allowed():
    assert validate_date_of_birth(date.today()) == date.today()


def test_dob_in_past_is_allowed():
    dob = date(1990, 1, 1)
    assert validate_date_of_birth(dob) == dob


def test_dob_in_future_is_rejected():
    with pytest.raises(ValueError, match="cannot be in the future"):
        validate_date_of_birth(date.today() + timedelta(days=1))


@pytest.mark.parametrize("value", ["+1 555 123 4567", "5551234567", "(555) 123-4567"])
def test_valid_phone_numbers_pass(value):
    assert validate_phone(value) == value.strip()


def test_blank_phone_is_rejected():
    with pytest.raises(ValueError, match="is required"):
        validate_phone("")


@pytest.mark.parametrize("value", ["123", "not-a-phone", "555-CALL-NOW"])
def test_malformed_phone_numbers_rejected(value):
    with pytest.raises(ValueError, match="valid phone number"):
        validate_phone(value)
