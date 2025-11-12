import json
from pathlib import Path

from app.services import refined_flow_service
from app.services.refined_flow_service import finalize_recorder_session


def test_finalize_session_without_metadata(tmp_path: Path) -> None:
    session_dir = tmp_path / "session"
    session_dir.mkdir()

    result = finalize_recorder_session(session_dir)

    assert result.auto_ingest_status == "skipped"
    assert any("metadata.json missing" in warning for warning in result.warnings)


def test_finalize_session_with_metadata(tmp_path: Path, monkeypatch) -> None:
    session_dir = tmp_path / "session"
    session_dir.mkdir()
    metadata = {
        "options": {
            "captureDom": True,
            "captureScreenshots": True,
            "recordTrace": True,
            "recordHar": True,
        },
        "artifacts": {},
    }
    (session_dir / "metadata.json").write_text(json.dumps(metadata))

    fake_result = {
        "refined_path": str(session_dir / "refined.json"),
        "ingest_stats": {"added": 5},
    }
    monkeypatch.setattr(
        refined_flow_service,
        "auto_refine_and_ingest",
        lambda _session, _metadata: fake_result,
    )

    result = finalize_recorder_session(session_dir)

    assert result.auto_ingest_status == "success"
    assert result.auto_ingest_result == fake_result
    assert any("Missing artefacts" in warning for warning in result.warnings)

