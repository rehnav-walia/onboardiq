from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from app import auth

router = APIRouter(prefix="/api/auth", tags=["auth"])


class ReviewerLoginRequest(BaseModel):
    username: str
    password: str


class ReviewerLoginResponse(BaseModel):
    token: str
    username: str


@router.post("/reviewer/login", response_model=ReviewerLoginResponse)
def reviewer_login(payload: ReviewerLoginRequest) -> ReviewerLoginResponse:
    token = auth.authenticate(payload.username, payload.password)
    if token is None:
        raise HTTPException(status_code=401, detail="Invalid username or password.")
    return ReviewerLoginResponse(token=token, username=payload.username)


@router.post("/reviewer/logout", status_code=204)
def reviewer_logout(authorization: str | None = Header(default=None)) -> None:
    auth.logout(authorization)
