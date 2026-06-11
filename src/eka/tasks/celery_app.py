from celery import Celery
from celery.signals import worker_process_init
from fastembed import SparseTextEmbedding

from eka.config import get_settings

settings = get_settings()

celery_app = Celery(
    "eka",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["eka.tasks.indexing"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    broker_connection_retry_on_startup=True,
    task_soft_time_limit=1800,  # 30 минут — предупреждение
    task_time_limit=2400,  # 40 минут — жёсткий лимит
    task_default_queue="indexing",
    task_routes={
        "eka.tasks.indexing.*": {"queue": "indexing"},
    },
)


@worker_process_init.connect(weak=False)
def preload_models(**kwargs):
    """Предзагружает модели эмбеддингов при старте воркера."""
    from fastembed import TextEmbedding

    from eka.config import get_settings

    settings = get_settings()
    print(f"🔄 Preloading embedding model: {settings.EMBEDDING_DENSE_MODEL}")
    TextEmbedding(model_name=settings.EMBEDDING_DENSE_MODEL)
    print("✅ Embedding dense model preloaded")
    print(f"🔄 Preloading embedding model: {settings.EMBEDDING_SPARSE_MODEL}")
    SparseTextEmbedding(model_name=settings.EMBEDDING_SPARSE_MODEL)
    print("✅ Embedding sparse model preloaded")
