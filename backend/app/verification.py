"""Cross-verification of submitted vs. extracted data (US-13, US-14).

Normalization rules (US-14 DoD requires these documented, not left implicit):

- Text fields: trimmed, whitespace runs collapsed to a single space, and
  compared case-insensitively.
- Full name: compared as a sequence of tokens. If the tokens on one side are
  a subsequence of the other's (i.e. one side has one or more extra name
  components, such as a middle name), that's a PARTIAL_MATCH, not a
  MISMATCH. Any other token difference is a MISMATCH.
- ID number: normalized the same way as text, with internal whitespace and
  hyphens also removed before comparing (ID numbers are often re-typed with
  different grouping), then compared exactly.
- Date of birth: parsed via parse_date, which resolves ambiguous numeric
  dates (DD/MM/YYYY vs MM/DD/YYYY) by ALWAYS treating them as day-first.
  This is a fixed, explicit rule, not a guess — the PRD's own worked
  example (US-14 AC) requires "01/02/1998" to match "1998-02-01", i.e.
  1 February 1998, which is only true under a day-first reading.

parse_date is a general date parser (not DOB-specific) — app/rules.py
reuses it for document expiry dates (US-17), so the same day-first rule
applies consistently everywhere a date string from the LLM is parsed.
"""

import re
from datetime import date, datetime

from app.models import MatchStatus

_WHITESPACE_RE = re.compile(r"\s+")

# Ordered so ISO (unambiguous) is tried first; the rest are all read
# day-first, per the module docstring's deterministic tie-breaker rule.
_DAY_FIRST_DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y")


def normalize_text(value: str | None) -> str:
    if value is None:
        return ""
    return _WHITESPACE_RE.sub(" ", value.strip()).upper()


def parse_date(value: str | None) -> date | None:
    if not value or not value.strip():
        return None
    text = value.strip()
    for fmt in _DAY_FIRST_DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _is_subsequence(shorter: list[str], longer: list[str]) -> bool:
    it = 0
    for token in longer:
        if it < len(shorter) and token == shorter[it]:
            it += 1
    return it == len(shorter)


def compare_full_name(submitted: str, extracted: str | None) -> tuple[MatchStatus, str]:
    if extracted is None or not extracted.strip():
        return MatchStatus.MISMATCH, "The document did not yield a legible full name to compare."

    norm_submitted = normalize_text(submitted)
    norm_extracted = normalize_text(extracted)
    if norm_submitted == norm_extracted:
        return MatchStatus.MATCH, "Full name on the document matches the submitted name (ignoring case and spacing)."

    tokens_submitted = norm_submitted.split()
    tokens_extracted = norm_extracted.split()
    shorter, longer = (
        (tokens_submitted, tokens_extracted)
        if len(tokens_submitted) <= len(tokens_extracted)
        else (tokens_extracted, tokens_submitted)
    )
    if len(longer) > len(shorter) and _is_subsequence(shorter, longer):
        extra_tokens = [t for t in longer if t not in shorter]
        extra = " ".join(extra_tokens).title()
        return MatchStatus.PARTIAL_MATCH, (
            f"Names match except for an additional name component ('{extra}') present on only one "
            "side — likely a middle name."
        )

    return MatchStatus.MISMATCH, (
        f"Submitted full name ('{submitted.strip()}') does not match the name on the document "
        f"('{extracted.strip()}')."
    )


def compare_date_of_birth(submitted: str, extracted: str | None) -> tuple[MatchStatus, str]:
    if extracted is None or not extracted.strip():
        return MatchStatus.MISMATCH, "The document did not yield a legible date of birth to compare."

    submitted_date = parse_date(submitted)
    extracted_date = parse_date(extracted)

    if submitted_date is not None and extracted_date is not None:
        if submitted_date == extracted_date:
            return MatchStatus.MATCH, "Date of birth matches between the application and the document."
        return MatchStatus.MISMATCH, (
            f"Submitted date of birth ({submitted}) does not match the document's date of birth "
            f"({extracted})."
        )

    # Neither side parsed as a recognized date format — fall back to a plain
    # normalized-text comparison rather than silently calling it a mismatch.
    if normalize_text(submitted) == normalize_text(extracted):
        return MatchStatus.MATCH, "Date of birth matches between the application and the document."
    return MatchStatus.MISMATCH, (
        f"Submitted date of birth ({submitted}) could not be confirmed against the document's date "
        f"of birth ({extracted})."
    )


def compare_id_number(submitted: str, extracted: str | None) -> tuple[MatchStatus, str]:
    if extracted is None or not extracted.strip():
        return MatchStatus.MISMATCH, "The document did not yield a legible ID number to compare."

    norm_submitted = normalize_text(submitted).replace(" ", "").replace("-", "")
    norm_extracted = normalize_text(extracted).replace(" ", "").replace("-", "")
    if norm_submitted == norm_extracted:
        return MatchStatus.MATCH, "ID number matches between the application and the document."
    return MatchStatus.MISMATCH, (
        f"Submitted ID number ('{submitted.strip()}') does not match the document's ID number "
        f"('{extracted.strip()}')."
    )


# US-13 AC: "Comparison covers at minimum: name, date of birth, ID number."
FIELD_COMPARATORS = {
    "full_name": compare_full_name,
    "date_of_birth": compare_date_of_birth,
    "id_number": compare_id_number,
}
