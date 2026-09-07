from fastapi import APIRouter

from app.rag.assistant import answer_question
from app.schemas import AskQuestionRequest, AskQuestionResponse, CitationOut

router = APIRouter(prefix="/api/policy-assistant", tags=["policy-assistant"])


@router.post("/ask", response_model=AskQuestionResponse)
def ask_question(payload: AskQuestionRequest) -> AskQuestionResponse:
    """US-30: grounded Q&A over the ingested policy documents.

    Deliberately a standalone route, not nested under any single applicant's
    record — this endpoint takes nothing but a question, so it has no
    access to any specific application's data at all. That's what makes
    "the assistant does not comment on the status or likely outcome of the
    applicant's own application" (US-30 AC) a structural guarantee rather
    than just a prompt instruction hoping the model behaves. The prompt
    also says so explicitly, as defense in depth.
    """
    result = answer_question(payload.question)
    return AskQuestionResponse(
        status=result.status.value,
        answer=result.answer,
        citations=[
            CitationOut(source_document=c.source_document, section_reference=c.section_reference)
            for c in result.citations
        ],
        retrieved_chunk_count=result.retrieved_chunk_count,
    )
