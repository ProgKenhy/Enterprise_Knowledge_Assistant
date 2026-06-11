from .base import DocumentLoader, RawDocument
from .docx_loader import DOCXLoader
from .html_markdown_loaders import HTMLLoader, MarkdownLoader
from .pdf_loader import PDFLoader
from .txt_loader import TxtLoader

__all__ = ["DocumentLoader", "RawDocument", "get_loader"]

_LOADERS: dict[str, DocumentLoader] = {
    "pdf": PDFLoader(),
    "docx": DOCXLoader(),
    "html": HTMLLoader(),
    "markdown": MarkdownLoader(),
    "txt": TxtLoader(),
}


def get_loader(source_type: str) -> DocumentLoader:
    """
    Фабрика: возвращает нужный лоадер по типу документа.

    source_type приходит из поля Document.source_type в БД,
    которое заполняется при загрузке файла в DocumentService.
    """
    loader = _LOADERS.get(source_type)
    if not loader:
        raise ValueError(f"No loader for source_type={source_type!r}. Available: {list(_LOADERS)}")
    return loader
