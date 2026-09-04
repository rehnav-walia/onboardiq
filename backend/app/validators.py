"""Server-side validation rules for application intake (US-01, US-04).

These duplicate the frontend's checks by design: the frontend's checks are a
UX convenience, these are the ones that actually protect the data — a
crafted API request that skips the browser entirely still has to pass
through here (US-01 DoD).
"""

import re
from datetime import date

PHONE_PATTERN = re.compile(r"^\+?[0-9\s\-()]{7,20}$")


def require_non_blank(value: str, label: str) -> str:
    if value is None or not value.strip():
        raise ValueError(f"{label} is required.")
    return value.strip()


def validate_date_of_birth(value: date) -> date:
    if value > date.today():
        raise ValueError("Date of birth cannot be in the future.")
    return value


def validate_phone(value: str) -> str:
    value = require_non_blank(value, "Phone number")
    digit_count = len(re.sub(r"\D", "", value))
    if not PHONE_PATTERN.match(value) or not (7 <= digit_count <= 15):
        raise ValueError("Enter a valid phone number, e.g. +1 555 123 4567.")
    return value
