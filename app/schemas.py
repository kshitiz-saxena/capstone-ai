from typing import Any

from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    query: str = Field(..., min_length=1)
    filters: dict[str, Any] | None = None


class SourceDocument(BaseModel):
    id: str | None = None
    content: str | None = None
    score: float | None = None
    metadata: dict[str, Any] | None = None


class QueryResponse(BaseModel):
    answer: str
    query: str
