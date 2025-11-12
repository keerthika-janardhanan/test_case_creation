from pathlib import Path
import os
from fastapi.testclient import TestClient

from app.api.main import app


def test_agentic_preview_stub(monkeypatch, tmp_path: Path):
    # Ensure resolver uses temp repo root with expected dirs
    repo_root = tmp_path / "framework"
    (repo_root / "tests").mkdir(parents=True)
    (repo_root / "pages").mkdir(parents=True)
    (repo_root / "locators").mkdir(parents=True)
    monkeypatch.setenv("FRAMEWORK_REPO_ROOT", str(repo_root))

    from app.api.routers import agentic as agentic_router

    class FakeAgent:
        def gather_context(self, scenario: str):  # type: ignore[no-untyped-def]
            return {"enriched_steps": "", "vector_steps": [{"step": 1, "action": "Click", "navigation": "Button"}]}

        def generate_preview(self, scenario, framework, context):  # type: ignore[no-untyped-def]
            return "1. Click | Button"

    monkeypatch.setattr(agentic_router, "AgenticScriptAgent", lambda: FakeAgent())

    client = TestClient(app)
    r = client.post("/agentic/preview", json={"scenario": "Create Supplier"})
    assert r.status_code == 200, r.text
    assert "preview" in r.json()


def test_agentic_payload_stub(monkeypatch, tmp_path: Path):
    repo_root = tmp_path / "framework"
    (repo_root / "tests").mkdir(parents=True)
    (repo_root / "pages").mkdir(parents=True)
    (repo_root / "locators").mkdir(parents=True)
    monkeypatch.setenv("FRAMEWORK_REPO_ROOT", str(repo_root))

    from app.api.routers import agentic as agentic_router

    class FakeAgent:
        def generate_script_payload(self, scenario, framework, accepted_preview):  # type: ignore[no-untyped-def]
            return {
                "locators": [{"path": "locators/slug.ts", "content": "export default {}"}],
                "pages": [{"path": "pages/SlugPage.ts", "content": "export class SlugPage {}"}],
                "tests": [{"path": "tests/slug.spec.ts", "content": "// test"}],
            }

    monkeypatch.setattr(agentic_router, "AgenticScriptAgent", lambda: FakeAgent())

    client = TestClient(app)
    r = client.post("/agentic/payload", json={"scenario": "Create Supplier", "acceptedPreview": "1. Click | Button"})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("tests") and data["tests"][0]["path"].startswith("tests/")


def test_agentic_preview_stream_stub(monkeypatch, tmp_path: Path):
    repo_root = tmp_path / "framework"
    (repo_root / "tests").mkdir(parents=True)
    (repo_root / "pages").mkdir(parents=True)
    (repo_root / "locators").mkdir(parents=True)
    monkeypatch.setenv("FRAMEWORK_REPO_ROOT", str(repo_root))

    from app.api.routers import agentic as agentic_router

    class FakeAgent:
        def gather_context(self, scenario: str):  # type: ignore[no-untyped-def]
            return {"enriched_steps": "", "vector_steps": [{"step": 1, "action": "Click", "navigation": "Button"}]}

        def generate_preview(self, scenario, framework, context):  # type: ignore[no-untyped-def]
            return "1. Click | Button"

    monkeypatch.setattr(agentic_router, "AgenticScriptAgent", lambda: FakeAgent())

    client = TestClient(app)
    with client.stream("POST", "/agentic/preview/stream", json={"scenario": "Create Supplier"}) as r:
        assert r.status_code == 200
        content = b"".join(r.iter_bytes())
        text = content.decode("utf-8", errors="replace")
        assert "text/event-stream" in r.headers.get("content-type", "")
        assert "\n\n" in text  # SSE frame separator
        assert "\"phase\": \"preview\"" in text
        assert "Click | Button" in text


def test_agentic_payload_stream_stub(monkeypatch, tmp_path: Path):
    repo_root = tmp_path / "framework"
    (repo_root / "tests").mkdir(parents=True)
    (repo_root / "pages").mkdir(parents=True)
    (repo_root / "locators").mkdir(parents=True)
    monkeypatch.setenv("FRAMEWORK_REPO_ROOT", str(repo_root))

    from app.api.routers import agentic as agentic_router

    class FakeAgent:
        def gather_context(self, scenario: str):  # type: ignore[no-untyped-def]
            return {"vector_steps": [{"step": 1, "action": "Click", "navigation": "Button"}]}

        def generate_script_payload(self, scenario, framework, accepted_preview):  # type: ignore[no-untyped-def]
            return {
                "locators": [{"path": "locators/slug.ts", "content": "export default {}"}],
                "pages": [{"path": "pages/SlugPage.ts", "content": "export class SlugPage {}"}],
                "tests": [{"path": "tests/slug.spec.ts", "content": "// test"}],
            }

    monkeypatch.setattr(agentic_router, "AgenticScriptAgent", lambda: FakeAgent())

    client = TestClient(app)
    with client.stream(
        "POST",
        "/agentic/payload/stream",
        json={"scenario": "Create Supplier", "acceptedPreview": "1. Click | Button"},
    ) as r:
        assert r.status_code == 200
        text = b"".join(r.iter_bytes()).decode("utf-8", errors="replace")
        assert "text/event-stream" in r.headers.get("content-type", "")
        assert "\"phase\": \"payload\"" in text
        assert "\"tests\": 1" in text  # summary.tests = 1