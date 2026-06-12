import uuid

import pytest

from eka.core.rag.generator import MockLLMGenerator
from eka.core.rag.retriever import RetrievedChunk


@pytest.fixture
def generator():
    return MockLLMGenerator()


@pytest.fixture
def mock_chunks():
    tenant_id = uuid.uuid4()
    return [
        RetrievedChunk(
            chunk_id="1",
            document_id=uuid.uuid4(),
            tenant_id=tenant_id,
            text="Секретный документ отдела А",
            score=0.9,
            metadata={},
        )
    ]


@pytest.mark.asyncio
async def test_mock_generator_handles_empty_context(generator):
    answer = await generator.generate("Вопрос", [])
    assert "нет информации" in answer.lower()


@pytest.mark.asyncio
async def test_mock_generator_uses_context(generator, mock_chunks):
    answer = await generator.generate("Вопрос", mock_chunks)
    assert "Mock LLM" in answer
    assert "Секретный документ отдела А" in answer


@pytest.mark.asyncio
async def test_mock_generator_streaming_format(generator, mock_chunks):
    tokens = [token async for token in generator.generate_stream("Вопрос", mock_chunks)]
    full_text = "".join(tokens)
    assert len(tokens) > 1
    assert "Mock LLM Stream" in full_text


# ==============================================================================
# ЗАГОТОВКА ДЛЯ ТЕСТОВ РЕАЛЬНОЙ LLM (OpenAI / Ollama / vLLM)
# Раскомментировать и дополнить, когда будет подключен настоящий LLMGenerator
# ==============================================================================
"""
@pytest.fixture
def real_llm_generator():
    from eka.core.rag.generator import LLMGenerator
    return LLMGenerator()

@pytest.mark.asyncio
async def test_real_llm_system_prompt_restricts_hallucinations(real_llm_generator, mock_httpx):
    # 1. Перехватываем запрос к API провайдера (через respx или pytest-httpx)
    # 2. В messages[0] (system) жестко зашито ограничение отвечать ТОЛЬКО по контексту
    # 3. Убеждаемся, что промпт требует отвечать на языке запроса
    pass

@pytest.mark.asyncio
async def test_real_llm_refusal_on_no_context(real_llm_generator, mock_httpx):
    # Проверяем, что если chunks=[], модель отвечает "В документах нет информации",
    # а не начинает галлюцинировать, опираясь на свои внутренние веса.
    pass
"""
