from __future__ import annotations

from typing import Any

from app.config import DEFAULT_COLLECTION
from app.schemas import QueryResponse, SourceDocument
from app.services.answer_generator import AnswerGenerator
from app.services.vector_db_client import VectorDBClient


class RAGService:
    """Orchestrates vector search and answer generation."""

    def __init__(
        self,
        vector_db_client: VectorDBClient | None = None,
        answer_generator: AnswerGenerator | None = None,
    ) -> None:
        self.vector_db_client = vector_db_client or VectorDBClient(default_collection=DEFAULT_COLLECTION)
        self.answer_generator = answer_generator or AnswerGenerator()

    def answer_query(
        self,
        query: str,
        filters: dict[str, Any] | None = None,
    ) -> QueryResponse:
        chunks = self.vector_db_client.search(
            query=query,
            collection=DEFAULT_COLLECTION,
            top_k=5,
            filters=filters,
        )
        
        context = self._create_context(chunks)
        
        print("Created context:", context)

        answer = self.answer_generator.generate(query, context)
        source_documents = [
            SourceDocument(
                id=document.get("id"),
                content=document.get("content"),
                score=document.get("score"),
                metadata=document.get("metadata"),
            )
            for document in chunks
        ]

        resolved_collection = DEFAULT_COLLECTION or getattr(self.vector_db_client, "default_collection", None)
        return QueryResponse(
            answer=answer,
            query=query
        )
        
    def _create_context(self, chunks: list[dict[str, Any]]) -> str:
        parts = []
        for i, c in enumerate(chunks, 1):
            m = c['metadata']
            label = (
                f'[{i}] [{m["type"].upper()} | section {m["section"]} | chapter {m["chapter"]} | '
                f'score {c["score"]}]'
            )
            parts.append(f'{label}\n{c["content"]}')
        return '\n\n'.join(parts)