import asyncio
import logging
from pathlib import Path

import trafilatura

from .base import RawDocument

logger = logging.getLogger(__name__)


class HTMLLoader:
    """
    Загружает HTML через trafilatura.

    Удаляет навигацию, рекламу, футеры и прочий шум,
    оставляя основной контент страницы для RAG.
    """

    async def load(self, file_path: str) -> RawDocument:
        text, title = await asyncio.to_thread(self._extract, file_path)

        return RawDocument(
            text=text,
            title=title,
            source=file_path,
        )

    def _extract(self, file_path: str) -> tuple[str, str]:
        try:
            html = Path(file_path).read_text(
                encoding="utf-8",
                errors="replace",
            )

            text = trafilatura.extract(
                html,
                include_tables=True,
                include_links=False,
                include_images=False,
                no_fallback=False,
            )

            if not text:
                text = (
                    trafilatura.extract(
                        html,
                        favor_recall=True,
                    )
                    or ""
                )

            metadata = trafilatura.extract_metadata(html)

            title = Path(file_path).stem

            if metadata and getattr(metadata, "title", None):
                title = str(metadata.title).strip()

            return text.strip(), title

        except Exception:
            logger.exception("Failed to process HTML %s", file_path)
            raise


class MarkdownLoader:
    """
    Загружает Markdown и plain text.

    Markdown сохраняется как есть, чтобы сплиттеры могли
    использовать структуру заголовков при разбиении документа.
    """

    async def load(self, file_path: str) -> RawDocument:
        text, title = await asyncio.to_thread(self._extract, file_path)

        return RawDocument(
            text=text,
            title=title,
            source=file_path,
        )

    def _extract(self, file_path: str) -> tuple[str, str]:
        text = (
            Path(file_path)
            .read_text(
                encoding="utf-8",
                errors="replace",
            )
            .strip()
        )

        title = Path(file_path).stem

        for line in text.splitlines():
            stripped_line = line.strip()

            if stripped_line.startswith("#"):
                heading = stripped_line.lstrip("#").strip()

                if heading:
                    title = heading
                    break

        return text, title
