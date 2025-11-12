from pathlib import Path
from fastapi.testclient import TestClient
import os

from app.api.main import app


def test_healthz_ok():
    client = TestClient(app)
    r = client.get("/healthz")
    assert r.status_code == 200
    data = r.json()
    assert data.get("status") == "ok"


def test_manual_table_stub(monkeypatch, tmp_path: Path):
    # Ensure resolver doesn't misbehave if called indirectly in imports
    os.environ["FRAMEWORK_REPO_ROOT"] = str(tmp_path)

    from app.api.routers import manual as manual_router

    class FakeGen:
        def generate_manual_table(self, **kwargs):  # type: ignore[no-untyped-def]
            return "| sl | Action |\n| 1 | Click |"

    monkeypatch.setattr(manual_router, "TestCaseGenerator", lambda: FakeGen())

    client = TestClient(app)
    payload = {
        "story": "Create Supplier",
        "dbQuery": "",
        "scope": "",
        "coverage": "full",
        "includeUnlabeled": True,
        "includeLogin": True,
    }
    r = client.post("/manual/table", json=payload)
    assert r.status_code == 200, r.text
    md = r.json().get("markdown", "")
    assert "| sl |" in md