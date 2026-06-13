import logging
from collections.abc import AsyncGenerator
from uuid import UUID

from eka.config import get_settings
from eka.core.rag.generator import OpenAIGenerator
from eka.core.rag.retriever import HybridRetriever, RetrievedChunk

logger = logging.getLogger(__name__)
settings = get_settings()


class RAGQueryPipeline:
    """
    Полный RAG-пайплайн: Retrieval → Generation.
    Используется в Chat API endpoints.
    """

    def __init__(self):
        self.retriever = HybridRetriever()
        self.generator = OpenAIGenerator()

    async def search(self, query: str, tenant_id: UUID) -> list[RetrievedChunk]:
        """Гибридный поиск. Возвращает топ чанков."""
        return await self.retriever.retrieve(query, tenant_id)

    async def chat(self, query: str, tenant_id: UUID) -> str:
        """Полный RAG: поиск → генерация ответа."""
        chunks = await self.search(query, tenant_id)
        return await self.generator.generate(query, chunks)

    async def chat_stream(self, query: str, tenant_id: UUID) -> AsyncGenerator[str, None]:
        """Потоковый RAG-ответ (для Server-Sent Events)."""
        chunks = await self.search(query, tenant_id)
        async for token in self.generator.generate_stream(query, chunks):
            yield token
