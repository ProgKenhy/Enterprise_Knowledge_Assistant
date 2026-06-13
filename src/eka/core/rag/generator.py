import asyncio
import json
import logging
import queue
import threading
from collections.abc import AsyncGenerator

import requests

from eka.config import get_settings
from eka.core.rag.retriever import RetrievedChunk

logger = logging.getLogger(__name__)
settings = get_settings()

SYSTEM_PROMPT = """Ты — точный и полезный AI-ассистент для работы с корпоративными документами.

ПРАВИЛА:
1. Отвечай ИСКЛЮЧИТЕЛЬНО на основе предоставленного контекста.
2. Если в контексте нет информации для ответа, так и скажи:
"В предоставленных документах нет информации для ответа на этот вопрос."
3. Отвечай кратко, структурированно и на том же языке, на котором задан вопрос.
4. Не выдумывай факты, которых нет в контексте."""

_SENTINEL = object()  # маркер конца стрима


class OpenAIGenerator:
    def __init__(self):
        self.model = settings.LLM_MODEL
        self.api_key = settings.OPENAI_API_KEY
        self.base_url = settings.OPENAI_BASE_URL or "https://openrouter.ai/api/v1"

        if not self.api_key or self.api_key in ("dummy", "sk-your-api-key-here", ""):
            raise ValueError("OPENAI_API_KEY не задан или содержит заглушку")

        logger.info(
            "LLM Generator initialized: model=%s, base_url=%s",
            self.model,
            self.base_url,
        )

    def _get_headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost:8000",
            "X-Title": "Enterprise Knowledge Assistant",
        }

    def _format_context(self, chunks: list[RetrievedChunk]) -> str:
        if not chunks:
            return "Контекст не найден."
        return "\n\n".join(f"[Фрагмент {i}]\n{chunk.text}" for i, chunk in enumerate(chunks, 1))

    def _build_payload(
        self, query: str, chunks: list[RetrievedChunk], stream: bool = False
    ) -> dict:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": f"Контекст:\n{self._format_context(chunks)}\n\nВопрос: {query}",
                },
            ],
            "temperature": 0.3,
            "max_tokens": 1024,
            "stream": stream,
        }
        # Включаем reasoning для моделей, которые его поддерживают
        if "nex-n2-pro" in self.model or "reasoning" in self.model.lower():
            payload["reasoning"] = {"enabled": True}
        return payload

    # ──────────────────────────────────────────────
    # Обычная генерация
    # ──────────────────────────────────────────────

    def _sync_generate(self, query: str, chunks: list[RetrievedChunk]) -> str:
        response = requests.post(
            url=f"{self.base_url}/chat/completions",
            headers=self._get_headers(),
            data=json.dumps(self._build_payload(query, chunks, stream=False)),
            timeout=60,
        )
        if response.status_code != 200:
            logger.error("LLM error %s: %s", response.status_code, response.text[:300])
            raise RuntimeError(f"LLM error {response.status_code}: {response.text[:200]}")

        return response.json()["choices"][0]["message"]["content"] or ""

    async def generate(self, query: str, chunks: list[RetrievedChunk]) -> str:
        if not chunks:
            return "В предоставленных документах нет информации для ответа на ваш вопрос."
        try:
            return await asyncio.to_thread(self._sync_generate, query, chunks)
        except Exception as e:
            logger.error("Ошибка генерации: %s", e)
            return f"Ошибка LLM: {e}"

    # ──────────────────────────────────────────────
    # Стриминг через очередь
    # ──────────────────────────────────────────────

    def _stream_into_queue(
        self, query: str, chunks: list[RetrievedChunk], token_queue: queue.Queue
    ) -> None:
        """
        Запускается в отдельном потоке.
        Читает SSE-ответ и кладёт каждый токен в очередь по мере поступления.
        В конце кладёт _SENTINEL — сигнал что стрим завершён.
        """
        try:
            response = requests.post(
                url=f"{self.base_url}/chat/completions",
                headers=self._get_headers(),
                data=json.dumps(self._build_payload(query, chunks, stream=True)),
                stream=True,
                timeout=60,
            )
            if response.status_code != 200:
                raise RuntimeError(
                    f"LLM stream error {response.status_code}: {response.text[:200]}"
                )

            for line in response.iter_lines():
                if not line:
                    continue
                line_str = line.decode("utf-8")
                if not line_str.startswith("data: "):
                    continue
                data = line_str[6:]
                if data.strip() == "[DONE]":
                    break
                try:
                    chunk_data = json.loads(data)
                    content = chunk_data["choices"][0].get("delta", {}).get("content")
                    if content:
                        token_queue.put(content)  # токен сразу попадает в очередь
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue
        except Exception as e:
            token_queue.put(e)  # ошибку тоже передаём через очередь
        finally:
            token_queue.put(_SENTINEL)  # всегда сигнализируем конец

    async def generate_stream(
        self, query: str, chunks: list[RetrievedChunk]
    ) -> AsyncGenerator[str, None]:
        if not chunks:
            yield "В предоставленных документах нет информации."
            return

        token_queue: queue.Queue = queue.Queue()

        # Запускаем блокирующий стрим в отдельном потоке
        thread = threading.Thread(
            target=self._stream_into_queue,
            args=(query, chunks, token_queue),
            daemon=True,
        )
        thread.start()

        # Читаем токены из очереди по мере поступления
        while True:
            # asyncio.to_thread чтобы не блокировать event loop на queue.get()
            token = await asyncio.to_thread(token_queue.get)

            if token is _SENTINEL:
                break
            if isinstance(token, Exception):
                logger.error("Ошибка стриминга: %s", token)
                yield f"\n\n❌ Ошибка: {token}"
                break

            yield token

    async def close(self) -> None:
        """requests не требует явного закрытия, метод нужен для lifespan."""
        pass
