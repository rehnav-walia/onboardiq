"""Local vector store for the RAG policy assistant (US-29), backed by a
persistent Chroma collection — local, no external service required (see
CLAUDE.md tech stack). Telemetry is explicitly disabled: "no external
service" should also mean no silent phone-home.

Embeddings are computed locally by Chroma's default embedding function (a
small ONNX MiniLM model, downloaded once and cached). Ingestion and
retrieval therefore need no Anthropic API key at all — only the final
answer-synthesis step in app/rag/assistant.py does.
"""

from dataclasses import dataclass
from pathlib import Path

import chromadb
from chromadb.config import Settings as ChromaSettings
from chromadb.utils import embedding_functions

from app.config import get_settings
from app.rag.chunking import chunk_document

_COLLECTION_NAME = "policy_documents"

_client = None
_collection = None


def _get_collection():
    global _client, _collection
    if _collection is None:
        settings = get_settings()
        Path(settings.chroma_persist_dir).mkdir(parents=True, exist_ok=True)
        _client = chromadb.PersistentClient(
            path=settings.chroma_persist_dir,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        embedding_fn = embedding_functions.DefaultEmbeddingFunction()
        _collection = _client.get_or_create_collection(name=_COLLECTION_NAME, embedding_function=embedding_fn)
    return _collection


def reset_collection_cache() -> None:
    """Test-only: forces the next call to reopen the collection — used when
    a test points CHROMA_PERSIST_DIR at a fresh temp directory."""
    global _client, _collection
    _client = None
    _collection = None


def ingest_document(source_document: str, raw_text: str) -> int:
    """Chunks and (re-)embeds one document. Idempotent (US-29 AC): every
    existing chunk for this source_document is deleted first, so re-running
    never creates duplicates and correctly handles a document that has
    shrunk, grown, or changed since the last run. Returns the chunk count.
    """
    settings = get_settings()
    collection = _get_collection()

    collection.delete(where={"source_document": source_document})

    chunks = chunk_document(source_document, raw_text, settings.rag_chunk_size, settings.rag_chunk_overlap)
    if not chunks:
        return 0

    collection.add(
        ids=[f"{source_document}::chunk-{c.chunk_index}" for c in chunks],
        documents=[c.text for c in chunks],
        metadatas=[
            {
                "source_document": c.source_document,
                "section_reference": c.section_reference,
                "chunk_index": c.chunk_index,
            }
            for c in chunks
        ],
    )
    return len(chunks)


def ingest_directory(directory: str) -> dict[str, int]:
    """Ingests every .md/.txt file in a directory. Returns
    {filename: chunk_count} (US-29 AC: ingestion reports how many chunks
    were created)."""
    directory_path = Path(directory)
    if not directory_path.is_dir():
        return {}

    paths = sorted(directory_path.glob("*.md")) + sorted(directory_path.glob("*.txt"))
    return {path.name: ingest_document(path.name, path.read_text(encoding="utf-8")) for path in paths}


def count_chunks() -> int:
    return _get_collection().count()


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: str
    source_document: str
    section_reference: str
    text: str
    distance: float


def retrieve_top_k(query: str, k: int) -> list[RetrievedChunk]:
    """US-29 AC: retrieval returns the top-k relevant chunks for a query."""
    collection = _get_collection()
    total = collection.count()
    if total == 0:
        return []

    results = collection.query(query_texts=[query], n_results=min(k, total))
    ids = results["ids"][0]
    documents = results["documents"][0]
    metadatas = results["metadatas"][0]
    distances = results["distances"][0]

    return [
        RetrievedChunk(
            chunk_id=chunk_id,
            source_document=metadata["source_document"],
            section_reference=metadata["section_reference"],
            text=text,
            distance=distance,
        )
        for chunk_id, text, metadata, distance in zip(ids, documents, metadatas, distances)
    ]


def list_chunks_for_document(source_document: str) -> list[RetrievedChunk]:
    """Every chunk currently stored for one source document, independent of
    any query ranking — used to verify ingestion/idempotency directly, and
    to independently confirm a citation corresponds to real stored content
    (US-30 DoD) rather than re-using the same query that produced it."""
    collection = _get_collection()
    result = collection.get(where={"source_document": source_document})
    return [
        RetrievedChunk(
            chunk_id=chunk_id,
            source_document=metadata["source_document"],
            section_reference=metadata["section_reference"],
            text=text,
            distance=0.0,
        )
        for chunk_id, text, metadata in zip(result["ids"], result["documents"], result["metadatas"])
    ]


def get_chunk_by_id(chunk_id: str) -> RetrievedChunk | None:
    """Used to prove a citation maps to a real, retrievable chunk (US-30
    DoD) — looks a chunk up directly by its stable id, independent of any
    query/ranking."""
    collection = _get_collection()
    result = collection.get(ids=[chunk_id])
    if not result["ids"]:
        return None
    return RetrievedChunk(
        chunk_id=result["ids"][0],
        source_document=result["metadatas"][0]["source_document"],
        section_reference=result["metadatas"][0]["section_reference"],
        text=result["documents"][0],
        distance=0.0,
    )
