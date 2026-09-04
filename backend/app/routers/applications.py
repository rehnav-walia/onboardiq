from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import crud
from app.database import get_db
from app.schemas import ApplicationCreate, ApplicationOut

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
