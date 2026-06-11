import logging

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance,
    HnswConfigDiff,
    OptimizersConfigDiff,
    PayloadSchemaType,
    SparseIndexParams,
    SparseVectorParams,
    VectorParams,
)

from eka.config import get_settings

logger = logging.getLogger(__name__)

_client: AsyncQdrantClient | None = None


def _create_client() -> AsyncQdrantClient:
    """Создает новый клиент Qdrant."""
    settings = get_settings()
    return AsyncQdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY, timeout=30)


async def init_qdrant(url: str, collection: str, dim: int, api_key: str | None = None):
    """
    Вызывается один раз при старте FastAPI (в lifespan).
    Создает клиента и коллекцию.
    """
    global _client
    _client = AsyncQdrantClient(url=url, api_key=api_key, timeout=30)
    await _ensure_collection(_client, collection, dim)
    logger.info("Qdrant ready: collection=%s dim=%d", collection, dim)


async def close_qdrant():
    """Закрывает клиент. Используется в FastAPI lifespan и в Celery."""
    global _client
    if _client is not None:
        await _client.close()
        _client = None
        logger.info("Qdrant client closed")


def get_qdrant() -> AsyncQdrantClient:
    """
    Возвращает клиент Qdrant.
    Для FastAPI: использует глобальный клиент (создается в lifespan).
    Для Celery: клиент должен быть создан явно через reset_qdrant_for_task().
    """
    global _client
    if _client is None:
        # Это не должно происходить в FastAPI (lifespan создает клиент).
        # Но для Celery мы создаем клиента в reset_qdrant_for_task().
        _client = _create_client()
        logger.info("Qdrant client created (fallback)")
    return _client


def reset_qdrant_for_task():
    """
    Сбрасывает глобальный клиент перед задачей Celery.
    Гарантирует, что для каждой задачи создается новый клиент,
    привязанный к новому event loop.
    """
    global _client
    _client = None
    logger.info("Qdrant client reset for new task")


async def _ensure_collection(client: AsyncQdrantClient, collection: str, dim: int):
    """Идемпотентно создает коллекцию и payload-индексы."""
    existing = await client.get_collections()
    existing_names = {c.name for c in existing.collections}

    if collection in existing_names:
        return

    await client.create_collection(
        collection_name=collection,
        vectors_config={
            "dense": VectorParams(
                size=dim,
                distance=Distance.COSINE,
                on_disk=False,
            )
        },
        sparse_vectors_config={"sparse": SparseVectorParams(index=SparseIndexParams())},
        optimizers_config=OptimizersConfigDiff(indexing_threshold=20_000),
        hnsw_config=HnswConfigDiff(
            m=16,
            ef_construct=100,
        ),
    )

    logger.info("Created Qdrant collection: %s", collection)

    for field in ("tenant_id", "document_id", "chunk_type"):
        await client.create_payload_index(
            collection_name=collection,
            field_name=field,
            field_schema=PayloadSchemaType.KEYWORD,
        )


async def ensure_qdrant_ready():
    """
    Вызывается в начале задачи Celery.
    Гарантирует, что клиент создан и коллекция существует.
    """
    client = get_qdrant()
    settings = get_settings()
    await _ensure_collection(client, settings.QDRANT_COLLECTION, settings.EMBEDDING_DIM)
    logger.info("Qdrant ready for indexing")
