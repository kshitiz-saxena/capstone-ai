from app.main import app
from app.api.routes import get_rag_service
from app.services.rag_service import RAGService
from app.services.vector_db_client import VectorDBClient
from fastapi.testclient import TestClient


class FakeVectorDBClient:
    def search(self, query, collection=None, top_k=5, filters=None):
        return [
            {
                "id": "doc-1",
                "content": "Retrieval-Augmented Generation combines search and generation to answer questions using relevant documents.",
                "score": 0.98,
                "metadata": {"source": "knowledge-base"},
            }
        ]


class FakeAnswerGenerator:
    def generate(self, query, documents):
        return f"Using the retrieved context, the answer is: {documents[0]['content']}"


app.dependency_overrides[get_rag_service] = lambda: RAGService(
    vector_db_client=FakeVectorDBClient(),
    answer_generator=FakeAnswerGenerator(),
)

client = TestClient(app)


def test_health_endpoint():
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_query_endpoint():
    response = client.post(
        "/api/v1/query",
        json={"query": "What is RAG?", "top_k": 2},
    )

    assert response.status_code == 200
    payload = response.json()
    assert "RAG" in payload["answer"] or "retrieved context" in payload["answer"]
    assert len(payload["sources"]) == 1


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

    client = VectorDBClient(default_collection="hs_code_rag")
    monkeypatch.setattr(client, "_chroma_client", FakeChromaClient())
    monkeypatch.setattr(client, "_get_embedding_model", lambda: FakeEmbeddingModel())

    documents = client.search("polo horses")

    assert documents[0]["id"] == "item-1"
    assert documents[0]["content"] == "Horses for polo"
