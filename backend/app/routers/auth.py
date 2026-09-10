from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel

from app import auth, rate_limit

router = APIRouter(prefix="/api/auth", tags=["auth"])


class ReviewerLoginRequest(BaseModel):
    username: str
    password: str


class ReviewerLoginResponse(BaseModel):
    token: str
    username: str


@router.post("/reviewer/login", response_model=ReviewerLoginResponse)
def reviewer_login(payload: ReviewerLoginRequest, request: Request) -> ReviewerLoginResponse:
    """Addition on top of the PRD: rate-limited per client IP (see
    app/rate_limit.py) — only FAILED attempts count, and a successful
    login resets the count, so this only ever slows down repeated wrong
    guesses, never a legitimate reviewer's own access."""
    ip = rate_limit.client_ip(request)
    rate_limit.enforce(rate_limit.login_limiter, ip)

    token = auth.authenticate(payload.username, payload.password)
    if token is None:
        rate_limit.login_limiter.record(ip)
        raise HTTPException(status_code=401, detail="Invalid username or password.")

    rate_limit.login_limiter.reset(ip)
    return ReviewerLoginResponse(token=token, username=payload.username)


@router.post("/reviewer/logout", status_code=204)
def reviewer_logout(authorization: str | None = Header(default=None)) -> None:
    auth.logout(authorization)
