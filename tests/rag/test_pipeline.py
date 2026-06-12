import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from eka.core.rag.pipeline import RAGQueryPipeline


@pytest.fixture
def pipeline():
    with (
        patch("eka.core.rag.pipeline.HybridRetriever"),
        patch("eka.core.rag.pipeline.MockLLMGenerator"),
    ):
        p = RAGQueryPipeline()
        p.retriever = AsyncMock()
        p.generator = MagicMock()
        return p


@pytest.mark.asyncio
async def test_pipeline_chat_flow(pipeline):
    tenant_id = uuid.uuid4()
    query = "Как оформить отпуск?"

    mock_chunks = [MagicMock()]
    pipeline.retriever.retrieve.return_value = mock_chunks

    pipeline.generator.generate = AsyncMock(return_value="Ответ ИИ")

    result = await pipeline.chat(query, tenant_id)

    # Проверяем, что поиск вызвался с правильным тенантом
    pipeline.retriever.retrieve.assert_called_once_with(query, tenant_id)
    # Проверяем, что генератор получил именно те чанки, которые нашел retriever
    pipeline.generator.generate.assert_called_once_with(query, mock_chunks)
    assert result == "Ответ ИИ"


@pytest.mark.asyncio
async def test_pipeline_stream_flow(pipeline):
    tenant_id = uuid.uuid4()
    query = "Stream test"

    mock_chunks = [MagicMock()]
    pipeline.retriever.retrieve.return_value = mock_chunks

    async def mock_stream(*args, **kwargs):
        yield "Token"

    pipeline.generator.generate_stream = mock_stream

    tokens = [t async for t in pipeline.chat_stream(query, tenant_id)]

    pipeline.retriever.retrieve.assert_called_once_with(query, tenant_id)
    assert tokens == ["Token"]
