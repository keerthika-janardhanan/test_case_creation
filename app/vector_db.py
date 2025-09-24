# vector_db.py
import chromadb
from chromadb.utils import embedding_functions
import os

class VectorDBClient:
    def __init__(self, path: str = "./vector_store"):
        self.client = chromadb.PersistentClient(path=path)
        self.collection = self.client.get_or_create_collection(
            name="gen_ai",
            embedding_function=embedding_functions.DefaultEmbeddingFunction()
        )

    # ---------------- Add ----------------
    def add_document(self, source: str, doc_id: str, content: str, metadata: dict):
        self.collection.add(
            documents=[content],
            metadatas=[metadata],
            ids=[f"{source}-{doc_id}"]
        )

    # ---------------- Query ----------------
    def query(self, query: str, top_k: int = 3):
        results = self.collection.query(query_texts=[query], n_results=top_k)
        if not results or "documents" not in results:
            return []
        return [
            {"id": results["ids"][0][i], "content": results["documents"][0][i]}
            for i in range(len(results["documents"][0]))
        ]

    # ---------------- Count ----------------
    def count(self) -> int:
        try:
            # Chroma v0.4+ does not have get_collection_stats; fallback to counting all docs
            results = self.list_all(limit=10000)
            return len(results)
        except Exception:
            return 0

    # ---------------- List all ----------------
    def list_all(self, limit: int = 20):
        """Return up to `limit` documents with metadata for inspection."""
        # Query with empty string to fetch all
        results = self.collection.query(query_texts=[""], n_results=limit)
        docs = []
        for i, doc in enumerate(results["documents"][0]):
            docs.append({
                "id": results["ids"][0][i],
                "content": doc,
                "metadata": results["metadatas"][0][i] if "metadatas" in results else {}
            })
        return docs

    # ---------------- Delete by ID ----------------
    def delete_document(self, doc_id: str):
        """Delete a single document by ID."""
        self.collection.delete(ids=[doc_id])

    # ---------------- Delete by source ----------------
    def delete_by_source(self, source: str):
        """Delete all documents with the given source prefix."""
        all_docs = self.list_all(limit=10000)
        ids_to_delete = [d["id"] for d in all_docs if d["id"].startswith(f"{source}-")]
        if ids_to_delete:
            self.collection.delete(ids=ids_to_delete)
