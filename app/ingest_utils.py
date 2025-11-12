# app/ingest_utils.py
import json

try:
    # Prefer package-relative imports when available
    from .vector_db import VectorDBClient  # type: ignore
    from .hashstore import compute_hash, is_changed  # type: ignore
except ImportError:  # pragma: no cover - fallback for direct script usage
    from app.vector_db import VectorDBClient
    from hashstore import compute_hash, is_changed

db = VectorDBClient()

def ingest_artifact(source_type: str, content_obj: dict, metadata: dict, provided_id: str = None):
    """
    Generic ingestion helper. Handles hashing, deduplication, and storage in VectorDB.
    """
    if isinstance(content_obj, str):
        content_str = content_obj
    else:
        try:
            content_str = json.dumps(content_obj, ensure_ascii=False)
        except TypeError:
            # Fallback to string representation if not JSON serialisable
            content_str = str(content_obj)

    # Use provided_id if available, else derive from hash
    doc_id = provided_id or compute_hash(content_str)

    if not is_changed(doc_id, content_str):
        return {"id": doc_id, "status": "skipped"}

    db.add_document(source_type, doc_id, content_str, metadata)
    return {"id": doc_id, "status": "updated"}
