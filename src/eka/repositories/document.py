import os
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from eka.db.models import Document, DocumentStatus
from eka.services.document import (
    _get_upload_dir,
    _save_file_and_hash,
    _validate_file,
)


async def get_documents(
    tenant_id: UUID,
    db: AsyncSession,
    status: DocumentStatus | None = None,
    source_type: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[Document], int]:
    """
    Возвращает (список документов, общее количество).
    Всегда фильтрует по tenant_id.
    """
    base_query = select(Document).where(Document.tenant_id == tenant_id)

    if status:
        base_query = base_query.where(Document.status == status)
    if source_type:
        base_query = base_query.where(Document.source_type == source_type)

    # Считаем total отдельным запросом (нужен для пагинации на фронте)
    total = await db.scalar(select(func.count()).select_from(base_query.subquery()))

    documents = await db.scalars(
        base_query.order_by(Document.created_at.desc()).limit(limit).offset(offset)
    )

    return list(documents.all()), total or 0


async def get_document_or_404(
    document_id: UUID,
    tenant_id: UUID,
    db: AsyncSession,
) -> Document:
    """Получает документ, проверяя принадлежность тенанту."""
    document = await db.scalar(
        select(Document).where(
            Document.id == document_id,
            Document.tenant_id == tenant_id,  # ← изоляция тенантов
        )
    )
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )
    return document


async def delete_document(
    document_id: UUID,
    tenant_id: UUID,
    db: AsyncSession,
) -> None:
    """
    Удаляет документ из БД и файл с диска.
    Векторы из Qdrant будут удалены отдельной Celery-задачей (шаг 7).
    """
    document = await get_document_or_404(document_id, tenant_id, db)

    # Нельзя удалять документ пока он индексируется
    if document.status == DocumentStatus.processing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot delete document while it is being processed",
        )

    # Удаляем физический файл если есть
    if document.file_path and Path(document.file_path).exists():
        os.unlink(document.file_path)

    await db.delete(document)


async def upload_document(
    file: UploadFile,
    title: str,
    tenant_id: UUID,
    db: AsyncSession,
) -> Document:
    """
    Полный цикл загрузки документа:
    1. Валидация типа файла
    2. Сохранение с подсчётом хэша
    3. Проверка дубликата по хэшу
    4. Создание записи в БД

    Commit не делает — вызывающий код сам решает когда коммитить.
    """
    source_type = _validate_file(file)

    upload_dir = _get_upload_dir(tenant_id)
    # Уникальное имя файла — избегаем коллизий при одинаковых оригинальных именах
    safe_filename = f"{uuid4()}{Path(file.filename or 'file').suffix.lower()}"
    dest_path = upload_dir / safe_filename

    content_hash, _ = await _save_file_and_hash(file, dest_path)

    # Дедупликация: тот же файл от того же тенанта уже есть?
    existing = await db.scalar(
        select(Document).where(
            Document.tenant_id == tenant_id,
            Document.content_hash == content_hash,
        )
    )
    if existing:
        # Удаляем только что сохранённый дубль
        os.unlink(dest_path)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Document with identical content already exists (id={existing.id})",
        )

    document = Document(
        tenant_id=tenant_id,
        title=title,
        source_type=source_type,
        file_path=str(dest_path),
        content_hash=content_hash,
        status=DocumentStatus.pending,
    )
    db.add(document)
    await db.flush()

    return document
