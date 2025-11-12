import json
from pathlib import Path

import pandas as pd
from fastapi.testclient import TestClient

from app.api.main import app
from app.services import refined_flow_service
from app.services.test_case_service import TestCaseGenerationError


client = TestClient(app)


def test_finalize_recorder_endpoint_not_found(tmp_path: Path) -> None:
    payload = {"sessionDir": str(tmp_path / "missing")}
    response = client.post("/api/refined-flows/finalize", json=payload)
    assert response.status_code == 404


def test_finalize_recorder_endpoint_success(tmp_path: Path, monkeypatch) -> None:
    session_dir = tmp_path / "session"
    session_dir.mkdir()
    metadata = {
        "options": {
            "captureDom": False,
            "captureScreenshots": False,
            "recordTrace": False,
            "recordHar": False,
        },
        "artifacts": {},
    }
    (session_dir / "metadata.json").write_text(json.dumps(metadata))

    monkeypatch.setattr(
        refined_flow_service,
        "auto_refine_and_ingest",
        lambda _path, _meta: {"refined_path": "refined.json", "ingest_stats": {}},
    )

    captured_events: list[tuple[str, dict]] = []

    async def fake_publish(session_id: str, message: dict) -> None:
        captured_events.append((session_id, message))

    monkeypatch.setattr("app.api.main.recorder_events.publish", fake_publish)

    response = client.post(
        "/api/refined-flows/finalize", json={"sessionDir": str(session_dir)}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["autoIngest"]["status"] == "success"
    assert data["autoIngest"]["result"]["refined_path"] == "refined.json"
    assert captured_events
    session_id, message = captured_events[0]
    assert session_id == "session"
    assert message["type"] == "finalized"


def test_generate_test_cases_endpoint_success(monkeypatch) -> None:
    def fake_generate(_story: str, llm_only: bool = False, template_df=None):
        return {
            "records": [{"id": 1, "title": "Example"}],
            "dataframe": pd.DataFrame([{"id": 1, "title": "Example"}]),
        }

    monkeypatch.setattr(
        "app.api.main.test_case_service.generate",
        fake_generate,
    )

    response = client.post(
        "/api/test-cases/generate",
        json={"story": "Create volunteering team", "llmOnly": False, "asExcel": True},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["records"][0]["title"] == "Example"
    assert data["excel"] is not None


def test_generate_test_cases_endpoint_validation(monkeypatch) -> None:
    def raise_error(*_args, **_kwargs):
        raise TestCaseGenerationError("Story text is required.")

    monkeypatch.setattr(
        "app.api.main.test_case_service.generate",
        raise_error,
    )

    response = client.post(
        "/api/test-cases/generate", json={"story": "", "llmOnly": False}
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Story text is required."


def test_publish_recorder_event_endpoint() -> None:
    response = client.post(
        "/api/recorder/demo/events",
        json={"message": "Recorder started", "level": "info"},
    )
    assert response.status_code == 202
    assert response.json()["status"] == "queued"

def test_create_recorder_session_job(tmp_path: Path, monkeypatch):
    recordings_dir = tmp_path / "recordings"
    recordings_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("app.tasks.RECORDINGS_DIR", recordings_dir)
    monkeypatch.setenv("RECORDER_OUTPUT_DIR", str(recordings_dir))

    class DummyEvents:
        def publish_from_thread(self, session_id: str, message: dict) -> None:
            pass

    monkeypatch.setattr("app.tasks.recorder_events", DummyEvents())
    monkeypatch.setattr(
        "app.tasks._run_recorder_subprocess",
        lambda cmd, session_dir, session_id=None, job_id=None: (0, "stdout", ""),
    )

    response = client.post(
        "/api/recorder/sessions",
        json={"url": "https://example.com", "flowName": "demo"},
    )
    assert response.status_code == 202
    data = response.json()
    assert "jobId" in data and "sessionId" in data
    job_response = client.get(f"/api/jobs/{data['jobId']}")
    assert job_response.status_code == 200
    job_detail = job_response.json()
    assert job_detail["status"] == "completed"
    assert job_detail["result"]["sessionId"] == data["sessionId"]
    assert job_detail["result"]["status"] == "completed"


def test_job_lookup_not_found():
    response = client.get("/api/jobs/nonexistent")
    assert response.status_code == 404


def test_download_recorder_artifact(tmp_path: Path, monkeypatch):
    from app.api.main import RECORDINGS_DIR

    session_dir = RECORDINGS_DIR / "testsession"
    session_dir.mkdir(parents=True, exist_ok=True)
    target = session_dir / "metadata.json"
    target.write_text("{}", encoding="utf-8")

    response = client.get("/api/recorder/testsession/artifacts/metadata.json")
    assert response.status_code == 200
    assert response.content == b"{}"


def test_ingest_jira_job(monkeypatch):
    monkeypatch.setattr("app.tasks.ingest_jira", lambda jql: [1, 2, 3])
    response = client.post("/api/ingest/jira", json={"jql": "project=TEST"})
    assert response.status_code == 202
    job_id = response.json()["jobId"]
    job = client.get(f"/api/jobs/{job_id}").json()
    assert job["status"] == "completed"
    assert job["result"]["ingested"] == 3


def test_ingest_website_job(monkeypatch):
    monkeypatch.setattr("app.tasks.ingest_web_site", lambda url, depth: [1])
    response = client.post("/api/ingest/website", json={"url": "https://example.com", "maxDepth": 1})
    assert response.status_code == 202
    job_id = response.json()["jobId"]
    job = client.get(f"/api/jobs/{job_id}").json()
    assert job["status"] == "completed"


def test_ingest_documents_job(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("app.tasks.ingest_document", lambda path: None)
    files = [("files", ("sample.txt", b"hello", "text/plain"))]
    response = client.post("/api/ingest/documents", files=files)
    assert response.status_code == 202
    job_id = response.json()["jobId"]
    job = client.get(f"/api/jobs/{job_id}").json()
    assert job["status"] == "completed"
    assert job["result"]["ingested"] == 1


def test_vector_delete_jobs(monkeypatch):
    monkeypatch.setattr("app.tasks.VectorDBClient.delete_document", lambda self, doc_id: None)
    monkeypatch.setattr("app.tasks.VectorDBClient.delete_by_source", lambda self, source: None)
    response = client.delete("/api/vector/docs/sample-id")
    assert response.status_code == 202
    job_id = response.json()["jobId"]
    assert client.get(f"/api/jobs/{job_id}").json()["status"] == "completed"

    response = client.delete("/api/vector/docs", params={"source": "jira"})
    assert response.status_code == 202
    job_id = response.json()["jobId"]
    assert client.get(f"/api/jobs/{job_id}").json()["status"] == "completed"


def test_agentic_trial_run_endpoint(monkeypatch):
    # Monkeypatch executor.run_trial to avoid invoking real Playwright
    def fake_run_trial(script: str, headed: bool = True):
        # Return success when headed True and script contains something
        return (bool(headed) and bool(script.strip())), "LOGS"

    monkeypatch.setattr("app.executor.run_trial", fake_run_trial)

    payload = {
        "testFileContent": "import { test } from '@playwright/test'; test('demo', async () => {});",
        "headed": True,
    }
    response = client.post("/agentic/trial-run", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "success" in data and "logs" in data
    assert data["success"] is True


def test_agentic_keyword_inspect_endpoint(monkeypatch, tmp_path: Path):
    # Create a fake repo with a tests file
    repo_root = tmp_path / "repo"
    (repo_root / "tests").mkdir(parents=True, exist_ok=True)
    test_file = repo_root / "tests" / "create_supplier.spec.ts"
    test_file.write_text("test('Create Supplier', async () => { /* ... */ })\n", encoding="utf-8")

    # Monkeypatch AgenticScriptAgent behaviors
    class DummyAgent:
        def find_existing_framework_assets(self, keyword, framework, top_k=5):
            return [{"path": test_file, "metadata": {"relevance_score": 10}}]

        def gather_context(self, keyword):
            return {"vector_steps": [
                {"step": 1, "action": "Click", "navigation": "Suppliers", "data": "", "expected": "Opened"}
            ], "flow_available": True}

    monkeypatch.setattr("app.api.routers.agentic.AgenticScriptAgent", DummyAgent)

    payload = {
        "keyword": "Create Supplier",
        "repoPath": str(repo_root),
        "branch": "main",
        "maxAssets": 3,
    }
    response = client.post("/agentic/keyword-inspect", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["keyword"] == "Create Supplier"
    assert data["existingAssets"] and data["existingAssets"][0]["path"].endswith("create_supplier.spec.ts")
    assert data["vectorContext"]["flowAvailable"] is True
    assert data["status"] in {"found-existing", "found-refined-only"}

