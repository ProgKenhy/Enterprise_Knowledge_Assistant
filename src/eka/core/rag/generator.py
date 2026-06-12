import asyncio
import logging
from collections.abc import AsyncGenerator

from eka.config import get_settings
from eka.core.rag.retriever import RetrievedChunk

logger = logging.getLogger(__name__)
settings = get_settings()


class MockLLMGenerator:
    """
    Заглушка (Mock) для генерации ответов.
    Используется на этапе разработки, когда нет API-ключа или локальной модели.
    Имитирует задержку сети и потоковую передачу (streaming) токенов.
    """

    def __init__(self):
        # Здесь можно добавить настройки, если нужно, но пока они не требуются
        pass

    def _format_context(self, chunks: list[RetrievedChunk]) -> str:
        if not chunks:
            return "Контекст не найден."
        parts = [f"[Фрагмент {i}]\n{chunk.text}" for i, chunk in enumerate(chunks, 1)]
        return "\n\n".join(parts)

    async def generate(self, query: str, chunks: list[RetrievedChunk]) -> str:
        """Обычная (не потоковая) генерация ответа."""
        if not chunks:
            return (
                "К сожалению, в предоставленных документах нет информации для ответа на ваш вопрос."
            )

        # Имитация осмысленного ответа на основе первого (самого релевантного) чанка
        top_chunk_preview = chunks[0].text[:300].strip() + "..."

        return (
            f"🤖 **[TEST MODE: Mock LLM]**\n\n"
            f"Я проанализировал {len(chunks)} фрагментов из вашей базы знаний.\n\n"
            f"Наиболее релевантная информация:\n> {top_chunk_preview}"
        )

    async def generate_stream(
        self, query: str, chunks: list[RetrievedChunk]
    ) -> AsyncGenerator[str, None]:
        """
        Имитация потоковой генерации (Server-Sent Events).
        Разбивает ответ на мелкие части и отдает их с небольшой задержкой,
        чтобы фронтенд мог красиво отображать "печатающийся" текст.
        """
        if not chunks:
            yield "К сожалению, в предоставленных документах нет информации."
            return

        # Формируем тестовый ответ
        mock_response = (
            f"🤖 **[TEST MODE: Mock LLM Stream]**\n\n"
            f"Я нашел {len(chunks)} релевантных фрагментов. "
            f"Вот начало самого подходящего из них: {chunks[0].text[:200].strip()}..."
        )

        # Разбиваем строку на "токены" по 4-6 символов для имитации стриминга
        chunk_size = 5
        tokens = [
            mock_response[i : i + chunk_size] for i in range(0, len(mock_response), chunk_size)
        ]

        for token in tokens:
            yield token
            # Имитируем задержку сети (около 30-40 "токенов" в секунду)
            await asyncio.sleep(0.03)
