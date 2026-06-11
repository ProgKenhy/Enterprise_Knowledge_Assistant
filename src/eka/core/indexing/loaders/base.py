from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass
class RawDocument:
    """Результат работы любого лоадера — чистый текст + метаданные."""

    text: str
    title: str
    source: str
    metadata: dict = field(default_factory=dict)


@runtime_checkable
class DocumentLoader(Protocol):
    """
    Протокол для всех лоадеров.
    """

    async def load(self, file_path: str) -> RawDocument: ...
