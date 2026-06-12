import logging

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from eka.core.rag.pipeline import RAGQueryPipeline
from eka.db.models import User
from eka.deps import get_user_by_token

logger = logging.getLogger(__name__)

chat_router = APIRouter()

rag_pipeline = RAGQueryPipeline()


@chat_router.post("")
async def chat(
    query: str,
    current_user: User = Depends(get_user_by_token),
):
    """
    Обычный RAG-чат. Возвращает полный ответ после генерации.
    """
    logger.info(f"Chat request from user {current_user.id}, tenant {current_user.tenant_id}")

    answer = await rag_pipeline.chat(query=query, tenant_id=current_user.tenant_id)

    return {"query": query, "answer": answer}


@chat_router.post("/stream")
async def chat_stream(
    query: str,
    current_user: User = Depends(get_user_by_token),
):
    """
    Потоковый RAG-чат (Server-Sent Events).
    Идеально для фронтенда: токены прилетают по мере генерации.
    """

    async def event_generator():
        try:
            async for token in rag_pipeline.chat_stream(
                query=query, tenant_id=current_user.tenant_id
            ):
                # Формат SSE: каждый кусок текста должен начинаться с "data: "
                yield f"data: {token}\n\n"

            # Сигнал окончания потока
            yield "data: [DONE]\n\n"
        except Exception as e:
            logger.error(f"Streaming error: {e}")
            yield f"data: [ERROR] {str(e)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )
