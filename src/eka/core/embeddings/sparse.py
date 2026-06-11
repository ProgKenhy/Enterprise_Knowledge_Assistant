import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from fastembed import SparseTextEmbedding

logger = logging.getLogger(__name__)


@dataclass
class SparseVector:
    """
    Разреженный вектор: только ненулевые индексы и их значения.
    Qdrant принимает именно такой формат для sparse vectors.

    Пример: {"indices": [42, 1337, 9001], "values": [0.8, 0.3, 0.5]}
    В отличие от dense вектора (1024 числа), здесь только значимые токены.
    """

    indices: list[int]
    values: list[float]


_model_cache: dict[str, SparseTextEmbedding] = {}


def _load_sparse_model(model_name: str) -> SparseTextEmbedding:
    if model_name not in _model_cache:
        logger.info("Loading sparse embedding model: %s", model_name)
        _model_cache[model_name] = SparseTextEmbedding(model_name=model_name)
    return _model_cache[model_name]


def _safe_list(x: Any) -> list:
    if hasattr(x, "tolist"):
        return x.tolist()
    return list(x)


class SparseEmbedder:
    """
    Модель по умолчанию — Qdrant/bm25:
    - чистый BM25 без нейросети, работает на любом железе
    - поддерживает мультиязычные тексты через токенизацию
    - для более качественного sparse можно заменить на SPLADE:
      "prithivMLmods/Splade_PP_En_Efficient" (нужен GPU)
    """

    def __init__(self, model_name: str = "Qdrant/bm25"):
        self.model_name = model_name

    @property
    def _model(self) -> SparseTextEmbedding:
        return _load_sparse_model(self.model_name)

    async def embed(self, text: str) -> SparseVector:
        """Один текст → sparse вектор."""
        return (await self.embed_batch([text]))[0]

    async def embed_batch(self, texts: list[str]) -> list[SparseVector]:
        """Батч текстов → список sparse векторов."""
        if not texts:
            return []

        return await asyncio.to_thread(self._encode, texts)

    def _encode(self, texts: list[str]) -> list[SparseVector]:
        embeddings = list(self._model.embed(texts))

        return [
            SparseVector(
                indices=_safe_list(getattr(emb, "indices", [])),
                values=_safe_list(getattr(emb, "values", [])),
            )
            for emb in embeddings
        ]
