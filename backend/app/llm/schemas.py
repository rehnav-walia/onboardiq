from pydantic import BaseModel, field_validator


class LLMFieldResult(BaseModel):
    value: str | None
    confidence: float
    justification: str

    @field_validator("confidence")
    @classmethod
    def _confidence_in_range(cls, v: float) -> float:
        if not (0.0 <= v <= 1.0):
            raise ValueError("confidence must be between 0.0 and 1.0")
        return v


class LLMExtractionResponse(BaseModel):
    """Mirrors prompts/document_extraction.txt exactly. Defensive parsing
    (US-09 DoD) happens by validating the LLM's raw JSON against this model —
    anything that doesn't fit this shape is treated as AI_UNAVAILABLE rather
    than trusted."""

    readable: bool
    overall_justification: str
    full_name: LLMFieldResult
    date_of_birth: LLMFieldResult
    id_number: LLMFieldResult
    document_type: LLMFieldResult
