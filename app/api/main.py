from __future__ import annotations

import base64
import os
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import (
    FastAPI,
    File,
    HTTPException,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
    Form,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

# Ensure .env is loaded for Azure/OpenAI and other settings
try:
    from dotenv import load_dotenv  # type: ignore
except Exception:
    load_dotenv = None  # type: ignore

from .. import job_store
from ..services.refined_flow_service import RecorderSessionResult, finalize_recorder_session
from ..services.test_case_service import (
    TestCaseGenerationError,
    TestCaseService,
    dataframe_to_excel_bytes,
)
from ..tasks import (
    enqueue_ingest_documents,
    enqueue_ingest_jira,
    enqueue_ingest_website,
    enqueue_recorder_launch,
    enqueue_recorder_stop,
    enqueue_vector_delete_by_id,
    enqueue_vector_delete_by_source,
)
from .events import recorder_events


class AutoIngestPayload(BaseModel):
    status: str = Field(..., description="Status of auto-refine ingestion (success, error, skipped).")
    result: Optional[Dict[str, Any]] = Field(None, description="Details returned by auto_refine_and_ingest.")
    error: Optional[str] = Field(None, description="Error message when status is error.")


class RecorderSessionResponse(BaseModel):
    sessionDir: str
    listing: Dict[str, Any]
    metadata: Optional[Dict[str, Any]]
    warnings: List[str]
    autoIngest: AutoIngestPayload

    @classmethod
    def from_result(cls, result: RecorderSessionResult) -> "RecorderSessionResponse":
        payload = result.to_dict()
        return cls(
            sessionDir=payload["sessionDir"],
            listing=payload["listing"],
            metadata=payload["metadata"],
            warnings=payload["warnings"],
            autoIngest=AutoIngestPayload(**payload["autoIngest"]),
        )


class FinalizeRecorderRequest(BaseModel):
    sessionDir: str = Field(..., description="Absolute or relative path to the recorder session directory.")


class RecorderEventPayload(BaseModel):
    message: str = Field(..., description="Human readable status update.")
    level: str = Field("info", description="Severity level for the event.")
    details: Dict[str, Any] | None = Field(None, description="Optional structured payload.")


class TestCaseRequest(BaseModel):
    story: str = Field(..., description="Jira story / scenario description.")
    llmOnly: bool = Field(False, description="Skip deterministic injection when true.")
    asExcel: bool = Field(False, description="Return results as XLSX bytes if true.")


class TestCaseResponse(BaseModel):
    records: List[Dict[str, Any]]
    excel: Optional[str] = Field(
        None,
        description="Base64 encoded XLSX payload when requested via asExcel=true.",
    )


class RecorderSessionCreateRequest(BaseModel):
    url: str = Field(..., description="URL to open when the recorder launches.")
    flowName: Optional[str] = Field(None, description="Friendly name for the recorder session.")
    options: Dict[str, Any] = Field(default_factory=dict, description="Additional recorder options.")


class RecorderSessionCreateResponse(BaseModel):
    jobId: str
    sessionId: str


class JobEnqueueResponse(BaseModel):
    jobId: str


class JobDetailResponse(BaseModel):
    jobId: str
    type: str
    status: str
    payload: Dict[str, Any] | None = None
    result: Dict[str, Any] | None = None
    error: Optional[str] = None
    createdAt: str
    updatedAt: str


class IngestJiraRequest(BaseModel):
    jql: str


class IngestWebsiteRequest(BaseModel):
    url: str
    maxDepth: int = Field(2, ge=1, le=5)


job_store.init_job_store()

def _load_env_files() -> None:
    """Load environment variables from .env files.

    We load from current working directory and from repo root to be robust to different
    launch contexts (e.g., running uvicorn from project root or elsewhere).
    """
    if load_dotenv is None:
        return
    # 1) Load .env from current working dir if present
    try:
        load_dotenv()
    except Exception:
        pass
    # 2) Load .env from repository root explicitly
    try:
        repo_root = Path(__file__).resolve().parents[2]
        root_env = repo_root / ".env"
        if root_env.exists():
            load_dotenv(dotenv_path=root_env, override=False)
    except Exception:
        pass


_load_env_files()

app = FastAPI(title="Test Artifact Backend", version="0.2.0")

# CORS for local React dev server; adjust via env ALLOW_ORIGINS if needed
allow_origins = os.getenv("ALLOW_ORIGINS", "http://localhost:5173").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in allow_origins if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

test_case_service = TestCaseService()

RECORDINGS_DIR = Path(os.getenv("RECORDER_OUTPUT_DIR", "recordings")).resolve()
UPLOADS_DIR = Path(os.getenv("UPLOAD_DIR", "uploads")).resolve()
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)


def _session_identifier(session_dir: Path) -> str:
    return session_dir.name


def _job_dict_to_response(job: Dict[str, Any]) -> JobDetailResponse:
    return JobDetailResponse(
        jobId=job["id"],
        type=job["type"],
        status=job["status"],
        payload=job.get("payload"),
        result=job.get("result"),
        error=job.get("error"),
        createdAt=job["created_at"],
        updatedAt=job["updated_at"],
    )


@app.post("/api/refined-flows/finalize", response_model=RecorderSessionResponse)
async def finalize_recorder(req: FinalizeRecorderRequest) -> RecorderSessionResponse:
    session_dir = Path(req.sessionDir).expanduser().resolve()
    if not session_dir.exists():
        raise HTTPException(status_code=404, detail=f"Session directory not found: {session_dir}")

    result = finalize_recorder_session(session_dir)
    session_id = _session_identifier(session_dir)
    await recorder_events.publish(
        session_id,
        {
            "type": "finalized",
            "message": f"Session {session_id} finalized.",
            "autoIngest": result.auto_ingest_status,
        },
    )
    return RecorderSessionResponse.from_result(result)


@app.post("/recorder/finalize")
async def finalize_recorder_by_session(req: dict) -> dict:
    """Finalize recorder session by sessionId (used by recorder-sync flow)."""
    session_id = req.get("sessionId")
    if not session_id:
        raise HTTPException(status_code=400, detail="sessionId is required")
    
    session_dir = (RECORDINGS_DIR / session_id).resolve()
    if not session_dir.exists():
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")
    
    # Run finalization in background daemon thread - will auto-terminate on server restart
    def background_finalize():
        try:
            result = finalize_recorder_session(session_dir)
            print(f"[Finalize] Session {session_id} finalized successfully")
            print(f"[Finalize] Auto-ingest status: {result.auto_ingest_status}")
        except Exception as e:
            print(f"[Finalize] Error finalizing session {session_id}: {e}")
    
    thread = threading.Thread(target=background_finalize, daemon=True)
    thread.start()
    
    # Return immediately - daemon thread will complete or die on restart
    return {
        "status": "processing",
        "sessionId": session_id,
        "message": "Finalization started in background (will complete or auto-cancel on restart)"
    }


@app.post("/api/recorder/sessions", response_model=RecorderSessionCreateResponse, status_code=202)
async def create_recorder_session(req: RecorderSessionCreateRequest) -> RecorderSessionCreateResponse:
    job_id, session_id = enqueue_recorder_launch(req.model_dump())
    return RecorderSessionCreateResponse(jobId=job_id, sessionId=session_id)


@app.post("/api/recorder/sessions/{session_id}/stop", response_model=JobEnqueueResponse, status_code=202)
async def stop_recorder_session(session_id: str) -> JobEnqueueResponse:
    job_id = enqueue_recorder_stop(session_id)
    return JobEnqueueResponse(jobId=job_id)


@app.get("/api/recorder/{session_id}/artifacts/{artifact_path:path}")
async def download_recorder_artifact(session_id: str, artifact_path: str):
    base_dir = (RECORDINGS_DIR / session_id).resolve()
    target = (base_dir / artifact_path).resolve()
    if not str(target).startswith(str(base_dir)):
        raise HTTPException(status_code=400, detail="Invalid artifact path.")
    if not target.exists():
        raise HTTPException(status_code=404, detail="Artifact not found.")
    return FileResponse(target)


@app.post("/api/recorder/{session_id}/events", status_code=202)
async def publish_recorder_event(session_id: str, payload: RecorderEventPayload) -> Dict[str, str]:
    await recorder_events.publish(session_id, payload.model_dump())
    return {"status": "queued"}


@app.websocket("/ws/recorder/{session_id}")
async def recorder_event_stream(websocket: WebSocket, session_id: str) -> None:
    await websocket.accept()
    queue = await recorder_events.connect(session_id)
    try:
        while True:
            message = await queue.get()
            await websocket.send_json(message)
    except WebSocketDisconnect:
        await recorder_events.disconnect(session_id, queue)


@app.post("/api/test-cases/generate", response_model=TestCaseResponse)
async def generate_test_cases(req: TestCaseRequest) -> TestCaseResponse:
    try:
        service_result = test_case_service.generate(req.story, llm_only=req.llmOnly)
    except TestCaseGenerationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    records = service_result["records"]
    df = service_result["dataframe"]

    excel_b64: Optional[str] = None
    if req.asExcel:
        excel_bytes = dataframe_to_excel_bytes(df)
        excel_b64 = base64.b64encode(excel_bytes).decode("utf-8")

    return TestCaseResponse(records=records, excel=excel_b64)


@app.post("/api/test-cases/generate-upload", response_model=TestCaseResponse)
async def generate_test_cases_with_upload(
    story: str = Form(...),
    llmOnly: bool = Form(False),
    template: UploadFile | None = File(None),
) -> TestCaseResponse:
    """Generate test cases with optional Excel template upload.

    Accepts multipart/form-data with fields:
    - story: text content to generate test cases from
    - llmOnly: whether to skip deterministic injection
    - template: optional Excel file (.xlsx or .xls) used to map fields
    """
    template_df = None
    if template is not None and template.filename:
        name = template.filename.lower()
        try:
            if name.endswith(".xlsx") or name.endswith(".xls"):
                content = await template.read()
                import pandas as _pd  # local import to avoid global import for this path
                from io import BytesIO as _BytesIO

                template_df = _pd.read_excel(_BytesIO(content))
            else:
                # Non-Excel templates are ignored (parity with Streamlit UI)
                template_df = None
        except Exception as exc:  # pragma: no cover
            raise HTTPException(status_code=400, detail=f"Failed to read template: {exc}") from exc

    try:
        service_result = test_case_service.generate(story, llm_only=llmOnly, template_df=template_df)
    except TestCaseGenerationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    records = service_result["records"]
    df = service_result["dataframe"]
    excel_bytes = dataframe_to_excel_bytes(df)
    excel_b64 = base64.b64encode(excel_bytes).decode("utf-8")
    return TestCaseResponse(records=records, excel=excel_b64)


@app.post("/api/ingest/jira", response_model=JobEnqueueResponse, status_code=202)
async def ingest_jira_route(req: IngestJiraRequest) -> JobEnqueueResponse:
    job_id = enqueue_ingest_jira(req.jql)
    return JobEnqueueResponse(jobId=job_id)


@app.post("/api/ingest/website", response_model=JobEnqueueResponse, status_code=202)
async def ingest_website_route(req: IngestWebsiteRequest) -> JobEnqueueResponse:
    job_id = enqueue_ingest_website(req.url, req.maxDepth)
    return JobEnqueueResponse(jobId=job_id)


@app.post("/api/ingest/documents", response_model=JobEnqueueResponse, status_code=202)
async def ingest_documents_route(files: List[UploadFile] = File(...)) -> JobEnqueueResponse:
    saved_paths: List[str] = []
    for upload in files:
        target = UPLOADS_DIR / upload.filename
        content = await upload.read()
        target.write_bytes(content)
        saved_paths.append(str(target))
    job_id = enqueue_ingest_documents(saved_paths)
    return JobEnqueueResponse(jobId=job_id)


@app.delete("/api/vector/docs/{doc_id:path}", response_model=JobEnqueueResponse, status_code=202)
async def delete_vector_doc(doc_id: str) -> JobEnqueueResponse:
    from urllib.parse import unquote
    # URL decode the doc_id to handle encoded characters
    decoded_doc_id = unquote(doc_id)
    job_id = enqueue_vector_delete_by_id(decoded_doc_id)
    return JobEnqueueResponse(jobId=job_id)


@app.delete("/api/vector/docs/sync/{doc_id:path}", status_code=200)
async def delete_vector_doc_sync(doc_id: str) -> dict:
    """Synchronous delete - immediately deletes the document"""
    from app.vector_db import VectorDBClient
    from urllib.parse import unquote
    client = VectorDBClient()
    # URL decode the doc_id to handle encoded characters like %3A (colon) and %2F (slash)
    decoded_doc_id = unquote(doc_id)
    client.delete_document(decoded_doc_id)
    return {"deleted": decoded_doc_id, "status": "success"}


@app.delete("/api/vector/docs", response_model=JobEnqueueResponse, status_code=202)
async def delete_vector_by_source(source: str) -> JobEnqueueResponse:
    job_id = enqueue_vector_delete_by_source(source)
    return JobEnqueueResponse(jobId=job_id)


@app.delete("/api/vector/docs/sync", status_code=200)
async def delete_vector_by_source_sync(source: str) -> dict:
    """Synchronous delete by source - immediately deletes all documents from source"""
    from app.vector_db import VectorDBClient
    client = VectorDBClient()
    client.delete_by_source(source)
    return {"deletedSource": source, "status": "success"}


@app.get("/api/jobs/{job_id}", response_model=JobDetailResponse)
async def get_job_detail(job_id: str) -> JobDetailResponse:
    job = job_store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    return _job_dict_to_response(job)


class GitPushRequest(BaseModel):
    repoUrl: str
    branch: str = "main"
    commitMessage: str = "Add new test script"


class GitPushResponse(BaseModel):
    success: bool
    message: str


@app.post("/api/git/push", response_model=GitPushResponse)
async def push_to_git_endpoint(request: GitPushRequest) -> GitPushResponse:
    """Push changes to git repository"""
    from app.git_utils import push_to_git
    from app.api.framework_resolver import resolve_framework_root
    
    try:
        # Resolve the repository path
        repo_path = resolve_framework_root(request.repoUrl)
        
        # Push to git
        success = push_to_git(repo_path, request.branch, request.commitMessage)
        
        if success:
            return GitPushResponse(
                success=True,
                message=f"Successfully pushed to {request.branch}"
            )
        else:
            return GitPushResponse(
                success=False,
                message="Failed to push changes. Check git configuration and credentials."
            )
    except Exception as e:
        return GitPushResponse(
            success=False,
            message=f"Error: {str(e)}"
        )


# Contract-aligned routers (skeletons; some endpoints implemented in this file already)
from .routers import health as r_health
from .routers import manual as r_manual
from .routers import cases as r_cases
from .routers import agentic as r_agentic
from .routers import recorder as r_recorder
from .routers import recorder_sync as r_recorder_sync
from .routers import trial as r_trial
from .routers import files as r_files
from .routers import config as r_config
from .routers import vector as r_vector

app.include_router(r_health.router)
app.include_router(r_manual.router)
app.include_router(r_cases.router)
app.include_router(r_agentic.router)
app.include_router(r_recorder.router)
app.include_router(r_recorder_sync.router)
app.include_router(r_trial.router)
app.include_router(r_files.router)
app.include_router(r_config.router)
app.include_router(r_vector.router)


if __name__ == "__main__":
    import uvicorn

    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("API_PORT", "8000"))
    uvicorn.run("app.api.main:app", host=host, port=port, reload=False)

