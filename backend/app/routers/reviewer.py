from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import crud
from app.auth import require_reviewer
from app.config import get_settings
from app.database import get_db
from app.models import ApplicationStatus, RiskLevel
from app.schemas import QueueItemOut, QueueOut

router = APIRouter(prefix="/api/reviewer", tags=["reviewer"])

_MAX_PAGE_SIZE = 100
_QUEUE_STATUSES = (ApplicationStatus.PENDING_REVIEW, ApplicationStatus.INFO_REQUESTED)
_SORT_FIELDS = ("submitted_at", "risk_level")
_SORT_DIRECTIONS = ("asc", "desc")


@router.get("/queue", response_model=QueueOut)
def get_queue(
    limit: int = 20,
    offset: int = 0,
    status: ApplicationStatus | None = None,
    risk_level: RiskLevel | None = None,
    sort_by: str = "submitted_at",
    sort_dir: str = "asc",
    overdue_only: bool = False,
    _reviewer: str = Depends(require_reviewer),
    db: Session = Depends(get_db),
) -> QueueOut:
    """US-19/US-20/US-21: paginated, filterable, sortable list of
    applications awaiting a decision, with ageing visibility.

    Server-side LIMIT/OFFSET pagination (US-19 DoD) and server-side
    filtering/sorting (US-20 DoD) — all exercised together in
    tests/test_reviewer_queue.py against a 50+ row seeded dataset.

    Reviewer login required (additive, out-of-PRD-scope — see app/auth.py):
    `_reviewer` is unused beyond gating access, since the queue itself
    doesn't depend on who's viewing it.
    """
    if not (1 <= limit <= _MAX_PAGE_SIZE):
        raise HTTPException(status_code=400, detail=f"limit must be between 1 and {_MAX_PAGE_SIZE}.")
    if offset < 0:
        raise HTTPException(status_code=400, detail="offset must be zero or greater.")
    if status is not None and status not in _QUEUE_STATUSES:
        raise HTTPException(
            status_code=400,
            detail="status must be PENDING_REVIEW or INFO_REQUESTED — no other status ever appears in the queue.",
        )
    if sort_by not in _SORT_FIELDS:
        raise HTTPException(status_code=400, detail=f"sort_by must be one of {_SORT_FIELDS}.")
    if sort_dir not in _SORT_DIRECTIONS:
        raise HTTPException(status_code=400, detail=f"sort_dir must be one of {_SORT_DIRECTIONS}.")

    total, items = crud.list_queue(
        db,
        limit=limit,
        offset=offset,
        status=status,
        risk_level=risk_level,
        sort_by=sort_by,
        sort_dir=sort_dir,
        overdue_only=overdue_only,
    )
    overdue_threshold_hours = get_settings().overdue_threshold_hours
    return QueueOut(
        total=total,
        limit=limit,
        offset=offset,
        items=[QueueItemOut.from_application(item, overdue_threshold_hours) for item in items],
    )
