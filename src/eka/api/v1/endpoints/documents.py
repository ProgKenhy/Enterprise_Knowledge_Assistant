from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from eka.db.models import DocumentStatus, User, UserRole
from eka.deps import get_db_session, get_user_by_token, require_role
from eka.repositories.document import (
    delete_document,
    get_document_or_404,
    get_documents,
    upload_document,
)
from eka.schemas.document import DocumentListResponse, DocumentResponse
from eka.tasks.indexing import index_document

documents_router = APIRouter()


@documents_router.post(
    "",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Загрузить документ",
)
async def upload_document_endpoint(
    # Form + File нельзя смешивать с BaseModel — только отдельные параметры
    file: Annotated[UploadFile, File(description="PDF, DOCX, HTML или Markdown")],
    title: Annotated[str, Form(min_length=1, max_length=500)],
    current_user: Annotated[User, Depends(require_role(UserRole.admin, UserRole.superadmin))],
    db: Annotated[AsyncSession, Depends(get_db_session)],
):
    """
    Загружает файл и создаёт запись документа со статусом `pending`.
    После успешной загрузки ставит задачу индексирования в очередь.

    Доступно только admin и superadmin.
    """
    document = await upload_document(
        file=file,
        title=title,
        tenant_id=current_user.tenant_id,
        db=db,
    )
    await db.commit()
    await db.refresh(document)

    # Запуск индексирования в фоне
    index_document.delay(  # type: ignore[attr-defined]
        document_id=str(document.id),
        tenant_id=str(current_user.tenant_id),
        file_path=document.file_path,
        source_type=document.source_type,
    )

    return DocumentResponse.model_validate(document)


@documents_router.get(
    "",
    response_model=DocumentListResponse,
    summary="Список документов тенанта",
)
async def list_documents_endpoint(
    current_user: Annotated[User, Depends(get_user_by_token)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    doc_status: Annotated[DocumentStatus | None, Query(alias="status")] = None,
    source_type: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    """
    Возвращает документы текущего тенанта с пагинацией.
    Доступно всем авторизованным пользователям тенанта.
    """
    documents, total = await get_documents(
        tenant_id=current_user.tenant_id,
        db=db,
        status=doc_status,
        source_type=source_type,
        limit=limit,
        offset=offset,
    )

    return DocumentListResponse(
        items=[DocumentResponse.model_validate(d) for d in documents],
        total=total,
        limit=limit,
        offset=offset,
    )


@documents_router.get(
    "/{document_id}",
    response_model=DocumentResponse,
    summary="Получить документ по ID",
)
async def get_document_endpoint(
    document_id: UUID,
    current_user: Annotated[User, Depends(get_user_by_token)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
):
    document = await get_document_or_404(
        document_id=document_id,
        tenant_id=current_user.tenant_id,  # нельзя получить чужой документ
        db=db,
    )
    return DocumentResponse.model_validate(document)


@documents_router.delete(
    "/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить документ",
)
async def delete_document_endpoint(
    document_id: UUID,
    current_user: Annotated[User, Depends(require_role(UserRole.admin, UserRole.superadmin))],
    db: Annotated[AsyncSession, Depends(get_db_session)],
):
    """
    Удаляет документ из БД и файл с диска.
    Статус `processing` блокирует удаление.
    Векторы из Qdrant будут очищены на шаге 7.
    """
    await delete_document(
        document_id=document_id,
        tenant_id=current_user.tenant_id,
        db=db,
    )
    await db.commit()
