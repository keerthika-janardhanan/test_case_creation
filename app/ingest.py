import json
import os
from sources.jira import fetch_jira_issues
from sources.documents import load_documents
from sources.ui_crawl import load_ui_crawl
from vector_db import VectorDBClient
from ingest_utils import ingest_artifact
from utils import clean_metadata
from metadata_utils import prepare_artifact_and_metadata_for_ingest
from fastapi import FastAPI, Request
from parse_playwright import parse_playwright_code


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

    # Build metadata for Vector DB
    metadata = {
        "artifact_type": "ui_flow",
        "source": "playwright-recorder",
        "flow_name": flow_name,
        "steps_count": len(steps)
    }

    # Unique ID for the flow
    doc_id = f"playwright_{abs(hash(flow_name))}"

    # Ingest into Vector DB
    db_client.add_document(
        source="ui_flow",
        doc_id=doc_id,
        content=json.dumps(artifact),
        metadata=metadata
    )

    print(f"✅ Flow '{flow_name}' ingested successfully (doc_id={doc_id})")
    return doc_id, json_path



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

def ingest_ui_crawl(path: str):
    data = load_ui_crawl(path)
    results = []
    for entry in data:
        metadata = {"type": "ui", "flow": entry["flow"]}
        ingest_artifact("ui_crawl", entry, metadata, provided_id=entry["id"])
        results.append(entry["id"])
    return results

