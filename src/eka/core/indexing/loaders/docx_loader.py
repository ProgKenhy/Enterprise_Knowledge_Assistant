import asyncio
import logging
from pathlib import Path

from docx import Document as DocxDocument
from docx.table import Table
from docx.text.paragraph import Paragraph

from .base import RawDocument

logger = logging.getLogger(__name__)


class DOCXLoader:
    """
    Загружает DOCX и конвертирует его в Markdown-подобный текст.

    Особенности:
    - сохраняет структуру заголовков (H1/H2/H3);
    - сохраняет порядок параграфов и таблиц;
    - преобразует таблицы в текстовый вид;
    - работает за O(N), без поиска элементов по всему документу.
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
            doc = DocxDocument(file_path)
        except Exception:
            logger.exception("Failed to read DOCX %s", file_path)
            raise

        blocks: list[str] = []

        metadata_title = doc.core_properties.title.strip() if doc.core_properties.title else ""

        fallback_title = Path(file_path).stem
        title = metadata_title or fallback_title

        h1_found = False

        for element in doc.element.body:
            tag = element.tag.split("}")[-1]

            if tag == "p":
                paragraph = Paragraph(element, doc)
                paragraph_text = self._parse_paragraph(paragraph)

                if not paragraph_text:
                    continue

                if not metadata_title and not h1_found and paragraph_text.startswith("# "):
                    title = paragraph_text[2:].strip()
                    h1_found = True

                blocks.append(paragraph_text)

            elif tag == "tbl":
                table = Table(element, doc)
                table_text = self._parse_table(table)

                if table_text:
                    blocks.append(table_text)

        return "\n\n".join(blocks), title

    def _parse_paragraph(self, paragraph: Paragraph) -> str:
        text = paragraph.text.strip()

        if not text:
            return ""

        style = paragraph.style
        style_name = style.name.lower() if style and style.name else ""

        if "heading 1" in style_name or "заголовок 1" in style_name:
            return f"# {text}"

        if "heading 2" in style_name or "заголовок 2" in style_name:
            return f"## {text}"

        if "heading 3" in style_name or "заголовок 3" in style_name:
            return f"### {text}"

        return text

    def _parse_table(self, table: Table) -> str:
        rows: list[str] = []
        for row in table.rows:
            seen: set[int] = set()
            cells: list[str] = []

            for cell in row.cells:
                if id(cell) not in seen:
                    seen.add(id(cell))
                    cells.append(cell.text.strip())

            if any(cells):
                rows.append(" | ".join(cells))

        return "\n".join(rows)
