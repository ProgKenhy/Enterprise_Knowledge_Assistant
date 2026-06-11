import asyncio
import logging
from datetime import UTC, datetime
from uuid import UUID

from celery import Task
from sqlalchemy import select

from eka.config import get_settings
from eka.core.indexing.pipeline import IndexingPipeline
from eka.core.indexing.vector_store import (
    close_qdrant,
    ensure_qdrant_ready,
    reset_qdrant_for_task,
)
from eka.db.models import Document, DocumentStatus
from eka.deps import get_sync_db_session
from eka.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)
settings = get_settings()


class IndexingTask(Task):
    _pipeline: IndexingPipeline | None = None

    @property
    def pipeline(self) -> IndexingPipeline:
        if self._pipeline is None:
            self._pipeline = IndexingPipeline(
                collection=settings.QDRANT_COLLECTION,
            )
        return self._pipeline


@celery_app.task(
    bind=True,
    base=IndexingTask,
    name="eka.tasks.indexing.index_document",
    max_retries=3,
    default_retry_delay=60,
    acks_late=True,
)
def index_document(
    self,
    document_id: str,
    tenant_id: str,
    file_path: str,
    source_type: str,
) -> dict:
    doc_uuid = UUID(document_id)
    tenant_uuid = UUID(tenant_id)

    _update_status(doc_uuid, DocumentStatus.processing)

    try:

        async def _run_indexing():
            # Сбрасываем клиент, чтобы он создался заново для этого loop
            reset_qdrant_for_task()

            try:
                await ensure_qdrant_ready()
                return await self.pipeline.run(
                    document_id=doc_uuid,
                    tenant_id=tenant_uuid,
                    file_path=file_path,
                    source_type=source_type,
                )
            finally:
                # Закрываем клиент ДО завершения asyncio.run()
                await close_qdrant()

        chunk_count = asyncio.run(_run_indexing())

        _update_status(
            doc_uuid,
            DocumentStatus.indexed,
            chunk_count=chunk_count,
            indexed_at=datetime.now(UTC),
        )

        logger.info("Document %s indexed: %d chunks", document_id, chunk_count)
        return {"document_id": document_id, "chunk_count": chunk_count}

    except Exception as exc:
        logger.exception("Failed to index document %s", document_id)

        if self.request.retries < self.max_retries:
            _update_status(doc_uuid, DocumentStatus.pending)
            raise self.retry(exc=exc, countdown=60 * 2**self.request.retries) from exc

        _update_status(doc_uuid, DocumentStatus.failed, error=str(exc))
        raise


def _update_status(
    document_id: UUID,
    status: DocumentStatus,
    chunk_count: int | None = None,
    indexed_at: datetime | None = None,
    error: str | None = None,
):
    with get_sync_db_session() as session:
        doc = session.scalar(select(Document).where(Document.id == document_id))
        if not doc:
            logger.error("Document %s not found for status update", document_id)
            return

        doc.status = status

        if chunk_count is not None:
            doc.chunk_count = chunk_count
        if indexed_at is not None:
            doc.indexed_at = indexed_at
        if error is not None:
            doc.metadata_["last_error"] = error[:500]

        session.commit()
