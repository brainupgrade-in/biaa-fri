"""Vector store for document embeddings and retrieval."""

from __future__ import annotations

import os
from typing import Optional

import chromadb
from chromadb.config import Settings

from backend.config import settings as app_settings


class VectorStore:
    """ChromaDB vector store for document chunks."""

    def __init__(self, host: str = "localhost", port: int = 8000):
        self.host = host
        self.port = port
        self._client: Optional[chromadb.Client] = None
        self._collection = None
        self._use_embedded = os.getenv("CHROMA_EMBEDDED", "true").lower() == "true"

    def _get_client(self) -> chromadb.Client:
        if self._client is None:
            if self._use_embedded:
                # Use embedded client for development
                self._client = chromadb.PersistentClient(
                    path=app_settings.chroma_persist_dir,
                    settings=Settings(anonymized_telemetry=False),
                )
            else:
                self._client = chromadb.HttpClient(
                    host=self.host,
                    port=self.port,
                    settings=Settings(anonymized_telemetry=False),
                )
        return self._client

    def _get_collection(self):
        if self._collection is None:
            client = self._get_client()
            self._collection = client.get_or_create_collection(
                name="financial_documents",
                metadata={"hnsw:space": "cosine"},
            )
        return self._collection

    def add_chunks(self, doc_id: str, chunks: list[dict]) -> list[str]:
        """Add document chunks to vector store."""
        collection = self._get_collection()

        ids = []
        documents = []
        metadatas = []

        for i, chunk in enumerate(chunks):
            chunk_id = f"{doc_id}_chunk_{i}"
            ids.append(chunk_id)
            documents.append(chunk["content"])
            metadatas.append({
                "doc_id": doc_id,
                "page": chunk.get("page", 1),
                "section": chunk.get("section", "General"),
                "chunk_index": i,
            })

        collection.add(
            ids=ids,
            documents=documents,
            metadatas=metadatas,
        )

        return ids

    def query(self, query_text: str, n_results: int = 5, doc_id: str = None) -> dict:
        """Query vector store for relevant chunks."""
        collection = self._get_collection()

        where_filter = {"doc_id": doc_id} if doc_id else None

        results = collection.query(
            query_texts=[query_text],
            n_results=n_results,
            where=where_filter,
        )

        return results

    def delete_document(self, doc_id: str) -> None:
        """Delete all chunks for a document."""
        collection = self._get_collection()
        collection.delete(where={"doc_id": doc_id})

    def get_document_chunks(self, doc_id: str) -> dict:
        """Get all chunks for a document."""
        collection = self._get_collection()
        results = collection.get(where={"doc_id": doc_id})
        return results


# Global instance
vector_store = VectorStore()