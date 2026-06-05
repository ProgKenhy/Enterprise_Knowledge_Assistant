from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from eka.db.models import DocumentStatus

# Форматы, которые принимает система
ALLOWED_CONTENT_TYPES = {
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "text/html": "html",
    "text/markdown": "markdown",
    "text/plain": "markdown",
}
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".html", ".htm", ".md", ".txt"}
MAX_FILE_SIZE_MB = 50


class DocumentResponse(BaseModel):
    """Возвращается клиенту. Никогда не содержит file_path (внутренний путь)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    title: str
    source_type: str
    status: DocumentStatus
    chunk_count: int | None
    created_at: datetime
    updated_at: datetime
    indexed_at: datetime | None


class DocumentListResponse(BaseModel):
    """Список документов с пагинацией."""

    items: list[DocumentResponse]
    total: int
    limit: int
    offset: int
