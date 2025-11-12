from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from ..auth import jwt_required
from ...tasks import enqueue_recorder_launch, enqueue_recorder_stop
from ...services.refined_flow_service import (
    load_recorder_metadata,
    scan_session_directory,
    finalize_recorder_session,
)


router = APIRouter(prefix="/recorder", tags=["recorder"], dependencies=[Depends(jwt_required)])


class RecorderStartRequest(BaseModel):
    url: str
    sessionName: Optional[str] = None
    options: Dict[str, Any] = Field(default_factory=dict)


class RecorderStartResponse(BaseModel):
    sessionId: str
    status: str


@router.post("/start", response_model=RecorderStartResponse)
async def start(req: RecorderStartRequest) -> RecorderStartResponse:
    payload = {
        "url": req.url,
        "sessionName": req.sessionName,
        "options": req.options or {},
    }
    try:
        job_id, session_id = enqueue_recorder_launch(payload)
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return RecorderStartResponse(sessionId=session_id, status="started")


class RecorderStopRequest(BaseModel):
    sessionId: str


@router.post("/stop")
async def stop(req: RecorderStopRequest) -> Dict[str, str]:
    try:
        enqueue_recorder_stop(req.sessionId)
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"status": "stopping"}


@router.get("/status/{session_id}")
async def status(session_id: str) -> Dict[str, Any]:
    base_dir = Path(os.getenv("RECORDER_OUTPUT_DIR", "recordings")).resolve()
    session_dir = (base_dir / session_id).resolve()
    if not str(session_dir).startswith(str(base_dir)):
        raise HTTPException(status_code=400, detail="Invalid session id/path")
    listing = scan_session_directory(session_dir)
    metadata = load_recorder_metadata(session_dir, attempts=2, delay=0.1)
    artifacts = dict(((metadata or {}).get("artifacts") or {}))
    files = listing.get("top_level") or []
    # Heuristic status: 'stopped' if metadata present, else 'running' if dir exists
    state = "stopped" if metadata else ("running" if listing.get("exists") else "not-found")
    # Best-effort: surface latest screenshot for inline preview
    try:
        shots_dir = session_dir / "screenshots"
        if shots_dir.exists():
            latest_path: Optional[Path] = None
            latest_mtime = -1.0
            for p in shots_dir.glob("*.png"):
                try:
                    m = p.stat().st_mtime
                except Exception:
                    m = 0.0
                if m >= latest_mtime:
                    latest_mtime = m
                    latest_path = p
            if latest_path is not None:
                try:
                    rel = latest_path.relative_to(session_dir)
                    artifacts.setdefault("latestScreenshot", str(rel))
                except Exception:
                    artifacts.setdefault("latestScreenshot", str(latest_path))
    except Exception:
        pass
    return {"status": state, "artifacts": artifacts, "files": files}


class RecorderFinalizeRequest(BaseModel):
    sessionId: str


@router.post("/finalize")
async def finalize(req: RecorderFinalizeRequest) -> Dict[str, Any]:
    """Finalize a recorder session by ID and run auto refine + ingest.

    Returns a payload aligned to the legacy /api/refined-flows/finalize endpoint
    for frontend reuse.
    """
    base_dir = Path(os.getenv("RECORDER_OUTPUT_DIR", "recordings")).resolve()
    session_dir = (base_dir / req.sessionId).resolve()
    if not str(session_dir).startswith(str(base_dir)):
        raise HTTPException(status_code=400, detail="Invalid session id/path")
    if not session_dir.exists():
        raise HTTPException(status_code=404, detail="Session directory not found")
    try:
        result = finalize_recorder_session(session_dir)
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return result.to_dict()
