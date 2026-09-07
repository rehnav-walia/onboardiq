import json

from app.rag import assistant


def test_ask_question_endpoint_retrieves_for_real_with_no_api_key(client):
    """No mocking — exercises the real endpoint end to end, including real
    retrieval against the real ingested sample documents. Only synthesis
    degrades, since there's no ANTHROPIC_API_KEY in this environment."""
    response = client.post("/api/policy-assistant/ask", json={"question": "What documents do I need to apply?"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "AI_UNAVAILABLE"
    assert body["retrieved_chunk_count"] > 0
    assert body["answer"]
    assert body["citations"] == []


def test_ask_question_rejects_blank_question(client):
    response = client.post("/api/policy-assistant/ask", json={"question": "   "})
    assert response.status_code == 422


def test_ask_question_requires_the_question_field(client):
    response = client.post("/api/policy-assistant/ask", json={})
    assert response.status_code == 422


def test_ask_question_with_mocked_llm_returns_citations(client, monkeypatch):
    monkeypatch.setattr(
        assistant,
        "run_text_completion",
        lambda prompt_text, max_tokens=512: json.dumps(
            {
                "relevant": True,
                "answer": "Most applications are reviewed within one business day.",
                "used_chunk_indices": [1],
            }
        ),
    )
    response = client.post("/api/policy-assistant/ask", json={"question": "How long does review take?"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ANSWERED"
    assert body["answer"] == "Most applications are reviewed within one business day."
    assert len(body["citations"]) == 1
    assert body["citations"][0]["source_document"] == "processing_timelines.md"
    assert body["citations"][0]["section_reference"]


def test_ask_out_of_scope_question_with_mocked_decline(client, monkeypatch):
    """US-30 DoD: tested with an out-of-scope question; assistant declines
    rather than hallucinating."""
    monkeypatch.setattr(
        assistant,
        "run_text_completion",
        lambda prompt_text, max_tokens=512: json.dumps(
            {"relevant": False, "answer": "This isn't something our policy documents cover.", "used_chunk_indices": []}
        ),
    )
    response = client.post("/api/policy-assistant/ask", json={"question": "What's the capital of France?"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "NOT_FOUND"
    assert body["citations"] == []
