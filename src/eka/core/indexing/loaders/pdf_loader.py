import asyncio
import logging
import re
from pathlib import Path

import fitz

from .base import RawDocument

logger = logging.getLogger(__name__)


class PDFLoader:
    """
    Загружает PDF через PyMuPDF.

    Что делает:
    - Извлекает текст страниц в правильном порядке
    - Удаляет артефакты PDF-разметки
    - Отфильтровывает колонтитулы по позиции
    - Выполняет синхронную работу в отдельном потоке
    """

    HEADER_FOOTER_MARGIN = 0.07

    async def load(self, file_path: str) -> RawDocument:
        return await asyncio.to_thread(self._process_file, file_path)

    def _process_file(self, file_path: str) -> RawDocument:
        with fitz.open(file_path) as doc:
            return RawDocument(
                text=self._extract_text_from_doc(doc),
                title=self._extract_title_from_doc(doc, file_path),
                source=file_path,
                metadata={"page_count": doc.page_count},
            )

    def _extract_text_from_doc(self, doc: fitz.Document) -> str:
        pages_text: list[str] = []

        for page in doc:
            page_height = page.rect.height
            blocks = page.get_text("blocks", sort=True)

            page_lines: list[str] = []

            for block in blocks:
                _, y0, _, y1, text, *_ = block

                if y0 < page_height * self.HEADER_FOOTER_MARGIN:
                    continue

                if y1 > page_height * (1 - self.HEADER_FOOTER_MARGIN):
                    continue

                cleaned = self._clean_text(text)

                if cleaned:
                    page_lines.append(cleaned)

            if page_lines:
                pages_text.append("\n".join(page_lines))

        return "\n\n".join(pages_text)

    def _extract_title_from_doc(self, doc: fitz.Document, file_path: str) -> str:
        metadata = doc.metadata or {}
        title = str(metadata.get("title", "")).strip()

        return title or Path(file_path).stem

    def _clean_text(self, text: str) -> str:
        # Склеиваем переносы внутри слов:
        # "при-\nмер" -> "пример"
        text = re.sub(r"-\n(\w)", r"\1", text)

        # Убираем лишние пробелы
        text = re.sub(r" {2,}", " ", text)

        # Убираем лишние пустые строки
        text = re.sub(r"\n{3,}", "\n\n", text)

        return text.strip()
