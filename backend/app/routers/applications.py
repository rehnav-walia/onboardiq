from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import crud
from app.database import get_db
from app.schemas import (
    ApplicationCreate,
    ApplicationExtractionOut,
    ApplicationOut,
    ExtractionFieldOut,
    ExtractionSummaryOut,
    VerificationResultOut,
)

router = APIRouter(prefix="/api/applications", tags=["applications"])


@router.post("", response_model=ApplicationOut, status_code=201)
def submit_application(payload: ApplicationCreate, db: Session = Depends(get_db)) -> ApplicationOut:
    """US-01: creates the Application as SUBMITTED and returns its reference ID.

    payload is an ApplicationCreate — the schema accepts only the fields an
    applicant is meant to set, so there is no way for a client to smuggle in
    a status, reference_id, or any other server-controlled value.
    """
    application = crud.create_application(db, payload)
    return ApplicationOut.model_validate(application)


@router.get("/{reference_id}", response_model=ApplicationOut)
def get_application(reference_id: str, db: Session = Depends(get_db)) -> ApplicationOut:
    application = crud.get_application_by_reference(db, reference_id)
    if application is None:
        raise HTTPException(status_code=404, detail="No application found with that reference ID.")
    return ApplicationOut.model_validate(application)


@router.get("/{reference_id}/extraction", response_model=ApplicationExtractionOut)
def get_extraction(reference_id: str, db: Session = Depends(get_db)) -> ApplicationExtractionOut:
    """Surfaces the AI extraction + cross-verification outcome (US-09..US-14)
    for an application's most recently uploaded document. This is the API
    contract the phase 3 reviewer screen will consume."""
    application = crud.get_application_by_reference(db, reference_id)
    if application is None:
        raise HTTPException(status_code=404, detail="No application found with that reference ID.")

    documents = crud.list_documents(db, application.id)
    extraction_out = None
    if documents:
        latest_document = documents[-1]
        extraction_result = crud.get_latest_extraction_result(db, latest_document.id)
        if extraction_result is not None:
            extraction_out = ExtractionSummaryOut(
                status=extraction_result.status,
                justification=extraction_result.justification,
                created_at=extraction_result.created_at,
                fields={
                    field_name: ExtractionFieldOut.from_stored(field_data)
                    for field_name, field_data in extraction_result.extracted_fields.items()
                },
            )

    if extraction_out is None:
        raise HTTPException(
            status_code=404,
            detail="No extraction result is available yet for this application.",
        )

    verification_results = crud.get_verification_results(db, application.id)
    return ApplicationExtractionOut(
        application_status=application.status,
        flag_count=application.flag_count,
        extraction=extraction_out,
        verification=[VerificationResultOut.model_validate(v) for v in verification_results],
    )
