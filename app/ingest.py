import json
import os
from app.sources.jira import fetch_jira_issues
from app.sources.documents import load_documents
from app.sources.ui_crawl import load_ui_crawl
from app.vector_db import VectorDBClient
from app.ingest_utils import ingest_artifact
from app.utils import clean_metadata
from app.metadata_utils import prepare_artifact_and_metadata_for_ingest
from fastapi import FastAPI, Request
from app.parse_playwright import parse_playwright_code


db = VectorDBClient()
jql_query = "project=TEST ORDER BY created DESC"

# app = FastAPI()
# db = VectorDBClient()

JSON_FLOW_DIR = r"./app/saved_flows"
os.makedirs(JSON_FLOW_DIR, exist_ok=True)

def ingest_playwright_flow(code: str, flow_name: str, db_client: VectorDBClient):
    """
    Parse TS code → convert to JSON → add metadata → ingest into Vector DB.
    """
    # Parse TS code
    steps = parse_playwright_code(code)

    # Build artifact JSON
    artifact = {
        "flow_name": flow_name,
        "source": "playwright",
        "steps": steps
    }

    # Save JSON locally
    json_path = os.path.join(JSON_FLOW_DIR, f"{flow_name}.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(artifact, f, indent=4)

    print(f"✅ Flow '{flow_name}' saved locally at {json_path}")
    return None, json_path



def ingest_jira(jql_query):
    stories = fetch_jira_issues(jql_query)
    results = []
    for story in stories:
        key = story.get("key")
        fields = story.get("fields", {})
        summary = fields.get("summary", "")
        description = fields.get("description", "")
        issue_type = fields.get("issuetype", {}).get("name", "Unknown")
        project_key = fields.get("project", {}).get("key", "Unknown")
        metadata = clean_metadata({
            "source": "jira",
            "issue_key": key,
            "type": issue_type,
            "project": project_key
        })
        content = f"{summary}\n{description}"
        ingest_artifact("jira", {"id": key, "content": content}, metadata, provided_id=key)
        results.append(key)
    return results

def ingest_web_site(base_url: str, max_depth: int = 1, max_pages: int = 50):
    docs = []
    for doc_id, content, metadata in load_documents(
        base_url,
        crawl_depth=max_depth,
        max_pages=max_pages
    ):
        # ✅ Add artifact type + source
        metadata.update({
            "artifact_type": "website_doc",
            "source": "website",
            "url": base_url,
        })

        db.add_document(
            source="website",
            doc_id=doc_id,
            content=content,
            metadata=metadata
        )
        docs.append({"id": doc_id, "content": content, "metadata": metadata})

    return docs

def flatten_metadata(meta: dict) -> dict:
    """Flatten metadata and remove None values so Chroma accepts them."""
    flat = {}
    for k, v in meta.items():
        if v is None:
            # Option 1: skip it
            continue
            # Option 2: convert to string
            # flat[k] = "None"
        elif isinstance(v, (dict, list)):
            flat[k] = json.dumps(v, ensure_ascii=False)
        else:
            flat[k] = v
    return flat


def ingest_document(file_path: str):
    docs = []
    for doc_id, chunk, metadata in load_documents(file_path):
        artifact, meta, new_doc_id = prepare_artifact_and_metadata_for_ingest(chunk, metadata)
        final_doc_id = new_doc_id if new_doc_id else doc_id

        safe_meta = flatten_metadata(meta)

        db.add_document(
            source="document",
            doc_id=final_doc_id,
            content=json.dumps(artifact, ensure_ascii=False),
            metadata=safe_meta
        )

        docs.append((final_doc_id, chunk))
    return docs

def ingest_ui_crawl(path: str):
    data = load_ui_crawl(path)
    results = []
    for entry in data:
        metadata = {"type": "ui", "flow": entry["flow"]}
        ingest_artifact("ui_crawl", entry, metadata, provided_id=entry["id"])
        results.append(entry["id"])
    return results

