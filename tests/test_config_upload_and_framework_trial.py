from pathlib import Path
from fastapi.testclient import TestClient
import subprocess

from app.api.main import app


client = TestClient(app)


def test_config_upload_datasheet_success(tmp_path: Path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)

    files = {
        "datasheetFile": ("SupplierData.xlsx", b"bytes", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
    }
    data = {"scenario": "Create Supplier", "frameworkRoot": str(repo_root)}
    r = client.post("/config/upload_datasheet", data=data, files=files)
    assert r.status_code == 200, r.text
    payload = r.json()
    assert payload.get("saved", "").startswith("data/")
    saved_rel = payload["saved"]
    assert (repo_root / saved_rel).exists()


def test_config_upload_datasheet_missing_file_returns_422(tmp_path: Path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)
    data = {"scenario": "Create Supplier", "frameworkRoot": str(repo_root)}
    r = client.post("/config/upload_datasheet", data=data)
    # Missing required file field should trigger validation error
    assert r.status_code == 422


def test_config_upload_datasheet_clone_failure(monkeypatch):
    # Simulate git clone failure for remote URL
    def fake_run(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise subprocess.CalledProcessError(returncode=128, cmd=args[0])

    monkeypatch.setattr(subprocess, "run", fake_run)
    data = {"scenario": "X", "frameworkRoot": "https://github.com/org/missing.git"}
    files = {"datasheetFile": ("Data.xlsx", b"x", "application/octet-stream")}
    r = client.post("/config/upload_datasheet", data=data, files=files)
    assert r.status_code == 400
    assert "Git clone failed" in r.text


def test_trial_run_framework_root_delegation(monkeypatch, tmp_path: Path):
    # Ensure /agentic/trial-run uses run_trial_in_framework when frameworkRoot provided
    from pathlib import Path as _P

    called = {"args": None}

    def fake_run_trial_in_framework(script: str, root: _P, headed: bool = True):  # type: ignore[no-untyped-def]
        called["args"] = (script, root, headed)
        return True, "OK"

    monkeypatch.setattr("app.executor.run_trial_in_framework", fake_run_trial_in_framework)

    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)
    payload = {
        "testFileContent": "import { test, expect } from '@playwright/test'; test('smoke', async () => { expect(true).toBeTruthy(); });",
        "headed": True,
        "frameworkRoot": str(repo_root),
    }
    r = client.post("/agentic/trial-run", json=payload)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("success") is True
    assert called["args"] is not None
    _, used_root, used_headed = called["args"]
    assert str(used_root) == str(repo_root)
    assert used_headed is True


def test_run_trial_in_framework_places_in_test_dir(monkeypatch, tmp_path: Path):
    # Unit-test run_trial_in_framework to verify temp spec is created inside detected testDir.
    from app.executor import run_trial_in_framework
    import os
    import types
    import shutil as _shutil

    repo_root = tmp_path / "framework"
    repo_root.mkdir(parents=True, exist_ok=True)
    # Create a config that sets a custom testDir
    cfg = repo_root / "playwright.config.ts"
    cfg.write_text("export default { testDir: 'e2e' }\n", encoding="utf-8")

    # Ensure command resolution uses npx path without requiring Node
    monkeypatch.setattr("app.executor.shutil.which", lambda name: "npx" if name.startswith("npx") else None)

    # Capture unlink path to verify location
    unlinked = {"path": None}

    def fake_unlink(p):  # type: ignore[no-untyped-def]
        unlinked["path"] = str(p)
        # emulate deletion without error
        try:
            os.remove(p)
        except FileNotFoundError:
            pass

    monkeypatch.setattr(os, "unlink", fake_unlink)

    # Stub subprocess.run to avoid executing Playwright
    class DummyResult:
        def __init__(self):
            self.returncode = 0
            self.stdout = "ok"
            self.stderr = ""

    monkeypatch.setattr("app.executor.subprocess.run", lambda *a, **k: DummyResult())  # type: ignore[no-untyped-call]

    success, logs = run_trial_in_framework("test('x', async()=>{})", repo_root, headed=True)
    assert success is True
    assert "ok" in logs
    assert unlinked["path"] is not None
    # The temp file should have been created under repo_root/e2e
    created_dir = Path(unlinked["path"]).parent
    assert created_dir == (repo_root / "e2e")
