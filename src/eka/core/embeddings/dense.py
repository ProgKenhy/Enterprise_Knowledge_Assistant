import asyncio
import hashlib
import json
import logging
from typing import Any

from fastembed import TextEmbedding

logger = logging.getLogger(__name__)

# -------------------------
# MODEL SINGLETON
# -------------------------
_MODELS: dict[str, TextEmbedding] = {}


def get_model(model_name: str) -> TextEmbedding:
    """
    Singleton модели fastembed (ONNX runtime).
    """
    if model_name not in _MODELS:
        logger.info("Loading fastembed model: %s", model_name)
        _MODELS[model_name] = TextEmbedding(model_name=model_name)
    return _MODELS[model_name]


# -------------------------
# EMBEDDER
# -------------------------
class DenseEmbedder:
    """
    Dense embeddings через fastembed (CPU-only, ONNX).
    """

    def __init__(
        self,
        model_name: str = "intfloat/multilingual-e5-small",
        redis_client=None,
    ):
        self.model_name = model_name
        self._redis = redis_client

    @property
    def _model(self) -> TextEmbedding:
        return get_model(self.model_name)

    async def embed(self, text: str) -> list[float]:
        return (await self.embed_batch([text]))[0]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        # -------------------------
        # dedup (preserve order)
        # -------------------------
        seen: dict[str, int] = {}
        unique_texts: list[str] = []

        for t in texts:
            if t not in seen:
                seen[t] = len(unique_texts)
                unique_texts.append(t)

        # -------------------------
        # no redis fallback
        # -------------------------
        if self._redis is None:
            vectors = await asyncio.to_thread(self._encode, unique_texts)
            return [vectors[seen[t]] for t in texts]

        results = await self._embed_with_cache(unique_texts)

        return [results[seen[t]] for t in texts]

    async def _embed_with_cache(self, texts: list[str]) -> list[list[float]]:
        keys = [self._cache_key(t) for t in texts]

        redis = self._redis
        assert redis is not None

        cached_values = await redis.mget(keys)

        def decode(v: Any):
            if v is None:
                return None
            if isinstance(v, bytes):
                v = v.decode()

            try:
                return json.loads(v)
            except Exception:
                return None

        results: list[Any] = [decode(v) for v in cached_values]

        miss_items = [(i, texts[i], keys[i]) for i, v in enumerate(results) if v is None]

        if miss_items:
            miss_texts = [t for _, t, _ in miss_items]
            miss_keys = [k for _, _, k in miss_items]

            new_vectors = await asyncio.to_thread(self._encode, miss_texts)

            redis = self._redis
            assert redis is not None

            pipe = redis.pipeline(transaction=False)

            for key, vec in zip(miss_keys, new_vectors, strict=False):
                pipe.set(key, json.dumps(vec), ex=86400)

            await pipe.execute()

            for (i, _, _), vec in zip(miss_items, new_vectors, strict=False):
                results[i] = vec

        return results

    def _encode(self, texts: list[str]) -> list[list[float]]:
        """
        fastembed inference (CPU, ONNX).
        """
        vectors = list(self._model.embed(texts))
        return [list(v) for v in vectors]

    @staticmethod
    def _cache_key(text: str) -> str:
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
        return f"emb:dense:{digest}"
