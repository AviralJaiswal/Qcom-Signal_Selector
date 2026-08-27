import logging
from time import perf_counter
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.assistant.service import handle_message
from app.database import get_db
from app.schemas.api import RAGQueryRequest, RAGQueryData
from app.schemas.envelope import ResponseEnvelope, success_response
from app.utils.trace import trace, trace_async

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["AI Assistant API"])
legacy_router = APIRouter(tags=["Legacy AI Assistant API"])


@router.post("/ai/rag/query", response_model=ResponseEnvelope[RAGQueryData])
@trace
def query_rag_assistant(request: RAGQueryRequest, db: Session = Depends(get_db)):
    """AI Assistant API - Modular orchestration powered by Gemini & ChromaDB RAG."""
    started = perf_counter()
    structured = request.structured_fields.model_dump(exclude_none=True) if request.structured_fields else None

    result = handle_message(
        session_id=request.session_id,
        message=request.message,
        db=db,
        structured_fields=structured,
    )

    response_data = {
        "answer": result.get("response", ""),
        "mode": result.get("mode", "RAG"),
        "evidence": result.get("sources", []),
        "sources": result.get("sources", []),
        "intent": result.get("intent", ""),
        "workflow_state": result.get("workflowState", ""),
        "recommended_plan": result.get("recommendedPlan") or result.get("recommended_plan"),
        "updated_state": result.get("updatedState", {}),
    }

    duration_ms = round((perf_counter() - started) * 1000)
    logger.info("RAG query processed in %dms mode=%s", duration_ms, result.get("mode"))
    return success_response(response_data, message="Assistant response generated successfully")


@legacy_router.post("/chat")
def chat_legacy(request: RAGQueryRequest, db: Session = Depends(get_db)):
    return query_rag_assistant(request, db)

