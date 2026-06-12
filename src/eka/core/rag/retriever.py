import asyncio
import logging
from dataclasses import dataclass, field
from uuid import UUID

from fastembed import SparseTextEmbedding, TextEmbedding
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Condition,
    FieldCondition,
    Filter,
    MatchAny,
    MatchValue,
    ScoredPoint,
    SearchParams,
    SparseVector,
)

from eka.config import get_settings
from eka.core.indexing.vector_store import get_qdrant

logger = logging.getLogger(__name__)
settings = get_settings()


@dataclass
class RetrievedChunk:
    """Результат поиска с метаданными."""

    chunk_id: str
    document_id: UUID
    tenant_id: UUID
    text: str
    score: float
    metadata: dict = field(default_factory=dict)


class HybridRetriever:
    """
    Гибридный retriever с RRF (Reciprocal Rank Fusion).
    Комбинирует семантический (dense) и ключевой (sparse/BM25) поиск.
    """

    def __init__(
        self,
        dense_model_name: str | None = None,
        sparse_model_name: str = "Qdrant/bm25",
        top_k: int | None = None,
    ):
        self.dense_model_name = dense_model_name or settings.EMBEDDING_DENSE_MODEL
        self.sparse_model_name = sparse_model_name or settings.EMBEDDING_SPARSE_MODEL
        self.top_k = top_k or settings.RETRIEVAL_TOP_K

        self._dense_model: TextEmbedding | None = None
        self._sparse_model: SparseTextEmbedding | None = None

    @property
    def dense_model(self) -> TextEmbedding:
        if self._dense_model is None:
            logger.info(f"Loading dense model: {self.dense_model_name}")
            self._dense_model = TextEmbedding(model_name=self.dense_model_name)
        return self._dense_model

    @property
    def sparse_model(self) -> SparseTextEmbedding:
        if self._sparse_model is None:
            logger.info(f"Loading sparse model: {self.sparse_model_name}")
            self._sparse_model = SparseTextEmbedding(model_name=self.sparse_model_name)
        return self._sparse_model

    async def retrieve(
        self,
        query: str,
        tenant_id: UUID,
        document_ids: list[UUID] | None = None,
    ) -> list[RetrievedChunk]:
        qdrant = get_qdrant()

        # 1. Создаем эмбеддинги запроса
        dense_query_vector = list(self.dense_model.query_embed(query))[0].tolist()

        sparse_raw = list(self.sparse_model.query_embed(query))[0]
        sparse_query_vector = SparseVector(
            indices=sparse_raw.indices.tolist(),
            values=sparse_raw.values.tolist(),
        )

        # 2. Формируем фильтр (ОБЯЗАТЕЛЬНО tenant_id для безопасности)
        must_conditions: list[Condition] = [
            FieldCondition(key="tenant_id", match=MatchValue(value=str(tenant_id)))
        ]
        if document_ids:
            must_conditions.append(
                FieldCondition(
                    key="document_id",
                    match=MatchAny(any=[str(d) for d in document_ids]),
                )
            )
        search_filter = Filter(must=must_conditions)

        # 3. Параллельный поиск
        dense_results, sparse_results = await self._parallel_search(
            qdrant, dense_query_vector, sparse_query_vector, search_filter
        )

        # 4. RRF Fusion
        fused_results = self._rrf_fusion(dense_results, sparse_results)

        # 5. Конвертация в формат приложения
        chunks = []
        for point in fused_results[: self.top_k]:
            payload = point.payload or {}
            chunks.append(
                RetrievedChunk(
                    chunk_id=str(point.id),
                    document_id=UUID(payload["document_id"]),
                    tenant_id=UUID(payload["tenant_id"]),
                    text=payload.get("text", ""),
                    score=point.score,
                    metadata=payload,
                )
            )
        return chunks

    async def _parallel_search(
        self,
        qdrant: AsyncQdrantClient,
        dense_vector: list[float],
        sparse_vector: SparseVector,
        search_filter: Filter,
    ) -> tuple[list[ScoredPoint], list[ScoredPoint]]:
        async def run_dense() -> list[ScoredPoint]:
            try:
                r = await qdrant.query_points(
                    collection_name=settings.QDRANT_COLLECTION,
                    query=dense_vector,
                    using="dense",
                    query_filter=search_filter,
                    limit=self.top_k * 2,
                    search_params=SearchParams(hnsw_ef=128, exact=False),
                    with_payload=True,
                )
                return r.points
            except Exception as e:
                logger.error(f"Dense search failed: {e}")
                return []

        async def run_sparse() -> list[ScoredPoint]:
            try:
                r = await qdrant.query_points(
                    collection_name=settings.QDRANT_COLLECTION,
                    query=sparse_vector,
                    using="sparse",
                    query_filter=search_filter,
                    limit=self.top_k * 2,
                    with_payload=True,
                )
                return r.points
            except Exception as e:
                logger.error(f"Sparse search failed: {e}")
                return []

        return await asyncio.gather(run_dense(), run_sparse())

    def _rrf_fusion(
        self,
        dense_results: list[ScoredPoint],
        sparse_results: list[ScoredPoint],
        k: int = 60,  # Стандартная константа для RRF
    ) -> list[ScoredPoint]:
        scores: dict = {}

        for rank, point in enumerate(dense_results):
            chunk_id = str(point.id)
            if chunk_id not in scores:
                scores[chunk_id] = {"point": point, "score": 0.0}
            scores[chunk_id]["score"] += 1.0 / (k + rank + 1)

        for rank, point in enumerate(sparse_results):
            chunk_id = str(point.id)
            if chunk_id not in scores:
                scores[chunk_id] = {"point": point, "score": 0.0}
            scores[chunk_id]["score"] += 1.0 / (k + rank + 1)

        sorted_items = sorted(scores.values(), key=lambda x: x["score"], reverse=True)

        result = []
        for item in sorted_items:
            point = item["point"]
            point.score = item["score"]
            result.append(point)

        return result
