import asyncio
import logging
from typing import Any, cast
from uuid import UUID

from qdrant_client.models import (
    FieldCondition,
    Filter,
    FilterSelector,
    MatchValue,
    PointStruct,
    SparseVector,
)

from eka.config import get_settings
from eka.core.embeddings import DenseEmbedder, SparseEmbedder
from eka.core.indexing.loaders import get_loader
from eka.core.indexing.splitters.hierarchical import HierarchicalSplitter
from eka.core.indexing.vector_store import get_qdrant

logger = logging.getLogger(__name__)
settings = get_settings()

BATCH_SIZE = 64


class IndexingPipeline:
    """
    Оркестратор индексирования: связывает все компоненты.

    Loader → Splitter → Embedder (dense + sparse) → Qdrant
    """

    def __init__(self, collection: str, redis_client=None):
        self.collection = collection
        self.dense = DenseEmbedder(
            redis_client=redis_client, model_name=settings.EMBEDDING_DENSE_MODEL
        )
        self.sparse = SparseEmbedder(model_name=settings.EMBEDDING_SPARSE_MODEL)
        self.splitter = HierarchicalSplitter(
            parent_chunk_size=1500,
            child_chunk_size=400,
            child_overlap=50,
        )

    async def run(
        self,
        document_id: UUID,
        tenant_id: UUID,
        file_path: str,
        source_type: str,
        extra_metadata: dict | None = None,
    ) -> int:
        """
        Полный цикл индексирования одного документа.
        Возвращает количество записанных чанков.
        """
        extra_metadata = extra_metadata or {}

        logger.info("Loading document %s (%s)", document_id, source_type)

        loader = get_loader(source_type)
        raw_doc = await loader.load(file_path)

        base_metadata = {
            "document_id": str(document_id),
            "tenant_id": str(tenant_id),
            "title": raw_doc.title,
            "source": raw_doc.source,
            **extra_metadata,
        }

        all_chunks = self.splitter.split(raw_doc.text, base_metadata)

        parents = {str(c.id): c for c in all_chunks if c.chunk_type == "parent"}
        children = [c for c in all_chunks if c.chunk_type == "child"]

        if not children:
            logger.warning("No child chunks produced for document %s", document_id)
            return 0

        logger.info("Embedding %d child chunks", len(children))

        texts = [c.text for c in children]

        dense_vecs, sparse_vecs = await asyncio.gather(
            self.dense.embed_batch(texts),
            self.sparse.embed_batch(texts),
        )

        points = []

        for chunk, dense_vec, sparse_vec in zip(children, dense_vecs, sparse_vecs, strict=False):
            parent_id = str(chunk.parent_id) if chunk.parent_id else None
            parent = parents.get(parent_id) if parent_id else None

            # Динамически собираем векторы, избегая передачи None
            vector: dict[str, Any] = {"dense": dense_vec}

            if sparse_vec and getattr(sparse_vec, "indices", None):
                vector["sparse"] = SparseVector(
                    indices=sparse_vec.indices,
                    values=sparse_vec.values,
                )

            points.append(
                PointStruct(
                    id=chunk.id,
                    vector=cast(dict[str, Any], vector),
                    payload={
                        **chunk.metadata,
                        "text": chunk.text,
                        "parent_text": parent.text if parent else chunk.text,
                    },
                )
            )

        await self._upsert_batched(points)

        logger.info("Indexed %d chunks for document %s", len(points), document_id)
        return len(points)

    async def delete_document(self, document_id: UUID, tenant_id: UUID):
        """
        Удаляет все точки документа из Qdrant.
        """
        qdrant = get_qdrant()

        # Оборачиваем Filter в FilterSelector для строгого соответствия API Qdrant
        await qdrant.delete(
            collection_name=self.collection,
            points_selector=FilterSelector(
                filter=Filter(
                    must=[
                        FieldCondition(
                            key="document_id",
                            match=MatchValue(value=str(document_id)),
                        ),
                        FieldCondition(
                            key="tenant_id",
                            match=MatchValue(value=str(tenant_id)),
                        ),
                    ]
                )
            ),
        )

        logger.info("Deleted vectors for document %s", document_id)

    async def _upsert_batched(self, points: list[PointStruct]):
        """
        Батчевый upsert — защита от timeout и перегрузки Qdrant.
        """
        if not points:
            return

        qdrant = get_qdrant()

        for i in range(0, len(points), BATCH_SIZE):
            batch = points[i : i + BATCH_SIZE]

            await qdrant.upsert(
                collection_name=self.collection,
                points=batch,
                wait=True,
            )
