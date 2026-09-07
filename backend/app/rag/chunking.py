"""Chunking for the RAG policy assistant (US-29).

Chunk size and overlap are configuration, not magic numbers (US-29 DoD) —
see Settings.rag_chunk_size / rag_chunk_overlap in app/config.py.

Chunking is section-aware: markdown documents are first split on `#`/`##`
headings, and only sections longer than the configured chunk size are
further split with a sliding window. This means most chunks map to exactly
one real heading, which is what makes a meaningful, human-readable
section_reference possible for citations (US-30 AC).
"""

import re
from dataclasses import dataclass

_HEADING_RE = re.compile(r"^#{1,6}\s+(.*)$", re.MULTILINE)


@dataclass(frozen=True)
class Chunk:
    source_document: str
    section_reference: str
    chunk_index: int
    text: str


def _split_into_sections(raw_text: str) -> list[tuple[str, str]]:
    """Splits markdown text into (heading, body) pairs. Content before the
    first heading, if any, is kept under a generic "Introduction" heading
    rather than silently dropped."""
    matches = list(_HEADING_RE.finditer(raw_text))
    if not matches:
        stripped = raw_text.strip()
        return [("Document", stripped)] if stripped else []

    sections: list[tuple[str, str]] = []
    if matches[0].start() > 0:
        preamble = raw_text[: matches[0].start()].strip()
        if preamble:
            sections.append(("Introduction", preamble))

    for i, match in enumerate(matches):
        heading = match.group(1).strip()
        body_start = match.end()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(raw_text)
        body = raw_text[body_start:body_end].strip()
        if body:
            sections.append((heading, body))

    return sections


def _sliding_window(text: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    if len(text) <= chunk_size:
        return [text]

    pieces = []
    step = max(chunk_size - chunk_overlap, 1)
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        piece = text[start:end].strip()
        if piece:
            pieces.append(piece)
        if end == len(text):
            break
        start += step
    return pieces


def chunk_document(source_document: str, raw_text: str, chunk_size: int, chunk_overlap: int) -> list[Chunk]:
    chunks: list[Chunk] = []
    index = 0
    for heading, body in _split_into_sections(raw_text):
        for piece in _sliding_window(body, chunk_size, chunk_overlap):
            chunks.append(
                Chunk(source_document=source_document, section_reference=heading, chunk_index=index, text=piece)
            )
            index += 1
    return chunks
