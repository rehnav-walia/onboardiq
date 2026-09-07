"""Grounded chat assistant tests (US-30).

Retrieval is always real (the same ingested sample documents used in
test_rag_store.py). Only the final answer-synthesis call to Claude is ever
mocked — via app.rag.assistant.run_text_completion — since that's the one
part that genuinely needs a paid API key, which isn't available in this
environment (see docs/PROGRESS.md).
"""

import json
from pathlib import Path

from app.llm.errors import AIUnavailableError
from app.rag import assistant, store


def _mock_llm(monkeypatch, payload: dict | str):
    text = payload if isinstance(payload, str) else json.dumps(payload)
    monkeypatch.setattr(assistant, "run_text_completion", lambda prompt_text, max_tokens=512: text)


def test_no_api_key_still_retrieves_but_degrades_gracefully():
    """No mocking at all here — exercises the real graceful-degradation
    path with no ANTHROPIC_API_KEY configured (the default test/dev state,
    same as Phase 2). Retrieval must still have genuinely run."""
    result = assistant.answer_question("What identity documents do I need?")
    assert result.status == assistant.AssistantStatus.AI_UNAVAILABLE
    assert result.retrieved_chunk_count > 0
    assert result.citations == []
    assert result.answer  # never blank


def test_mocked_answer_with_valid_citation(monkeypatch):
    _mock_llm(
        monkeypatch,
        {
            "relevant": True,
            "answer": "You need a valid passport, national ID card, or driving licence.",
            "used_chunk_indices": [1],
        },
    )
    result = assistant.answer_question("What documents do I need to open an account?")
    assert result.status == assistant.AssistantStatus.ANSWERED
    assert result.answer == "You need a valid passport, national ID card, or driving licence."
    assert len(result.citations) == 1
    assert result.citations[0].source_document == "required_documents.md"


def test_every_citation_independently_maps_to_a_real_retrievable_chunk(monkeypatch):
    """US-30 DoD, verified literally: look the citation up in the full
    stored set (not just the query that produced it) and confirm it's
    really there."""
    _mock_llm(
        monkeypatch,
        {"relevant": True, "answer": "Answer using excerpt 1.", "used_chunk_indices": [1]},
    )
    result = assistant.answer_question("What documents do I need?")
    assert result.citations
    for citation in result.citations:
        stored = store.list_chunks_for_document(citation.source_document)
        assert any(c.section_reference == citation.section_reference for c in stored)


def test_out_of_range_citation_index_is_dropped_not_trusted(monkeypatch):
    _mock_llm(
        monkeypatch,
        {"relevant": True, "answer": "An answer.", "used_chunk_indices": [1, 999, -3]},
    )
    result = assistant.answer_question("What documents do I need?")
    assert result.status == assistant.AssistantStatus.ANSWERED
    # Only the in-range index (1) should have produced a citation.
    assert len(result.citations) == 1


def test_model_declines_when_context_is_not_relevant(monkeypatch):
    """US-30 AC/DoD: tested with an out-of-scope question — the assistant
    declines rather than hallucinating. Retrieval still runs (there's
    always *some* nearest chunk), but the model is simulated correctly
    recognizing none of it actually answers the question."""
    _mock_llm(
        monkeypatch,
        {
            "relevant": False,
            "answer": "Our policy documents don't cover the weather forecast.",
            "used_chunk_indices": [],
        },
    )
    result = assistant.answer_question("What's the weather like today?")
    assert result.status == assistant.AssistantStatus.NOT_FOUND
    assert result.citations == []
    assert "weather" in result.answer.lower()


def test_malformed_json_response_degrades_gracefully_without_crashing(monkeypatch):
    _mock_llm(monkeypatch, "this is not valid JSON at all")
    result = assistant.answer_question("What documents do I need?")
    assert result.status == assistant.AssistantStatus.AI_UNAVAILABLE
    assert result.answer


def test_llm_infrastructure_failure_degrades_gracefully(monkeypatch):
    def boom(prompt_text, max_tokens=512):
        raise AIUnavailableError("simulated network failure")

    monkeypatch.setattr(assistant, "run_text_completion", boom)
    result = assistant.answer_question("What documents do I need?")
    assert result.status == assistant.AssistantStatus.AI_UNAVAILABLE
    assert result.answer


def test_no_relevant_chunks_at_all_is_not_found_without_calling_the_llm(monkeypatch):
    # assistant.py did `from app.rag.store import retrieve_top_k`, binding the
    # name into its own module namespace — patch it there, not on `store`,
    # or this monkeypatch silently has no effect.
    monkeypatch.setattr(assistant, "retrieve_top_k", lambda question, k: [])
    calls = {"n": 0}

    def _should_not_be_called(prompt_text, max_tokens=512):
        calls["n"] += 1
        return "{}"

    monkeypatch.setattr(assistant, "run_text_completion", _should_not_be_called)
    result = assistant.answer_question("Anything")
    assert result.status == assistant.AssistantStatus.NOT_FOUND
    assert result.retrieved_chunk_count == 0
    assert calls["n"] == 0  # no point spending an LLM call with nothing to ground it in


def test_assistant_module_has_no_code_level_access_to_application_data():
    """US-30 AC: 'does not comment on the status or likely outcome of the
    applicant's own application' — proven structurally, the same way
    US-24's no-auto-approval is: the RAG module and its API route are
    scanned for any reference to application data at all. There is no
    reference_id parameter, no Application import, and no crud call
    anywhere in this code path — so there's no channel for that data to
    reach the model in the first place, regardless of how the prompt is
    worded (the prompt also says so explicitly, as defense in depth — but
    this test is the structural guarantee, not the wording).
    """
    rag_dir = Path(__file__).resolve().parent.parent / "app" / "rag"
    router_file = Path(__file__).resolve().parent.parent / "app" / "routers" / "policy_assistant.py"

    forbidden_terms = ["Application", "reference_id", "get_application_by_reference"]
    for path in list(rag_dir.glob("*.py")) + [router_file]:
        text = path.read_text(encoding="utf-8")
        for term in forbidden_terms:
            assert term not in text, f"{path.name} references {term!r} — the assistant must have no application data"
