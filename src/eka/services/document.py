import hashlib
import os
from pathlib import Path
from uuid import UUID

import aiofiles
from fastapi import HTTPException, UploadFile, status

from eka.config import get_settings
from eka.schemas.document import ALLOWED_CONTENT_TYPES, ALLOWED_EXTENSIONS, MAX_FILE_SIZE_MB

settings = get_settings()


def _get_upload_dir(tenant_id: UUID) -> Path:
    """
    Каждый тенант хранит файлы в отдельной папке.
    Изоляция на уровне файловой системы + нет коллизий имён.
    """
    upload_dir = Path(settings.UPLOAD_DIR) / str(tenant_id)
    upload_dir.mkdir(parents=True, exist_ok=True)
    return upload_dir


def _validate_file(file: UploadFile) -> str:
    """
    Проверяет тип файла и возвращает source_type ('pdf', 'docx', ...).
    Двойная проверка: content_type заголовок + расширение файла.
    Только content_type ненадёжно — браузеры иногда шлют 'application/octet-stream'.
    """
    ext = Path(file.filename or "").suffix.lower()

    source_type = ALLOWED_CONTENT_TYPES.get(file.content_type or "")

    if not source_type and ext in ALLOWED_EXTENSIONS:
        # Фолбэк: определяем по расширению если content_type не распознан
        ext_map = {
            ".pdf": "pdf",
            ".docx": "docx",
            ".html": "html",
            ".htm": "html",
            ".md": "markdown",
            ".txt": "markdown",
        }
        source_type = ext_map.get(ext)

    if not source_type:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file type: {file.content_type!r}. "
            f"Allowed: pdf, docx, html, markdown",
        )

    return source_type


async def _save_file_and_hash(file: UploadFile, dest_path: Path) -> tuple[str, int]:
    """
    Сохраняет файл и считает SHA-256 хэш за один проход чтения.
    Читаем чанками — не грузим весь файл в память (важно для 50MB PDF).

    Returns: (hex_hash, file_size_bytes)
    """
    hasher = hashlib.sha256()
    total_size = 0
    max_bytes = MAX_FILE_SIZE_MB * 1024 * 1024
    chunk_size = 1024 * 1024  # 1MB чанки

    async with aiofiles.open(dest_path, "wb") as f:
        while chunk := await file.read(chunk_size):
            total_size += len(chunk)

            if total_size > max_bytes:
                # Удаляем частично записанный файл
                await f.close()
                os.unlink(dest_path)
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=f"File exceeds {MAX_FILE_SIZE_MB}MB limit",
                )

            hasher.update(chunk)
            await f.write(chunk)

    return hasher.hexdigest(), total_size
