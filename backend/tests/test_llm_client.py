import json
import os

import pytest

from app.config import get_settings
from app.llm import client as llm_client
from app.llm.errors import AIUnavailableError

VALID_PAYLOAD = {
    "readable": True,
    "overall_justification": "Looks fine.",
    "full_name": {"value": "Jane Doe", "confidence": 0.9, "justification": "clear"},
    "date_of_birth": {"value": "1990-05-15", "confidence": 0.9, "justification": "clear"},
    "id_number": {"value": "A1234567", "confidence": 0.9, "justification": "clear"},
    "document_type": {"value": "PASSPORT", "confidence": 0.9, "justification": "clear"},
}


class _FakeTextBlock:
    def __init__(self, text):
        self.type = "text"
        self.text = text


class _FakeResponse:
    def __init__(self, text):
        self.content = [_FakeTextBlock(text)]


class _FakeMessages:
    def __init__(self, response=None, exception=None):
        self._response = response
        self._exception = exception

    def create(self, **kwargs):
        if self._exception is not None:
            raise self._exception
        return self._response


class _FakeAnthropic:
    def __init__(self, response=None, exception=None):
        self.messages = _FakeMessages(response=response, exception=exception)


@pytest.fixture()
def api_key_configured():
    """Sets ANTHROPIC_API_KEY for the duration of one test, then restores the
    environment and *then* clears the settings cache — in that exact order —
    so no other test can observe a stale cached Settings object."""
    original = os.environ.get("ANTHROPIC_API_KEY")
    os.environ["ANTHROPIC_API_KEY"] = "test-key"
    get_settings.cache_clear()
    try:
        yield
    finally:
        if original is None:
            os.environ.pop("ANTHROPIC_API_KEY", None)
        else:
            os.environ["ANTHROPIC_API_KEY"] = original
        get_settings.cache_clear()


def test_run_extraction_parses_valid_response(monkeypatch, api_key_configured):
    fake = _FakeAnthropic(response=_FakeResponse(json.dumps(VALID_PAYLOAD)))
    monkeypatch.setattr(llm_client, "Anthropic", lambda **kwargs: fake)

    result = llm_client.run_extraction(b"bytes", "image/jpeg", None)

    assert result.readable is True
    assert result.full_name.value == "Jane Doe"
    assert result.date_of_birth.value == "1990-05-15"


def test_run_extraction_strips_markdown_code_fences(monkeypatch, api_key_configured):
    fenced_text = "```json\n" + json.dumps(VALID_PAYLOAD) + "\n```"
    fake = _FakeAnthropic(response=_FakeResponse(fenced_text))
    monkeypatch.setattr(llm_client, "Anthropic", lambda **kwargs: fake)

    result = llm_client.run_extraction(b"bytes", "image/jpeg", None)

    assert result.readable is True


def test_run_extraction_raises_on_malformed_json(monkeypatch, api_key_configured):
    """US-09 DoD: malformed JSON must not crash the flow — it becomes a
    typed AIUnavailableError the caller is expected to handle."""
    fake = _FakeAnthropic(response=_FakeResponse("this is not json"))
    monkeypatch.setattr(llm_client, "Anthropic", lambda **kwargs: fake)

    with pytest.raises(AIUnavailableError):
        llm_client.run_extraction(b"bytes", "image/jpeg", None)


def test_run_extraction_raises_when_response_does_not_match_schema(monkeypatch, api_key_configured):
    fake = _FakeAnthropic(response=_FakeResponse(json.dumps({"readable": True})))
    monkeypatch.setattr(llm_client, "Anthropic", lambda **kwargs: fake)

    with pytest.raises(AIUnavailableError):
        llm_client.run_extraction(b"bytes", "image/jpeg", None)


def test_run_extraction_raises_when_confidence_out_of_range(monkeypatch, api_key_configured):
    bad_payload = dict(VALID_PAYLOAD, full_name={"value": "Jane Doe", "confidence": 1.5, "justification": "x"})
    fake = _FakeAnthropic(response=_FakeResponse(json.dumps(bad_payload)))
    monkeypatch.setattr(llm_client, "Anthropic", lambda **kwargs: fake)

    with pytest.raises(AIUnavailableError):
        llm_client.run_extraction(b"bytes", "image/jpeg", None)


def test_run_extraction_raises_on_api_exception(monkeypatch, api_key_configured):
    """Simulates a network failure / timeout from the SDK (US-12)."""
    fake = _FakeAnthropic(exception=TimeoutError("simulated timeout"))
    monkeypatch.setattr(llm_client, "Anthropic", lambda **kwargs: fake)

    with pytest.raises(AIUnavailableError):
        llm_client.run_extraction(b"bytes", "image/jpeg", None)


def test_run_extraction_raises_when_api_key_missing():
    """No ANTHROPIC_API_KEY configured (the default local-dev state) must
    degrade gracefully rather than attempting a doomed API call."""
    get_settings.cache_clear()
    try:
        with pytest.raises(AIUnavailableError):
            llm_client.run_extraction(b"bytes", "image/jpeg", None)
    finally:
        get_settings.cache_clear()
