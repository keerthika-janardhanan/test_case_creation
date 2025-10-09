# ingest_scaffold.py
import json
from vector_db import VectorDBClient
from ingest_utils import ingest_artifact

db = VectorDBClient(path="./vector_store")

with open("./parsed_repo_scaffold.json", "r", encoding="utf-8") as f:
    scaffold = json.load(f)

for file_data in scaffold:
    doc_id = f"ts_scaffold_{file_data['filePath'].replace('/', '_')}"
    metadata = {
        "type": "script_scaffold",
        "source": "repo",
        "file_path": file_data["filePath"]
    }
    ingest_artifact("script_scaffold", file_data, metadata, provided_id=doc_id)

print(f"✅ Ingested {len(scaffold)} TS files into Vector DB")
