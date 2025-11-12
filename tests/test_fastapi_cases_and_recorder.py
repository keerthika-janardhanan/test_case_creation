import json
import os
from pathlib import Path

from fastapi.testclient import TestClient

from app.api.main import app


def test_cases_generate_stub(monkeypatch, tmp_path: Path):
    os.environ["FRAMEWORK_REPO_ROOT"] = str(tmp_path)
    from app.api.routers import cases as cases_router

    class FakeService:
        def generate(self, story: str, llm_only: bool = False):  # type: ignore[no-untyped-def]
            return {
                "records": [
                    {"type": "positive", "steps": ["Step A", "Step B"], "expected": "OK"}
                ]
            }

    monkeypatch.setattr(cases_router, "TestCaseService", lambda: FakeService())

    client = TestClient(app)
    r = client.post("/cases/generate", json={"story": "Create Supplier", "llmOnly": False})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("cases") and data["cases"][0]["type"] == "positive"


def test_recorder_status_from_metadata(tmp_path: Path, monkeypatch):
    # Simulate a recording dir with metadata.json to yield 'stopped'
    base = tmp_path / "recordings"
    session = base / "sess1"
    session.mkdir(parents=True)
    (session / "dom").mkdir()
    (session / "screenshots").mkdir()
    meta = {"artifacts": {"har": "network.har", "trace": "trace.zip"}, "options": {}}
    (session / "metadata.json").write_text(json.dumps(meta), encoding="utf-8")
    monkeypatch.setenv("RECORDER_OUTPUT_DIR", str(base))

    client = TestClient(app)
    r = client.get("/recorder/status/sess1")
    assert r.status_code == 200, r.text
    payload = r.json()
    assert payload.get("status") == "stopped"
    assert "artifacts" in payload