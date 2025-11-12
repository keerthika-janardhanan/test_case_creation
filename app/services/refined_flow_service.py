"""Service functions for processing recorder sessions and refined flow ingestion."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from ..recorder_auto_ingest import auto_refine_and_ingest


@dataclass
class RecorderSessionResult:
    """Normalized result for recorder session finalisation."""

    session_dir: Path
    listing: Dict[str, Any]
    metadata: Optional[Dict[str, Any]]
    warnings: list[str]
    auto_ingest_status: str
    auto_ingest_result: Optional[Dict[str, Any]]
    auto_ingest_error: Optional[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sessionDir": str(self.session_dir),
            "listing": self.listing,
            "metadata": self.metadata,
            "warnings": self.warnings,
            "autoIngest": {
                "status": self.auto_ingest_status,
                "result": self.auto_ingest_result,
                "error": self.auto_ingest_error,
            },
        }


def load_recorder_metadata(session_dir: Path, attempts: int = 15, delay: float = 0.5) -> Optional[Dict[str, Any]]:
    """Best-effort load of Playwright recorder metadata.json."""

    session_path = session_dir
    metadata_path = session_path / "metadata.json"
    for _ in range(max(attempts, 1)):
        if metadata_path.exists():
            try:
                return json.loads(metadata_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                time.sleep(delay)
                continue
        time.sleep(delay)
    return None


def scan_session_directory(session_dir: Path) -> Dict[str, Any]:
    """Collect a lightweight summary of recorder session artefacts."""

    summary: Dict[str, Any] = {
        "exists": False,
        "top_level": [],
        "dom_files": 0,
        "screenshot_files": 0,
    }

    session_path = session_dir
    if not session_path.exists():
        return summary

    summary["exists"] = True
    try:
        summary["top_level"] = sorted(p.name for p in session_path.iterdir())
    except Exception:
        summary["top_level"] = []

    dom_dir = session_path / "dom"
    if dom_dir.exists():
        summary["dom_files"] = len(list(dom_dir.glob("*.html")))

    shots_dir = session_path / "screenshots"
    if shots_dir.exists():
        summary["screenshot_files"] = len(list(shots_dir.glob("*.png")))

    return summary


def finalize_recorder_session(session_dir: Path, metadata: Optional[Dict[str, Any]] = None) -> RecorderSessionResult:
    """Prepare recorder session artefacts and optionally run auto refine + ingest."""

    listing = scan_session_directory(session_dir)
    warnings: list[str] = []

    if metadata is None:
        metadata = load_recorder_metadata(session_dir)

    auto_status = "skipped"
    auto_result: Optional[Dict[str, Any]] = None
    auto_error: Optional[str] = None

    if not metadata:
        if listing["exists"]:
            warnings.append(
                "Recorder metadata.json missing; available artefacts: " + ", ".join(listing.get("top_level", []) or [])
            )
        else:
            warnings.append("Recorder session directory not found.")
        return RecorderSessionResult(
            session_dir=session_dir,
            listing=listing,
            metadata=None,
            warnings=warnings,
            auto_ingest_status=auto_status,
            auto_ingest_result=auto_result,
            auto_ingest_error=auto_error,
        )

    options = metadata.get("options") or {}
    artifacts = metadata.get("artifacts") or {}
    missing_parts: list[str] = []

    if options.get("captureDom") and not listing.get("dom_files"):
        missing_parts.append("DOM snapshots")
    if options.get("captureScreenshots") and not listing.get("screenshot_files"):
        missing_parts.append("screenshots")
    if options.get("recordTrace") and not artifacts.get("trace"):
        missing_parts.append("trace.zip")
    if options.get("recordHar") and not artifacts.get("har"):
        missing_parts.append("network.har")

    if missing_parts:
        warnings.append("Missing artefacts: " + ", ".join(missing_parts))

    try:
        auto_result = auto_refine_and_ingest(str(session_dir), metadata)
        auto_status = "success"
    except Exception as exc:  # noqa: BLE001
        auto_status = "error"
        auto_error = str(exc)
        warnings.append(f"Auto refine ingest failed: {exc}")

    return RecorderSessionResult(
        session_dir=session_dir,
        listing=listing,
        metadata=metadata,
        warnings=warnings,
        auto_ingest_status=auto_status,
        auto_ingest_result=auto_result,
        auto_ingest_error=auto_error,
    )
