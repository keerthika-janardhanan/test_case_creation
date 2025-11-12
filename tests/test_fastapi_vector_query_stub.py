from fastapi.testclient import TestClient
from pathlib import Path
from app.api.main import app


def test_vector_query_stub(monkeypatch, tmp_path: Path):
    # Stub client to avoid real Chroma access
    from app.api.routers import vector as vector_router

    class FakeClient:
        def __init__(self, path: str = "./vector_store") -> None:
            self.path = path
        def query(self, query: str, top_k: int = 3):  # type: ignore[no-untyped-def]
            return [
                {"id": "doc-1", "content": "alpha", "metadata": {"type": "note"}},
                {"id": "doc-2", "content": "beta", "metadata": {"type": "note"}},
            ][:top_k]
        def query_where(self, query: str, where: dict, top_k: int = 3):  # type: ignore[no-untyped-def]
            # Return only when where matches a simple key
            if where.get("type") == "refined":
                return [{"id": "doc-3", "content": "gamma", "metadata": {"type": "refined"}}]
            return []

    monkeypatch.setattr(vector_router, "VectorDBClient", FakeClient)

    client = TestClient(app)

    # Unfiltered
    r = client.post("/vector/query", json={"query": "hello", "topK": 2})
    assert r.status_code == 200, r.text
    data = r.json()
    assert len(data.get("results", [])) == 2

    # Filtered
    r2 = client.post("/vector/query", json={"query": "hello", "topK": 5, "where": {"type": "refined"}})
    assert r2.status_code == 200, r2.text
    data2 = r2.json()
    assert len(data2.get("results", [])) == 1
    assert data2["results"][0]["metadata"].get("type") == "refined"
