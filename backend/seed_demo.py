"""Seeds exactly one demo application for recording the product walkthrough
(submit -> reviewer login -> queue -> mismatch flag + risk breakdown ->
approve -> audit log).

Run from the `backend/` directory, with the same virtualenv the app itself
uses:

    python seed_demo.py            # seeds only if the database is empty
    python seed_demo.py --reset    # wipes the dev database + storage, then seeds fresh

Without --reset, this refuses to run (and touches nothing) if any
application already exists, so it's safe to re-run by accident — it will
never seed a second demo application alongside real or prior data. --reset
is the deliberate, explicit way to start over: it deletes the SQLite
database file and the uploaded-document storage directory before seeding,
the same manual reset steps documented in README "Running locally".

Deliberately does not call the real AI extraction pipeline (app/pipeline.py)
end to end: that call is non-deterministic (depends on ANTHROPIC_API_KEY
being set, on the live model's exact wording, on network availability) and
this script's whole point is a reproducible demo. Instead it writes the
same rows app/pipeline.py would have written for a SUCCESSFUL extraction
(ExtractionResult, VerificationResult, Document.detected_type/type_mismatch),
with hand-picked field values, and then calls the real, deterministic
app.risk.assess_risk — the same function the live pipeline calls — so the
resulting risk level and factors are computed by production code, not
hardcoded here.

The scenario: a declared PASSPORT that the (simulated) AI reads as a
NATIONAL_ID, plus an ID number transposed by one digit versus what the
applicant typed, plus a low-confidence read on that same field. That's
three distinct, plain-language contributing factors — a clear mismatch
flag and a HIGH advisory risk level on first view, landing the application
in the reviewer queue exactly as PENDING_REVIEW, ready to be approved on
camera with typed-in reasoning.
"""

import argparse
import shutil
import struct
import sys
import zlib
from datetime import date, datetime, timezone
from io import BytesIO
from pathlib import Path

from fastapi import UploadFile

from app import crud, storage
from app.config import get_settings
from app.database import Base, SessionLocal, engine
from app.models import AccountType, Application, ApplicationStatus, DocumentType, ExtractionStatus, MatchStatus
from app.risk import assess_risk
from app.schemas import ApplicationCreate

LOW_CONFIDENCE_THRESHOLD = 0.7


def _make_png(width: int, height: int, rgb: tuple[int, int, int]) -> bytes:
    """Builds a tiny, spec-valid, solid-color PNG (8-bit RGB, no filter,
    zlib-compressed) with correct chunk lengths and CRC32s — generated from
    the stdlib, not hand-copied magic bytes, so it's guaranteed to actually
    decode (a hand-typed PNG hex blob is exactly the kind of thing that
    LOOKS like a valid file to a magic-byte sniffer but silently fails to
    decode in a real browser — not worth that risk for a demo asset)."""

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    signature = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)  # 8-bit depth, RGB color type
    row = bytes([0]) + bytes(rgb) * width  # leading filter-type-0 byte per row
    raw = row * height
    idat = zlib.compress(raw)
    return signature + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")


# A light, neutral placeholder rectangle standing in for a scanned ID photo
# — real, valid PNG bytes so storage.save_upload's magic-byte sniffing and
# the browser's actual <img> decode both succeed end to end.
_DEMO_PNG_BYTES = _make_png(600, 380, (214, 224, 235))


def _ensure_tables() -> None:
    Base.metadata.create_all(bind=engine)


def _reset_dev_data() -> None:
    """Wipes the dev SQLite database file and the uploaded-document storage
    directory — the same two things the README's manual reset covers —
    before a fresh seed. Only called when --reset is passed explicitly."""
    db_path_str = engine.url.database
    if db_path_str and db_path_str != ":memory:":
        db_path = Path(db_path_str)
        if db_path.exists():
            try:
                db_path.unlink()
            except PermissionError:
                sys.exit(
                    f"Could not delete {db_path} — it looks like the backend dev server is "
                    "still running and holding it open. Stop it, then re-run with --reset."
                )

    storage_root = Path(get_settings().storage_root)
    if storage_root.exists():
        shutil.rmtree(storage_root)


def _build_upload_file() -> UploadFile:
    return UploadFile(filename="passport_front.png", file=BytesIO(_DEMO_PNG_BYTES))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Wipe the dev database and uploaded-document storage before seeding.",
    )
    args = parser.parse_args()

    if args.reset:
        _reset_dev_data()

    _ensure_tables()
    db = SessionLocal()
    try:
        if not args.reset and db.query(Application).first() is not None:
            sys.exit(
                "Refusing to seed: the database already has at least one application. "
                "Re-run with --reset to wipe the dev database and storage first, or this "
                "script will not touch existing data."
            )

        application = crud.create_application(
            db,
            ApplicationCreate(
                full_name="Amara Osei-Boateng",
                date_of_birth=date(1992, 5, 14),
                id_number="P4487219",
                address="14 Marlowe Court, Leicester, LE1 6TF",
                email="amara.osei@example.com",
                phone="+44 7700 900482",
                account_type=AccountType.CURRENT,
            ),
        )

        stored = storage.save_upload(application.id, _build_upload_file())
        document = crud.create_document(
            db,
            application,
            original_filename="passport_front.png",
            stored=stored,
            declared_type=DocumentType.PASSPORT,
        )

        now = datetime.now(timezone.utc)
        crud.create_audit_log_entry(
            db,
            application_id=application.id,
            actor="system",
            action="PROCESSING_STARTED",
            details="Document received; AI extraction started.",
        )

        # --- Simulated extraction result (what app/pipeline.py would have
        # written for a SUCCESS response) -----------------------------------
        extracted_fields = {
            "full_name": {
                "value": "Amara Osei-Boateng",
                "confidence": 0.95,
                "justification": "Full name printed clearly on the document's data page.",
            },
            "date_of_birth": {
                "value": "1992-05-14",
                "confidence": 0.93,
                "justification": "Date of birth printed clearly on the document's data page.",
            },
            "id_number": {
                "value": "P4487210",
                "confidence": 0.58,
                "justification": (
                    "Document number partially obscured by a glare on the laminate — last two "
                    "digits were the least legible part of the scan."
                ),
            },
            "document_type": {
                "value": "NATIONAL_ID",
                "confidence": 0.89,
                "justification": "Document layout and field set match a national ID card, not a passport.",
            },
            "expiry_date": {
                "value": "15/03/2029",
                "confidence": 0.9,
                "justification": "Expiry date printed clearly on the document's data page.",
            },
        }
        field_confidences = {name: data["confidence"] for name, data in extracted_fields.items()}
        overall_justification = (
            "Document was legible overall. Name and date of birth match the application. The ID "
            "number and detected document type did not match what the applicant declared."
        )

        crud.create_extraction_result(
            db,
            document_id=document.id,
            status=ExtractionStatus.SUCCESS,
            extracted_fields=extracted_fields,
            field_confidences=field_confidences,
            justification=overall_justification,
        )
        crud.create_audit_log_entry(
            db,
            application_id=application.id,
            actor="system",
            action="EXTRACTION_SUCCEEDED",
            details=overall_justification,
        )

        # US-15: declared vs. detected document type.
        crud.record_document_type_check(db, document, detected_type=extracted_fields["document_type"]["value"])

        # US-13/US-14: cross-verification, field by field.
        verification_fields = [
            ("full_name", application.full_name, extracted_fields["full_name"]["value"]),
            ("date_of_birth", application.date_of_birth.isoformat(), extracted_fields["date_of_birth"]["value"]),
            ("id_number", application.id_number, extracted_fields["id_number"]["value"]),
        ]
        flag_count = 0
        verification_results = []
        for field_name, submitted_value, extracted_value in verification_fields:
            if submitted_value == extracted_value:
                match_status = MatchStatus.MATCH
                justification = f"{field_name.replace('_', ' ').title()} matches between the application and the document."
            else:
                match_status = MatchStatus.MISMATCH
                justification = (
                    f"Submitted {field_name.replace('_', ' ')} ('{submitted_value}') does not match the "
                    f"document's {field_name.replace('_', ' ')} ('{extracted_value}')."
                )
                flag_count += 1
            crud.create_verification_result(
                db,
                application_id=application.id,
                document_id=document.id,
                field_name=field_name,
                submitted_value=submitted_value,
                extracted_value=extracted_value,
                match_status=match_status,
                justification=justification,
            )
            verification_results.append((field_name, match_status))

        crud.create_audit_log_entry(
            db,
            application_id=application.id,
            actor="system",
            action="VERIFICATION_COMPLETED",
            details=f"{flag_count} of {len(verification_fields)} compared field(s) flagged as mismatched.",
        )
        application.flag_count = flag_count

        # US-16/US-18: the real, deterministic risk function — not a
        # hardcoded level — decides LOW/MEDIUM/HIGH from these inputs.
        risk_level, factors = assess_risk(
            verification_results=verification_results,
            extraction_status=ExtractionStatus.SUCCESS,
            field_confidences=field_confidences,
            low_confidence_threshold=LOW_CONFIDENCE_THRESHOLD,
            declared_type_mismatch=document.type_mismatch,
            rule_flags=[],
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
        application.status = ApplicationStatus.PENDING_REVIEW
        application.pending_review_since = now
        db.commit()
        db.refresh(application)

        print("Seeded one demo application:")
        print(f"  reference_id: {application.reference_id}")
        print(f"  status:       {application.status.value}")
        print(f"  flag_count:   {application.flag_count}")
        print(f"  risk_level:   {application.risk_level.value}")
        print(f"  factors:      {[f.code for f in factors]}")
        print()
        print("Reviewer login: reviewer_1 / changeme123")
        print(f"Open the queue at http://localhost:5173 and look for {application.reference_id}.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
