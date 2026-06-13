import json
import uuid
from unittest.mock import MagicMock, patch

import pytest

from eka.core.rag.generator import OpenAIGenerator
from eka.core.rag.retriever import RetrievedChunk


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


@pytest.fixture
def generator():
    """Создаёт генератор с тестовыми настройками."""
    with patch("eka.core.rag.generator.settings") as mock_settings:
        mock_settings.LLM_MODEL = "test-model"
        mock_settings.OPENAI_API_KEY = "sk-test-key"
        mock_settings.OPENAI_BASE_URL = "https://test.api/v1"
        yield OpenAIGenerator()


# ==============================================================================
# Тесты обычной генерации
# ==============================================================================


@pytest.mark.asyncio
async def test_generate_handles_empty_context(generator):
    """Если chunks пустой, генератор должен вернуть сообщение об отсутствии информации."""
    answer = await generator.generate("Вопрос", [])
    assert "нет информации" in answer.lower()


@pytest.mark.asyncio
async def test_generate_calls_api_with_correct_payload(generator, mock_chunks):
    """Проверяем, что запрос к API формируется правильно."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [{"message": {"content": "Ответ на основе контекста"}}]
    }

    with patch("eka.core.rag.generator.requests.post", return_value=mock_response) as mock_post:
        answer = await generator.generate("Какой документ?", mock_chunks)

        assert answer == "Ответ на основе контекста"

        # Проверяем, что запрос был сделан
        assert mock_post.called
        call_args = mock_post.call_args

        # Проверяем URL
        assert call_args.kwargs["url"] == "https://test.api/v1/chat/completions"

        # Проверяем заголовки
        headers = call_args.kwargs["headers"]
        assert headers["Authorization"] == "Bearer sk-test-key"
        assert headers["Content-Type"] == "application/json"

        # Проверяем payload
        payload = json.loads(call_args.kwargs["data"])
        assert payload["model"] == "test-model"
        assert payload["temperature"] == 0.3
        assert payload["max_tokens"] == 1024
        assert payload["stream"] is False

        # Проверяем messages
        messages = payload["messages"]
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"

        # Проверяем, что контекст включён в user message
        user_content = messages[1]["content"]
        assert "Секретный документ отдела А" in user_content
        assert "Какой документ?" in user_content


@pytest.mark.asyncio
async def test_generate_system_prompt_restricts_hallucinations(generator, mock_chunks):
    """System prompt должен требовать отвечать ТОЛЬКО по контексту."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"choices": [{"message": {"content": "Ответ"}}]}

    with patch("eka.core.rag.generator.requests.post", return_value=mock_response) as mock_post:
        await generator.generate("Вопрос", mock_chunks)

        # Получаем payload из вызова
        call_args = mock_post.call_args
        payload = json.loads(call_args.kwargs["data"])
        system_message = payload["messages"][0]["content"]

        # Проверяем, что system prompt содержит ограничения
        assert "ИСКЛЮЧИТЕЛЬНО" in system_message or "только" in system_message.lower()
        assert "контекст" in system_message.lower()


@pytest.mark.asyncio
async def test_generate_handles_api_error(generator, mock_chunks):
    """Если API возвращает ошибку, генератор должен обработать её."""
    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.text = "Internal Server Error"

    with patch("eka.core.rag.generator.requests.post", return_value=mock_response):
        answer = await generator.generate("Вопрос", mock_chunks)
        assert "Ошибка" in answer or "error" in answer.lower()


# ==============================================================================
# Тесты стриминга
# ==============================================================================


@pytest.mark.asyncio
async def test_generate_stream_handles_empty_context(generator):
    """Если chunks пустой, стрим должен вернуть сообщение об отсутствии информации."""
    tokens = [token async for token in generator.generate_stream("Вопрос", [])]
    full_text = "".join(tokens)
    assert "нет информации" in full_text.lower()


@pytest.mark.asyncio
async def test_generate_stream_yields_tokens(generator, mock_chunks):
    """Стрим должен возвращать токены по мере поступления."""
    # Мокаем response с SSE-данными
    # Используем .encode('utf-8') для преобразования unicode-строк в bytes
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.iter_lines.return_value = [
        'data: {"choices": [{"delta": {"content": "Привет"}}]}'.encode(),
        b'data: {"choices": [{"delta": {"content": "!"}}]}',
        b"data: [DONE]",
    ]

    with patch("eka.core.rag.generator.requests.post", return_value=mock_response):
        tokens = [token async for token in generator.generate_stream("Вопрос", mock_chunks)]

        assert len(tokens) == 2
        assert tokens[0] == "Привет"
        assert tokens[1] == "!"


@pytest.mark.asyncio
async def test_generate_stream_handles_api_error(generator, mock_chunks):
    """Если API возвращает ошибку при стриминге, генератор должен обработать её."""
    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.text = "Internal Server Error"

    with patch("eka.core.rag.generator.requests.post", return_value=mock_response):
        tokens = [token async for token in generator.generate_stream("Вопрос", mock_chunks)]
        full_text = "".join(tokens)
        assert "Ошибка" in full_text or "error" in full_text.lower()


# ==============================================================================
# Тесты инициализации
# ==============================================================================


def test_generator_raises_on_missing_api_key():
    """Генератор должен поднять ошибку, если API-ключ не задан."""
    with patch("eka.core.rag.generator.settings") as mock_settings:
        mock_settings.LLM_MODEL = "test-model"
        mock_settings.OPENAI_API_KEY = ""
        mock_settings.OPENAI_BASE_URL = "https://test.api/v1"

        with pytest.raises(ValueError, match="OPENAI_API_KEY не задан"):
            OpenAIGenerator()


def test_generator_raises_on_dummy_api_key():
    """Генератор должен поднять ошибку, если API-ключ содержит заглушку."""
    with patch("eka.core.rag.generator.settings") as mock_settings:
        mock_settings.LLM_MODEL = "test-model"
        mock_settings.OPENAI_API_KEY = "dummy"
        mock_settings.OPENAI_BASE_URL = "https://test.api/v1"

        with pytest.raises(ValueError, match="OPENAI_API_KEY не задан"):
            OpenAIGenerator()
