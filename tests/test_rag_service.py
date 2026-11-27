from fastapi.testclient import TestClient

from app.api.routes import get_integrated_rag_agent, get_rag_service
from app.main import app
from app.services.rag_service import RAGService
from app.services.vector_db_client import VectorDBClient


class FakeVectorDBClient:
    def search(self, query, collection=None, top_k=5, filters=None):
        return [
            {
                "id": "doc-1",
                "content": "RAG combines retrieval and generation to answer with grounded context.",
                "score": 0.98,
                "metadata": {"type": "text", "section": "A", "chapter": "1"},
            }
        ]


class FakeAnswerGenerator:
    def generate(self, query, context):
        return f"Answer for '{query}' based on context: {context}"


class FakeIntegratedRAGAgent:
    def process_message(self, session_id, message, file_paths=None):
        return {"reply": f"stateful-reply::{session_id}::{message}"}


def _override_rag_service():
    return RAGService(
        vector_db_client=FakeVectorDBClient(),
        answer_generator=FakeAnswerGenerator(),
    )


def _override_integrated_agent():
    return FakeIntegratedRAGAgent()


app.dependency_overrides[get_rag_service] = _override_rag_service
app.dependency_overrides[get_integrated_rag_agent] = _override_integrated_agent
client = TestClient(app)


def test_health_endpoint():
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_query_endpoint_without_session_id_uses_standard_rag():
    response = client.post(
        "/api/v1/query",
        json={"query": "What is RAG?"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["query"] == "What is RAG?"
    assert "Answer for 'What is RAG?'" in payload["answer"]


def test_query_endpoint_with_session_id_uses_stateful_agent():
    response = client.post(
        "/api/v1/query",
        json={"query": "Classify this valve", "session_id": "thread-123"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["query"] == "Classify this valve"
    assert payload["answer"] == "stateful-reply::thread-123::Classify this valve"


def test_vector_db_client_queries_with_embedding(monkeypatch):
    class FakeEmbeddingModel:
        def encode(self, query, show_progress_bar=False):
            assert query == "polo horses"
            return [0.1, 0.2]

    class FakeCollection:
        def query(self, **kwargs):
            assert kwargs["query_embeddings"] == [[0.1, 0.2]]
            assert "query_texts" not in kwargs
            return {
                "documents": [["Horses for polo"]],
                "metadatas": [[{"type": "text"}]],
                "distances": [[0.1]],
                "ids": [["item-1"]],
            }

    class FakeChromaClient:
        def get_collection(self, name):
            assert name == "hs_code_rag"
            return FakeCollection()

    vector_client = VectorDBClient(default_collection="hs_code_rag")
    monkeypatch.setattr(vector_client, "_chroma_client", FakeChromaClient())
    monkeypatch.setattr(vector_client, "_get_embedding_model", lambda: FakeEmbeddingModel())

    documents = vector_client.search("polo horses")

    assert documents[0]["id"] == "item-1"
    assert documents[0]["content"] == "Horses for polo"
