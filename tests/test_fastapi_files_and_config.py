from pathlib import Path
import os
from fastapi.testclient import TestClient

from app.api.main import app


def test_upload_to_framework_data(tmp_path: Path, monkeypatch):
    # Prepare fake framework root
    repo_root = tmp_path / "framework"
    repo_root.mkdir()
    monkeypatch.setenv("FRAMEWORK_REPO_ROOT", str(repo_root))

    client = TestClient(app)
    files = {"file": ("CreateSupplierData.xlsx", b"bytes", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    r = client.post("/files/upload?target=framework-data", files=files)
    assert r.status_code == 200, r.text
    rel = r.json().get("path")
    assert rel and rel.startswith("data/")
    saved = repo_root / rel
    assert saved.exists()


def test_update_test_manager_stub(monkeypatch, tmp_path: Path):
    # Use stub to avoid openpyxl
    repo_root = tmp_path / "framework"
    repo_root.mkdir()
    monkeypatch.setenv("FRAMEWORK_REPO_ROOT", str(repo_root))

    from app.api.routers import config as config_router

    def fake_update(framework_root, scenario, execute_value, create_if_missing, datasheet, reference_id, id_name):  # type: ignore[no-untyped-def]
        return {
            "path": "testmanager.xlsx",
            "mode": "updated",
            "description": scenario,
            "previous": "",
            "execute": execute_value,
        }

    monkeypatch.setattr(config_router, "update_test_manager_entry", fake_update)

    client = TestClient(app)
    payload = {
        "scenario": "Create Supplier",
        "datasheet": "CreateSupplierData.xlsx",
        "referenceId": "CreateSupplier001",
        "idName": "CreateSupplierID",
    }
    r = client.post("/config/update_test_manager", json=payload)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("mode") in {"updated", "created", "unchanged"}