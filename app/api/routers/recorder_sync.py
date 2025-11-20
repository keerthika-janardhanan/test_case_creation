"""Synchronous recorder endpoints - no Celery needed."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any, Dict, Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field

# from ..auth import jwt_required
from ...services.refined_flow_service import (
    load_recorder_metadata,
    scan_session_directory,
)

router = APIRouter(prefix="/recorder-sync", tags=["recorder-sync"])  # No JWT for local dev

RECORDINGS_DIR = Path(os.getenv("RECORDER_OUTPUT_DIR", "recordings")).resolve()

# In-memory process tracking
_RECORDER_LOCK = threading.RLock()
_RECORDER_PROCESSES: Dict[str, subprocess.Popen] = {}


class RecorderStartRequest(BaseModel):
    url: str
    sessionName: Optional[str] = None
    options: Dict[str, Any] = Field(default_factory=dict)


class RecorderStartResponse(BaseModel):
    sessionId: str
    status: str


def _build_recorder_command(session_id: str, url: str, flow_name: str, options: Dict[str, Any], session_dir: Path) -> list:
    """Build the command to launch the recorder."""
    cmd = [
        sys.executable,
        "-m",
        "app.run_playwright_recorder_v2",
        "--url",
        url,
        "--output-dir",
        str(RECORDINGS_DIR),
        "--session-name",
        session_id,
        "--flow-name",
        flow_name,
    ]
    
    # Add boolean flags
    if options.get("captureDom", True):
        cmd.append("--capture-dom")
    if options.get("captureScreenshots", True):
        cmd.append("--capture-screenshots")
    if options.get("headless", False):
        cmd.append("--headless")
    if options.get("noTrace", False):
        cmd.append("--no-trace")
    if options.get("noHar", False):
        cmd.append("--no-har")
    
    # Add value flags
    if "browser" in options:
        cmd.extend(["--browser", options["browser"]])
    if "timeout" in options:
        cmd.extend(["--timeout", str(options["timeout"])])
    if "slowMo" in options:
        cmd.extend(["--slow-mo", str(options["slowMo"])])
    if "userAgent" in options:
        cmd.extend(["--user-agent", options["userAgent"]])
    
    return cmd


@router.post("/start", response_model=RecorderStartResponse)
async def start_sync(req: RecorderStartRequest) -> RecorderStartResponse:
    """Start a recorder session synchronously without Celery."""
    
    # Generate session ID
    session_id = req.sessionName or f"session_{uuid4().hex[:8]}"
    
    # Prepare output directory
    RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)
    session_dir = RECORDINGS_DIR / session_id
    
    # Ensure unique directory
    if session_dir.exists():
        suffix = uuid4().hex[:4]
        session_id = f"{session_id}_{suffix}"
        session_dir = RECORDINGS_DIR / session_id
    
    session_dir.mkdir(parents=True, exist_ok=True)
    
    # Write flow_name.txt
    flow_name = req.sessionName or session_id
    flow_name_file = session_dir / "flow_name.txt"
    flow_name_file.write_text(flow_name, encoding="utf-8")
    
    # Build command
    options = req.options or {}
    cmd = _build_recorder_command(session_id, req.url, flow_name, options, session_dir)
    
    # Log the command for debugging
    print(f"[Recorder] Starting session {session_id}")
    print(f"[Recorder] Command: {' '.join(cmd)}")
    print(f"[Recorder] URL: {req.url}")
    print(f"[Recorder] Options: {options}")
    
    try:
        # Start process in background with detached stdout/stderr
        # Use DEVNULL to prevent blocking on pipe buffers
        # Don't use CREATE_NO_WINDOW - we want the browser window to be visible
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            cwd=str(Path(__file__).parent.parent.parent.parent),  # Project root
        )
        
        print(f"[Recorder] Process started with PID: {process.pid}")
        
        # Store process
        with _RECORDER_LOCK:
            _RECORDER_PROCESSES[session_id] = process
        
        return RecorderStartResponse(sessionId=session_id, status="started")
    
    except Exception as exc:
        print(f"[Recorder] Error starting process: {exc}")
        raise HTTPException(status_code=500, detail=f"Failed to start recorder: {str(exc)}") from exc


class RecorderStopRequest(BaseModel):
    sessionId: str


@router.post("/stop")
async def stop_sync(req: RecorderStopRequest) -> Dict[str, str]:
    """Stop a recorder session."""
    import threading
    from app.services.refined_flow_service import finalize_recorder_session
    from pathlib import Path
    
    with _RECORDER_LOCK:
        process = _RECORDER_PROCESSES.get(req.sessionId)
        
        if not process:
            raise HTTPException(status_code=404, detail="Session not found or already stopped")
        
        try:
            # Send Ctrl+C signal (SIGINT on Windows)
            process.terminate()
            
            # Wait for process to finish (timeout 5 seconds)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                # Force kill if it doesn't stop gracefully
                process.kill()
                process.wait()
            
            # Remove from tracking
            del _RECORDER_PROCESSES[req.sessionId]
            
            # Auto-finalize in background after stopping
            session_dir = RECORDINGS_DIR / req.sessionId
            if session_dir.exists():
                def background_finalize():
                    try:
                        print(f"[Stop] Auto-finalizing session {req.sessionId}...")
                        result = finalize_recorder_session(session_dir)
                        print(f"[Stop] Finalization complete - Status: {result.auto_ingest_status}")
                        if result.auto_ingest_error:
                            print(f"[Stop] Finalization error: {result.auto_ingest_error}")
                    except Exception as e:
                        print(f"[Stop] Finalization failed: {e}")
                
                thread = threading.Thread(target=background_finalize, daemon=True)
                thread.start()
            
            return {"status": "stopped", "autoFinalize": "processing"}
        
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Failed to stop recorder: {str(exc)}") from exc

@router.get("/status/{session_id}")
async def status_sync(session_id: str) -> Dict[str, Any]:
    """Get status of a recorder session."""
    
    session_dir = (RECORDINGS_DIR / session_id).resolve()
    
    # Security check
    if not str(session_dir).startswith(str(RECORDINGS_DIR)):
        raise HTTPException(status_code=400, detail="Invalid session id/path")
    
    # Check if process is still running and capture any errors
    is_running = False
    process_error = None
    with _RECORDER_LOCK:
        process = _RECORDER_PROCESSES.get(session_id)
        if process:
            poll_result = process.poll()
            is_running = poll_result is None  # None means still running
            
            # If process has exited with error, capture stderr
            if poll_result is not None and poll_result != 0:
                try:
                    stderr_output = process.stderr.read() if process.stderr else ""
                    if stderr_output:
                        process_error = stderr_output[:500]  # First 500 chars
                        print(f"[Recorder] Process error for {session_id}: {process_error}")
                except Exception as e:
                    print(f"[Recorder] Could not read stderr: {e}")
    
    # Scan directory
    listing = scan_session_directory(session_dir)
    metadata = load_recorder_metadata(session_dir, attempts=2, delay=0.1)
    artifacts = dict(((metadata or {}).get("artifacts") or {}))
    files = listing.get("top_level") or []
    
    # Determine status
    if is_running:
        state = "running"
    elif metadata:
        state = "stopped"
    elif listing.get("exists"):
        state = "completed"
    else:
        state = "not-found"
    
    # Find latest screenshot for preview (limit to first 10 for performance)
    try:
        shots_dir = session_dir / "screenshots"
        if shots_dir.exists():
            latest_path: Optional[Path] = None
            latest_mtime = -1.0
            count = 0
            for p in shots_dir.glob("*.png"):
                count += 1
                if count > 10:  # Only check first 10 screenshots for performance
                    break
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
    
    response = {
        "status": state,
        "artifacts": artifacts,
        "files": files,
        "isRunning": is_running,
    }
    
    if process_error:
        response["error"] = process_error
    
    return response


@router.get("/list")
async def list_sessions() -> Dict[str, Any]:
    """List all recorder sessions with flow name and timestamp."""
    
    if not RECORDINGS_DIR.exists():
        return {"sessions": []}
    
    sessions = []
    for session_dir in RECORDINGS_DIR.iterdir():
        if session_dir.is_dir():
            session_id = session_dir.name
            
            # Check if running
            is_running = False
            with _RECORDER_LOCK:
                process = _RECORDER_PROCESSES.get(session_id)
                if process:
                    is_running = process.poll() is None
            
            # Try to load metadata for flow name and timestamp
            metadata = load_recorder_metadata(session_dir, attempts=1, delay=0.05)
            flow_name = session_id
            timestamp = None
            
            if metadata:
                flow_name = metadata.get("flowName") or metadata.get("sessionName") or session_id
                timestamp = metadata.get("timestamp") or metadata.get("startTime")
            
            # If no metadata timestamp, use directory modification time
            if not timestamp:
                try:
                    stat = session_dir.stat()
                    timestamp = stat.st_mtime
                except Exception:
                    pass
            
            sessions.append({
                "sessionId": session_id,
                "flowName": flow_name,
                "timestamp": timestamp,
                "path": str(session_dir),
                "isRunning": is_running,
            })
    
    # Sort by timestamp (newest first)
    sessions.sort(key=lambda x: x.get("timestamp") or 0, reverse=True)
    
    return {"sessions": sessions}
