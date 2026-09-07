"""Standalone ingestion entrypoint (US-29). Run from backend/:

    python -m app.rag.ingest_cli

Idempotent — safe to re-run any time policy documents change; existing
chunks for a changed document are replaced, not duplicated. Also runs
automatically on API startup (see app/main.py's lifespan) so a fresh clone
works immediately, per the PRD's "clonable and runnable by a stranger"
success criterion.
"""

from app.config import get_settings
from app.rag.store import count_chunks, ingest_directory


def run_ingestion() -> dict[str, int]:
    """Unconditional: always deletes and re-adds every document's chunks.
    This is the explicit "I changed the policy documents, re-ingest them"
    operation — used by the CLI and by idempotency tests."""
    settings = get_settings()
    return ingest_directory(settings.policy_documents_dir)


def ensure_ingested() -> None:
    """Startup convenience (called from app/main.py's lifespan): only
    ingests if the collection is currently empty, so repeated app restarts
    (or, in tests, repeated TestClient instantiations) don't needlessly
    re-embed unchanged documents every time. Editing a policy document
    requires an explicit run_ingestion() call (the CLI) to pick it up."""
    if count_chunks() == 0:
        run_ingestion()


def main() -> None:
    results = run_ingestion()
    total = sum(results.values())
    print(f"Ingested {len(results)} document(s), {total} chunk(s) total:")
    for filename, count in sorted(results.items()):
        print(f"  {filename}: {count} chunk(s)")


if __name__ == "__main__":
    main()
