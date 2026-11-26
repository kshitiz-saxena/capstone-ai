from __future__ import annotations

import chromadb

from typing import Any
from urllib.parse import urlparse

from app.config import DEFAULT_COLLECTION, EMBEDDING_MODEL_NAME, VECTOR_DB_BASE_URL
from app.core.errors import VectorDBConnectionError

from sentence_transformers import SentenceTransformer

DEFAULT_CONTENT_FILTER: dict[str, Any] = {
    "type": {"$in": ["text", "table"]}
}


class VectorDBClient:
    """Query Chroma using the same embedding model that indexed the collection."""
    def __init__(
        self,
        base_url: str = VECTOR_DB_BASE_URL,
        default_collection: str | None = DEFAULT_COLLECTION,
        embedding_model_name: str = EMBEDDING_MODEL_NAME,
        timeout: float = 10.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.default_collection = default_collection
        self.embedding_model_name = embedding_model_name
        self.timeout = timeout
        self._chroma_client = self._create_chroma_client()
        self._embedding_model: Any | None = None

    def search(
        self,
        query: str,
        collection: str | None = None,
        top_k: int = 5,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        target_collection = collection or self.default_collection
        if not target_collection:
            raise VectorDBConnectionError("No Chroma collection was configured.")
        if self._chroma_client is None:
            raise VectorDBConnectionError("ChromaDB client is unavailable.")

        query_embedding = self._embed_query(query)
        resolved_filters = filters if filters is not None else DEFAULT_CONTENT_FILTER.copy()

        try:
            collection_handle = self._chroma_client.get_collection(target_collection)
            results = collection_handle.query(
                query_embeddings=[query_embedding],
                n_results=min(top_k, 10),
                include=["documents", "metadatas", "distances"],
                where=resolved_filters,
            )
        except Exception as exc:
            raise VectorDBConnectionError(
                f"Unable to query Chroma collection '{target_collection}': {exc}"
            ) from exc

        return self._normalize_chroma_response(results)

    def _embed_query(self, query: str) -> list[float]:
        model = self._get_embedding_model()
        try:
            embedding = model.encode(query, show_progress_bar=False)
            return embedding.tolist() if hasattr(embedding, "tolist") else list(embedding)
        except Exception as exc:
            raise VectorDBConnectionError(
                f"Unable to embed query with '{self.embedding_model_name}': {exc}"
            ) from exc

    def _get_embedding_model(self) -> Any:
        if self._embedding_model is not None:
            return self._embedding_model

        try:
            self._embedding_model = SentenceTransformer(self.embedding_model_name)
        except Exception as exc:
            raise VectorDBConnectionError(
                f"Unable to load embedding model '{self.embedding_model_name}': {exc}"
            ) from exc

        return self._embedding_model

    def _create_chroma_client(self) -> Any | None:
        if chromadb is None:
            return None

        try:
            parsed = urlparse(self.base_url)
            return chromadb.HttpClient(
                host=parsed.hostname or "localhost",
                port=parsed.port or (443 if parsed.scheme == "https" else 8000),
                ssl=parsed.scheme == "https",
                tenant="default_tenant",
                database="default_database",
            )
        except Exception:
            return None

    def _normalize_chroma_response(
        self, data: dict[str, Any]
    ) -> list[dict[str, Any]]:
        documents = data.get("documents") or []
        metadatas = data.get("metadatas") or []
        distances = data.get("distances") or []
        ids = data.get("ids") or []

        normalized: list[dict[str, Any]] = []
        for batch_index, batch_documents in enumerate(documents):
            batch_metadata = metadatas[batch_index] if batch_index < len(metadatas) else []
            batch_distances = distances[batch_index] if batch_index < len(distances) else []
            batch_ids = ids[batch_index] if batch_index < len(ids) else []

            for item_index, content in enumerate(batch_documents):
                metadata = batch_metadata[item_index] if item_index < len(batch_metadata) else {}
                doc_id = batch_ids[item_index] if item_index < len(batch_ids) else None
                distance = batch_distances[item_index] if item_index < len(batch_distances) else None
                normalized.append(
                    {
                        "id": doc_id,
                        "content": content,
                        "score": (
                            None
                            if distance is None
                            else max(0.0, 1.0 - float(distance))
                        ),
                        "metadata": metadata,
                    }
                )

        return normalized
