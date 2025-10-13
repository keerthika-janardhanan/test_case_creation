# vector_db.py
import argparse
import json

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
        documents = results["documents"][0]
        ids = results.get("ids", [[None] * len(documents)])[0]
        metadatas = results.get("metadatas", [[{}] * len(documents)])[0]
        return [
            {
                "id": ids[i],
                "content": documents[i],
                "metadata": metadatas[i] if i < len(metadatas) else {},
            }
            for i in range(len(documents))
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


def _cli_query(client: VectorDBClient, args: argparse.Namespace) -> int:
    results = client.query(args.query, top_k=args.top_k)
    print(json.dumps({"results": results}, ensure_ascii=False))
    return 0


def _cli_add(client: VectorDBClient, args: argparse.Namespace) -> int:
    if not args.content:
        raise ValueError("Content is required when adding a document to the vector DB.")
    metadata = json.loads(args.metadata or "{}")
    client.add_document(args.source, args.doc_id, args.content, metadata)
    print(json.dumps({"status": "ok"}))
    return 0


def _cli_list(client: VectorDBClient, args: argparse.Namespace) -> int:
    records = client.list_all(limit=args.limit)
    print(json.dumps({"results": records}, ensure_ascii=False))
    return 0


def _cli_delete(client: VectorDBClient, args: argparse.Namespace) -> int:
    if args.doc_id:
        client.delete_document(args.doc_id)
    elif args.source:
        client.delete_by_source(args.source)
    else:
        raise ValueError("Either --doc-id or --source must be provided for delete.")
    print(json.dumps({"status": "ok"}))
    return 0


def main_cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Vector DB command line interface.")
    parser.add_argument("--path", default=os.getenv("VECTOR_DB_PATH", "./vector_store"), help="Path to vector DB.")

    subparsers = parser.add_subparsers(dest="command", required=True)

    query_parser = subparsers.add_parser("query", help="Query similar documents.")
    query_parser.add_argument("query", help="Natural language query string.")
    query_parser.add_argument("--top-k", type=int, default=3, help="Number of results to return.")

    add_parser = subparsers.add_parser("add", help="Add a new document.")
    add_parser.add_argument("source", help="Source prefix for the document.")
    add_parser.add_argument("doc_id", help="Document identifier.")
    add_parser.add_argument("content", help="Document content.")
    add_parser.add_argument("--metadata", help="JSON encoded metadata.")

    list_parser = subparsers.add_parser("list", help="List documents for inspection.")
    list_parser.add_argument("--limit", type=int, default=20, help="Limit number of documents.")

    delete_parser = subparsers.add_parser("delete", help="Delete documents.")
    delete_parser.add_argument("--doc-id", help="Specific document ID.")
    delete_parser.add_argument("--source", help="Source prefix.")

    args = parser.parse_args(argv)
    client = VectorDBClient(path=args.path)

    if args.command == "query":
        return _cli_query(client, args)
    if args.command == "add":
        return _cli_add(client, args)
    if args.command == "list":
        return _cli_list(client, args)
    if args.command == "delete":
        return _cli_delete(client, args)
    parser.error("Unknown command")
    return 1


if __name__ == "__main__":
    try:
        raise SystemExit(main_cli())
    except Exception as exc:
        print(json.dumps({"error": str(exc)}))
        raise SystemExit(1)
