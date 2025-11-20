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
        # Ensure source is included in metadata
        metadata_with_source = {**metadata, "source": source}
        self.collection.add(
            documents=[content],
            metadatas=[metadata_with_source],
            ids=[f"{source}-{doc_id}"]
        )

    # ---------------- Query ----------------
    def query(self, query: str, top_k: int = 3):
        results = self.collection.query(query_texts=[query], n_results=top_k)
        if not results or "documents" not in results:
            return []
        documents = results["documents"][0] if isinstance(results.get("documents"), list) else results.get("documents")
        if isinstance(documents, list):
            docs_list = documents
        else:
            docs_list = [documents] if documents is not None else []
        ids_raw = results.get("ids") or []
        ids = ids_raw[0] if ids_raw and isinstance(ids_raw[0], list) else (ids_raw if isinstance(ids_raw, list) else [])
        metas_raw = results.get("metadatas") or []
        metadatas = metas_raw[0] if metas_raw and isinstance(metas_raw[0], list) else (metas_raw if isinstance(metas_raw, list) else [])
        out = []
        n = len(docs_list)
        for i in range(n):
            meta = metadatas[i] if i < len(metadatas) else {}
            if not isinstance(meta, dict):
                try:
                    meta = json.loads(meta) if isinstance(meta, str) else {}
                except Exception:
                    meta = {}
            out.append({
                "id": ids[i] if i < len(ids) else None,
                "content": docs_list[i],
                "metadata": meta,
            })
        return out

    # ---------------- Query with metadata filter ----------------
    def query_where(self, query: str, where: dict, top_k: int = 3):
        """Query with a Chroma metadata filter (e.g., {"type":"recorder_refined","flow_hash":"abc123"})."""
        server_filtered = True
        try:
            results = self.collection.query(query_texts=[query], where=where or {}, n_results=top_k)
        except TypeError:
            # Older Chroma may not support where in this signature; fallback to unfiltered
            results = self.collection.query(query_texts=[query], n_results=top_k)
            server_filtered = False
        if not results or "documents" not in results:
            return []
        documents = results["documents"][0] if isinstance(results.get("documents"), list) else results.get("documents")
        docs_list = documents if isinstance(documents, list) else ([documents] if documents is not None else [])
        ids_raw = results.get("ids") or []
        ids = ids_raw[0] if ids_raw and isinstance(ids_raw[0], list) else (ids_raw if isinstance(ids_raw, list) else [])
        metas_raw = results.get("metadatas") or []
        metadatas = metas_raw[0] if metas_raw and isinstance(metas_raw[0], list) else (metas_raw if isinstance(metas_raw, list) else [])
        out = []
        n = len(docs_list)
        for i in range(n):
            meta = metadatas[i] if i < len(metadatas) else {}
            if not isinstance(meta, dict):
                try:
                    meta = json.loads(meta) if isinstance(meta, str) else {}
                except Exception:
                    meta = {}
            out.append({
                "id": ids[i] if i < len(ids) else None,
                "content": docs_list[i],
                "metadata": meta,
            })
        # Apply client-side filtering as a safeguard when server-side 'where' wasn't applied,
        # or to double-check equality matches.
        if where:
            def _match(meta: dict) -> bool:
                try:
                    for k, v in (where or {}).items():
                        if (meta or {}).get(k) != v:
                            return False
                    return True
                except Exception:
                    return False
            # If server didn't filter, or if any mismatches exist, enforce client-side filter
            if (not server_filtered) or any(not _match(item.get("metadata", {})) for item in out):
                out = [item for item in out if _match(item.get("metadata", {}))]
        return out

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

    # ---------------- Get by metadata filter ----------------
    def get_where(self, where: dict, limit: int = 1000):
        """Return all documents matching a metadata filter, up to limit. Preserves original order returned by Chroma.
        Example where: {"type": "recorder_refined", "flow_hash": "abc123"}
        """
        try:
            results = self.collection.get(where=where or {}, limit=limit)
        except (TypeError, ValueError):
            # Older client may not support where in get; fallback to list_all and filter client-side
            all_docs = self.list_all(limit=limit)
            def _match(meta: dict) -> bool:
                for k, v in (where or {}).items():
                    if (meta or {}).get(k) != v:
                        return False
                return True
            return [d for d in all_docs if _match(d.get("metadata", {}))]
        docs = []

        def _flatten(field):
            if field is None:
                return []
            if isinstance(field, list):
                if field and isinstance(field[0], list):
                    return field[0]
                return field
            return []

        documents = _flatten(results.get("documents"))
        metadatas = _flatten(results.get("metadatas"))
        ids = _flatten(results.get("ids"))

        max_len = len(documents)
        if not documents and isinstance(results.get("documents"), list) and results.get("documents"):
            # Chroma may return list of strings embedded in JSON; ensure iteration
            documents = list(results.get("documents"))
            max_len = len(documents)

        for i in range(max_len):
            doc = documents[i] if i < len(documents) else None
            meta = metadatas[i] if i < len(metadatas) else {}
            doc_id = ids[i] if i < len(ids) else None
            docs.append({
                "id": doc_id,
                "content": doc,
                "metadata": meta if isinstance(meta, dict) else {},
            })
        return docs

    # ---------------- List by metadata filter ----------------
    def list_where(self, where: dict, limit: int = 1000):
        """Compatibility wrapper preferred by agentic components; delegates to get_where."""
        return self.get_where(where=where, limit=limit)


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
