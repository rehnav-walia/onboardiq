import base64
import json
import re

from anthropic import Anthropic
from pydantic import ValidationError

from app.config import get_settings
from app.llm.errors import AIUnavailableError
from app.llm.prompts import render_prompt
from app.llm.schemas import LLMExtractionResponse

_CODE_FENCE_RE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL)


def _strip_code_fence(text: str) -> str:
    match = _CODE_FENCE_RE.match(text.strip())
    return match.group(1) if match else text.strip()


def _build_document_block(file_bytes: bytes, media_type: str) -> dict:
    encoded = base64.standard_b64encode(file_bytes).decode("ascii")
    block_type = "document" if media_type == "application/pdf" else "image"
    return {"type": block_type, "source": {"type": "base64", "media_type": media_type, "data": encoded}}


def run_extraction(file_bytes: bytes, media_type: str, declared_document_type: str | None) -> LLMExtractionResponse:
    """Calls the vision LLM once and returns a validated response.

    Raises AIUnavailableError — never lets any other exception escape — for
    every failure mode: missing API key, network/timeout/auth/rate-limit
    errors, and responses that don't parse into LLMExtractionResponse
    (US-09 DoD: malformed JSON must not crash the flow; US-12: any AI
    failure routes to manual review, it never surfaces as a server error).
    """
    settings = get_settings()
    if not settings.anthropic_api_key:
        raise AIUnavailableError("ANTHROPIC_API_KEY is not configured.")

    prompt_text = render_prompt(
        "document_extraction",
        declared_document_type=declared_document_type or "not specified",
    )

    try:
        client = Anthropic(api_key=settings.anthropic_api_key, timeout=settings.llm_timeout_seconds)
        response = client.messages.create(
            model=settings.llm_model_name,
            max_tokens=1024,
            messages=[
                {
                    "role": "user",
                    "content": [
                        _build_document_block(file_bytes, media_type),
                        {"type": "text", "text": prompt_text},
                    ],
                }
            ],
        )
    except Exception as exc:
        # Deliberately broad: any failure to reach or get a response from the
        # LLM (network, timeout, auth, rate limit, SDK internals) is an
        # infrastructure problem, not a document problem — US-12.
        raise AIUnavailableError(f"LLM request failed: {exc}") from exc

    raw_text = "".join(
        block.text for block in getattr(response, "content", []) if getattr(block, "type", None) == "text"
    )

    try:
        payload = json.loads(_strip_code_fence(raw_text))
        return LLMExtractionResponse.model_validate(payload)
    except (json.JSONDecodeError, ValidationError, TypeError) as exc:
        raise AIUnavailableError(f"LLM response could not be parsed: {exc}") from exc
