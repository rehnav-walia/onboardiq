from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import crud
from app.database import get_db
from app.schemas import QueueItemOut, QueueOut

router = APIRouter(prefix="/api/reviewer", tags=["reviewer"])

_MAX_PAGE_SIZE = 100


@router.get("/queue", response_model=QueueOut)
def get_queue(limit: int = 20, offset: int = 0, db: Session = Depends(get_db)) -> QueueOut:
    """US-19: paginated list of applications awaiting a decision.

    Server-side LIMIT/OFFSET pagination (DoD: "does not degrade with
    volume") — a 50+ row seeded dataset is exercised in
    tests/test_reviewer_queue.py.
    """
    if not (1 <= limit <= _MAX_PAGE_SIZE):
        raise HTTPException(status_code=400, detail=f"limit must be between 1 and {_MAX_PAGE_SIZE}.")
    if offset < 0:
        raise HTTPException(status_code=400, detail="offset must be zero or greater.")

    total, items = crud.list_queue(db, limit=limit, offset=offset)
    return QueueOut(
        total=total,
        limit=limit,
        offset=offset,
        items=[QueueItemOut.model_validate(item) for item in items],
    )
