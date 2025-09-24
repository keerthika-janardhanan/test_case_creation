# app/ingest_utils.py
from vector_db import VectorDBClient
from hashstore import compute_hash, is_changed

db = VectorDBClient()

def ingest_artifact(source_type: str, content_obj: dict, metadata: dict, provided_id: str = None):
    """
    Generic ingestion helper. Handles hashing, deduplication, and storage in VectorDB.
    """
    # Use provided_id if available, else derive from hash
    doc_id = provided_id or compute_hash(str(content_obj))
    content_str = str(content_obj)

    if not is_changed(doc_id, content_str):
        return {"id": doc_id, "status": "skipped"}

    db.add_document(source_type, doc_id, content_str, metadata)
    return {"id": doc_id, "status": "updated"}
