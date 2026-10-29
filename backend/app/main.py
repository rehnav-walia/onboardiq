import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.database import Base, engine
from app.rag.ingest_cli import ensure_ingested
from app.routers import applications, auth, documents, policy_assistant, reviewer

logger = logging.getLogger("onboardiq")
# Without this, INFO-level records (e.g. the RAG assistant's retrieved-
# context log, US-30 DoD) are silently dropped by the root logger's default
# WARNING level — "logged for debugging" only actually holds if the log is
# visible without extra configuration.
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Local-dev convenience: create tables if they don't exist yet.
    # A production deployment would use migrations instead.
    Base.metadata.create_all(bind=engine)
    try:
        # Only ingests if nothing has been ingested yet (see ensure_ingested
        # docstring) — keeps a fresh clone's RAG assistant working
        # immediately, per the PRD's "clonable and runnable by a stranger"
        # success criterion, without re-embedding on every restart.
        ensure_ingested()
    except Exception:
        logger.exception("Policy document ingestion failed at startup — the assistant may have no content to use.")
    yield


app = FastAPI(title="OnboardIQ API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(applications.router)
app.include_router(documents.router)
app.include_router(reviewer.router)
app.include_router(policy_assistant.router)
app.include_router(auth.router)


def _field_name(loc: tuple) -> str:
    # loc looks like ("body", "email") — the field name is whatever follows "body".
    return str(loc[-1]) if loc else "form"


def _clean_message(raw_msg: str) -> str:
    # Pydantic v2 prefixes messages raised via `raise ValueError(...)` in a
    # validator with "Value error, " — strip that so only our own
    # plain-language copy reaches the applicant (US-04 DoD).
    prefix = "Value error, "
    return raw_msg[len(prefix):] if raw_msg.startswith(prefix) else raw_msg


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Converts Pydantic's internal error structure into a plain
    {field: message} map so the UI never has to render library internals
    (US-04 DoD)."""
    field_errors: dict[str, str] = {}
    for error in exc.errors():
        field = _field_name(error.get("loc", ()))
        field_errors.setdefault(field, _clean_message(error.get("msg", "Invalid value.")))

    return JSONResponse(
        status_code=422,
        content={
            "message": "Please correct the highlighted fields and try again.",
            "errors": field_errors,
        },
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    # exc.headers is None for every HTTPException raised elsewhere in this
    # codebase (none of them set one) — forwarding it here is additive and
    # changes nothing for those. It matters for rate limiting (app/rate_limit.py),
    # whose 429s set a Retry-After header the client needs to actually see.
    return JSONResponse(status_code=exc.status_code, content={"message": exc.detail, "errors": {}}, headers=exc.headers)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    # Global DoD: no unhandled exception (or its stack trace) may surface to the user.
    logger.exception("Unhandled error while processing %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"message": "Something went wrong on our end. Please try again shortly.", "errors": {}},
    )


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
