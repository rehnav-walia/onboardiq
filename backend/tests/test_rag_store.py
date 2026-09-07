"""Real, non-mocked tests against the local Chroma store (US-29).

These use the actual embedding model and the actual sample documents
shipped in backend/policy_documents/ — the session-scoped
`_ingest_real_policy_documents` fixture in conftest.py has already run
real ingestion before any test here executes. Nothing here is mocked;
only the LLM answer-synthesis step (tested separately in
test_rag_assistant.py) needs mocking, since that's the one part that
genuinely requires a paid API call.
"""

from app.config import get_settings
from app.rag import store

_POLICY_DOCS_EXPECTED = {"account_types_faq.md", "processing_timelines.md", "required_documents.md"}


def test_real_sample_documents_were_ingested_with_chunks():
    """US-29 DoD: sample policy documents are committed to the repo and
    actually ingest into real chunks."""
    for doc_name in _POLICY_DOCS_EXPECTED:
        chunks = store.list_chunks_for_document(doc_name)
        assert len(chunks) > 0, f"expected at least one chunk for {doc_name}"


def test_ingest_directory_reports_chunk_counts_per_file():
    """US-29 AC: ingestion reports how many chunks were created."""
    settings = get_settings()
    results = store.ingest_directory(settings.policy_documents_dir)
    assert set(results.keys()) == _POLICY_DOCS_EXPECTED
    assert all(count > 0 for count in results.values())


def test_ingestion_is_idempotent_when_run_twice():
    """US-29 AC/DoD: re-running ingestion does not create duplicate
    entries — verified by actually running it twice and comparing state."""
    settings = get_settings()

    first_results = store.ingest_directory(settings.policy_documents_dir)
    count_after_first = store.count_chunks()

    second_results = store.ingest_directory(settings.policy_documents_dir)
    count_after_second = store.count_chunks()

    assert first_results == second_results
    assert count_after_first == count_after_second

    # No duplicate chunk ids for any document.
    for doc_name in _POLICY_DOCS_EXPECTED:
        chunks = store.list_chunks_for_document(doc_name)
        ids = [c.chunk_id for c in chunks]
        assert len(ids) == len(set(ids)), f"duplicate chunk ids found for {doc_name}"


def test_reingesting_a_shrunk_document_removes_stale_chunks():
    """Idempotency must also handle content changes, not just repeats:
    a document that goes from two sections to one must not leave the old
    second section's chunk behind."""
    store.ingest_document("temp_doc.md", "## First\nBody one.\n\n## Second\nBody two.\n")
    assert len(store.list_chunks_for_document("temp_doc.md")) == 2

    store.ingest_document("temp_doc.md", "## OnlySection\nJust one now.\n")
    remaining = store.list_chunks_for_document("temp_doc.md")
    assert len(remaining) == 1
    assert remaining[0].section_reference == "OnlySection"

    # Clean up so this synthetic doc doesn't linger in the shared test collection.
    store.ingest_document("temp_doc.md", "")
    assert store.list_chunks_for_document("temp_doc.md") == []


def test_retrieval_returns_the_relevant_document_for_a_real_question():
    """US-29 AC: retrieval returns the top-k relevant chunks for a query —
    exercised with a real question against the real embedded documents."""
    results = store.retrieve_top_k("What identity documents do I need to open an account?", k=3)
    assert len(results) > 0
    assert results[0].source_document == "required_documents.md"


def test_retrieval_ranks_different_topics_to_different_documents():
    doc_question = store.retrieve_top_k("What ID documents are accepted?", k=1)
    timeline_question = store.retrieve_top_k("How long does review take?", k=1)
    account_question = store.retrieve_top_k("What is a savings account for?", k=1)

    assert doc_question[0].source_document == "required_documents.md"
    assert timeline_question[0].source_document == "processing_timelines.md"
    assert account_question[0].source_document == "account_types_faq.md"


def test_retrieve_top_k_respects_the_requested_k():
    results = store.retrieve_top_k("documents account timeline", k=2)
    assert len(results) <= 2


def test_get_chunk_by_id_resolves_a_real_chunk():
    any_chunk = store.list_chunks_for_document("required_documents.md")[0]
    resolved = store.get_chunk_by_id(any_chunk.chunk_id)
    assert resolved is not None
    assert resolved.source_document == "required_documents.md"
    assert resolved.text == any_chunk.text


def test_get_chunk_by_id_returns_none_for_an_unknown_id():
    assert store.get_chunk_by_id("does-not-exist::chunk-999") is None


def test_retrieve_top_k_returns_empty_list_when_nothing_has_been_ingested(monkeypatch, tmp_path):
    """Edge case: a fresh clone before any ingestion, or a wiped collection,
    must not error — it should just report nothing found."""
    monkeypatch.setenv("CHROMA_PERSIST_DIR", str(tmp_path / "empty_chroma_for_test"))
    get_settings.cache_clear()
    store.reset_collection_cache()
    try:
        assert store.retrieve_top_k("anything at all", k=3) == []
        assert store.count_chunks() == 0
    finally:
        get_settings.cache_clear()
        store.reset_collection_cache()
