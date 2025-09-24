import pytest
from app.vector_db import VectorDBClient
from app.hashstore import HashStore

class DummyVectorDB(VectorDBClient):
    def __init__(self):
        self.data = []

    def ingest(self, content, metadata):
        self.data.append({"content": content, "metadata": metadata})

def test_idempotent_ingestion(tmp_path):
    store = HashStore(str(tmp_path / "hashes.json"))
    vdb = DummyVectorDB()

    content = {"flow": "login"}
    metadata = {"source": "recorder"}

    if store.is_new(content):
        vdb.ingest(content, metadata)
        store.add(content)

    # Try ingesting same content again
    if store.is_new(content):
        vdb.ingest(content, metadata)
        store.add(content)

    assert len(vdb.data) == 1
