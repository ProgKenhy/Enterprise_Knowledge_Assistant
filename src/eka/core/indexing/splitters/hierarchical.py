import re
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

import tiktoken

_ENCODER = tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    return len(_ENCODER.encode(text))


@dataclass
class Chunk:
    id: str
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)
    chunk_type: str = "child"
    parent_id: str | None = None


class HierarchicalSplitter:
    """
    Hybrid RAG splitter:

    - Parent chunks: semantic (paragraph-based)
    - Child chunks: sentence-based retrieval units
    - Fallback: token window for "dirty" text (logs, code, JSON)
    """

    def __init__(
        self,
        parent_chunk_size: int = 1500,
        child_chunk_size: int = 400,
        child_overlap: int = 50,
    ):
        if child_overlap >= child_chunk_size:
            raise ValueError("child_overlap must be smaller than child_chunk_size")

        self.parent_chunk_size = parent_chunk_size
        self.child_chunk_size = child_chunk_size
        self.child_overlap = child_overlap

    def split(self, text: str, base_metadata: dict[str, Any]) -> list[Chunk]:
        if not text or not text.strip():
            return []

        paragraphs = self._split_into_paragraphs(text)
        parents = self._build_parent_chunks(paragraphs, base_metadata)

        chunks: list[Chunk] = []

        for parent in parents:
            chunks.append(parent)

            children = self._build_child_chunks(parent)

            if not children:
                children = self._build_token_fallback_chunks(parent)

            chunks.extend(children)

        return chunks

    # ─────────────────────────────
    # Parent level (semantic)
    # ─────────────────────────────

    def _split_into_paragraphs(self, text: str) -> list[str]:
        return [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]

    def _build_parent_chunks(
        self,
        paragraphs: list[str],
        base_metadata: dict[str, Any],
    ) -> list[Chunk]:
        parents: list[Chunk] = []
        buffer: list[str] = []
        tokens = 0
        idx = 0

        for para in paragraphs:
            t = count_tokens(para)

            if t > self.parent_chunk_size:
                if buffer:
                    parents.append(self._make_parent(buffer, idx, base_metadata))
                    idx += 1
                    buffer = []
                    tokens = 0

                parents.append(self._make_parent([para], idx, base_metadata))
                idx += 1
                continue

            if buffer and (tokens + t > self.parent_chunk_size):
                parents.append(self._make_parent(buffer, idx, base_metadata))
                idx += 1
                buffer = []
                tokens = 0

            buffer.append(para)
            tokens += t

        if buffer:
            parents.append(self._make_parent(buffer, idx, base_metadata))

        return parents

    def _make_parent(
        self,
        paragraphs: list[str],
        index: int,
        base_metadata: dict[str, Any],
    ) -> Chunk:
        return Chunk(
            id=str(uuid4()),
            text="\n\n".join(paragraphs),
            chunk_type="parent",
            metadata={
                **base_metadata,
                "chunk_index": index,
                "chunk_type": "parent",
            },
        )

    # ─────────────────────────────
    # Child level (retrieval units)
    # ─────────────────────────────

    def _build_child_chunks(self, parent: Chunk) -> list[Chunk]:
        sentences = re.split(r"(?<=[.!?])\s+", parent.text)

        chunks: list[Chunk] = []
        buffer: list[str] = []
        tokens = 0
        idx = 0

        for s in sentences:
            s = s.strip()
            if not s:
                continue

            t = count_tokens(s)

            if t > self.child_chunk_size:
                if buffer:
                    chunks.append(self._make_child(" ".join(buffer), parent, idx))
                    idx += 1
                    buffer = []
                    tokens = 0

                chunks.append(self._make_child(s, parent, idx))
                idx += 1
                continue

            if buffer and (tokens + t > self.child_chunk_size):
                chunks.append(self._make_child(" ".join(buffer), parent, idx))
                idx += 1

                overlap: list[str] = []
                ot = 0

                for prev in reversed(buffer):
                    pt = count_tokens(prev)
                    if ot + pt <= self.child_overlap:
                        overlap.insert(0, prev)
                        ot += pt
                    else:
                        break

                buffer = overlap
                tokens = ot

            buffer.append(s)
            tokens += t

        if buffer:
            chunks.append(self._make_child(" ".join(buffer), parent, idx))

        return chunks

    def _make_child(self, text: str, parent: Chunk, index: int) -> Chunk:
        return Chunk(
            id=str(uuid4()),
            text=text,
            chunk_type="child",
            parent_id=parent.id,
            metadata={
                **parent.metadata,
                "chunk_type": "child",
                "child_index": index,
                "parent_id": parent.id,
            },
        )

    # ─────────────────────────────
    # Fallback (dirty text safety)
    # ─────────────────────────────

    def _build_token_fallback_chunks(self, parent: Chunk) -> list[Chunk]:
        tokens = _ENCODER.encode(parent.text)

        chunks: list[Chunk] = []
        idx = 0
        start = 0

        while start < len(tokens):
            end = min(start + self.child_chunk_size, len(tokens))
            text = _ENCODER.decode(tokens[start:end])

            chunks.append(self._make_child(text, parent, idx))
            idx += 1

            next_start = end - self.child_overlap
            if next_start <= start:
                break

            start = next_start

        return chunks
