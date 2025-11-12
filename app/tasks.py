"""Celery task definitions and enqueue helpers."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple
from uuid import uuid4

from celery import Task

from .celery_app import celery_app
from . import job_store
from .api.events import recorder_events
from .ingest import ingest_document, ingest_jira, ingest_web_site
from .vector_db import VectorDBClient

RECORDINGS_DIR = Path(os.getenv("RECORDER_OUTPUT_DIR", "recordings")).resolve()


_RECORDER_LOCK = threading.RLock()
_RECORDER_PROCESSES: Dict[str, subprocess.Popen[str]] = {}
_RECORDER_SESSION_JOBS: Dict[str, str] = {}
_RECORDER_SESSION_DIRS: Dict[str, Path] = {}
_RECORDER_STOP_REQUESTS: Set[str] = set()


def _env_flag(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).lower() in {"1", "true", "yes"}


DEFAULT_RECORDER_OPTIONS = {
    # Run headed by default unless RECORDER_HEADLESS is set
    "headless": _env_flag("RECORDER_HEADLESS", "0"),
    # Enable key captures by default so UI can stay simple
    "captureDom": True,
    "captureScreenshots": True,
}


def _prepare_output_root() -> Path:
    output_root = RECORDINGS_DIR
    output_root.mkdir(parents=True, exist_ok=True)
    return output_root


def _ensure_unique_session_dir(output_root: Path, session_id: str) -> Path:
    session_dir = output_root / session_id
    if session_dir.exists():
        suffix = uuid4().hex[:4]
        session_dir = output_root / f"{session_id}_{suffix}"
    session_dir.mkdir(parents=True, exist_ok=True)
    return session_dir


def _store_recorder_session(session_id: str, job_id: str, session_dir: Path, process: subprocess.Popen[str]) -> None:
    with _RECORDER_LOCK:
        _RECORDER_SESSION_JOBS[session_id] = job_id
        _RECORDER_SESSION_DIRS[session_id] = session_dir
        _RECORDER_PROCESSES[session_id] = process


def _release_recorder_session(session_id: str) -> None:
    with _RECORDER_LOCK:
        _RECORDER_SESSION_JOBS.pop(session_id, None)
        _RECORDER_SESSION_DIRS.pop(session_id, None)
        _RECORDER_PROCESSES.pop(session_id, None)
        _RECORDER_STOP_REQUESTS.discard(session_id)


def _mark_stop_requested(session_id: str) -> None:
    with _RECORDER_LOCK:
        _RECORDER_STOP_REQUESTS.add(session_id)


def _consume_stop_request(session_id: str) -> bool:
    with _RECORDER_LOCK:
        if session_id in _RECORDER_STOP_REQUESTS:
            _RECORDER_STOP_REQUESTS.remove(session_id)
            return True
        return False


def _get_recorder_runtime(session_id: str) -> Tuple[Optional[subprocess.Popen[str]], Optional[str], Optional[Path]]:
    with _RECORDER_LOCK:
        return (
            _RECORDER_PROCESSES.get(session_id),
            _RECORDER_SESSION_JOBS.get(session_id),
            _RECORDER_SESSION_DIRS.get(session_id),
        )


def _build_recorder_command(
    session_id: str,
    payload: Dict[str, Any],
    options: Dict[str, Any],
    output_root: Path,
) -> Tuple[List[str], Path]:
    flow_name = payload.get("flowName") or options.get("flowName") or payload.get("sessionName")
    session_dir = _ensure_unique_session_dir(output_root, session_id)
    if flow_name:
        (session_dir / "flow_name.txt").write_text(flow_name, encoding="utf-8")

    opts = {**DEFAULT_RECORDER_OPTIONS, **options}

    cmd: List[str] = [
        sys.executable,
        "-m",
        "app.run_playwright_recorder_v2",
        "--url",
        payload["url"],
        "--output-dir",
        str(output_root),
        "--session-name",
        session_dir.name,
    ]

    if flow_name:
        cmd.extend(["--flow-name", flow_name])

    value_flags = {
        "browser": "--browser",
        "slowMo": "--slow-mo",
        "timeout": "--timeout",
        "userAgent": "--user-agent",
        "proxy": "--proxy",
    }
    bool_flags = {
        "headless": "--headless",
        # disable flags
        "noTrace": "--no-trace",
        "noHar": "--no-har",
        # enable flags
        "captureDom": "--capture-dom",
        "captureScreenshots": "--capture-screenshots",
        "ignoreHttpsErrors": "--ignore-https-errors",
        "disableGpu": "--disable-gpu",
        "bypassCsp": "--bypass-csp",
    }

    for key, flag in value_flags.items():
        if key in opts and opts[key] not in (None, ""):
            cmd.extend([flag, str(opts[key])])

    for key, flag in bool_flags.items():
        if opts.get(key):
            cmd.append(flag)

    return cmd, session_dir


def _run_recorder_subprocess(
    cmd: List[str],
    session_dir: Path,
    *,
    session_id: Optional[str] = None,
    job_id: Optional[str] = None,
) -> Tuple[int, str, str]:
    # Ensure Python can import the 'app' package by running from repo root
    try:
        repo_root = Path(__file__).resolve().parent.parent
    except Exception:
        repo_root = Path.cwd()
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=str(repo_root),
    )
    if session_id:
        if job_id:
            _store_recorder_session(session_id, job_id, session_dir, process)
        else:
            with _RECORDER_LOCK:
                _RECORDER_PROCESSES[session_id] = process
                _RECORDER_SESSION_DIRS.setdefault(session_id, session_dir)
    stdout, stderr = process.communicate()
    return process.returncode, (stdout or "").strip(), (stderr or "").strip()


class JobTask(Task):
    abstract = True

    def on_failure(self, exc: BaseException, task_id: str, args: Tuple[Any, ...], kwargs: Dict[str, Any], einfo) -> None:
        job_id = args[0] if args else kwargs.get("job_id")
        if job_id:
            job_store.update_job(job_id, "failed", error=str(exc))

    def on_success(self, retval: Any, task_id: str, args: Tuple[Any, ...], kwargs: Dict[str, Any]) -> None:
        job_id = args[0] if args else kwargs.get("job_id")
        if job_id:
            result_payload = retval if isinstance(retval, dict) else {"result": retval}
            job_store.update_job(job_id, "completed", result=result_payload)


@celery_app.task(base=JobTask, bind=True)
def launch_recorder_session_task(self, job_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    job_store.update_job(job_id, "running")
    session_id = payload["sessionId"]
    output_root = _prepare_output_root()
    options = payload.get("options") or {}

    recorder_events.publish_from_thread(
        session_id,
        {
            "type": "launch-requested",
            "message": f"Recorder session '{session_id}' launch queued.",
            "options": options,
        },
    )

    cmd, session_dir = _build_recorder_command(session_id, payload, options, output_root)
    recorder_events.publish_from_thread(
        session_id,
        {
            "type": "launch-started",
            "message": "Recorder process starting.",
            "sessionDir": str(session_dir),
            "command": cmd,
        },
    )

    stdout = ""
    stderr = ""
    stop_requested = False
    try:
        returncode, stdout, stderr = _run_recorder_subprocess(
            cmd,
            session_dir,
            session_id=session_id,
            job_id=job_id,
        )
        stop_requested = _consume_stop_request(session_id)
        summary_payload = {
            "sessionDir": str(session_dir),
            "stdout": stdout[-2000:],
            "stderr": stderr[-2000:],
        }
        if returncode != 0 and not stop_requested:
            raise subprocess.CalledProcessError(returncode, cmd, output=stdout, stderr=stderr)

        auto_finalize_result: Optional[Dict[str, Any]] = None
        # Auto-finalize and ingest on completion (or after stop)
        try:
            from .services.refined_flow_service import finalize_recorder_session as _finalize
            result_obj = _finalize(session_dir)
            auto_finalize_result = result_obj.to_dict()
            recorder_events.publish_from_thread(
                session_id,
                {
                    "type": "auto-finalized",
                    "message": "Recorder session auto-finalized and ingested.",
                    "autoIngest": auto_finalize_result.get("autoIngest") if isinstance(auto_finalize_result, dict) else None,
                },
            )
        except Exception as _exc:
            recorder_events.publish_from_thread(
                session_id,
                {
                    "type": "auto-finalize-error",
                    "message": f"Auto-finalize failed: {_exc}",
                    "level": "error",
                },
            )

        if stop_requested:
            recorder_events.publish_from_thread(
                session_id,
                {
                    "type": "launch-stopped",
                    "message": "Recorder session terminated by user request.",
                    **summary_payload,
                },
            )
            return {
                "sessionId": session_id,
                "sessionDir": str(session_dir),
                "stdout": stdout,
                "stderr": stderr,
                "status": "stopped",
                "autoFinalize": auto_finalize_result,
            }

        recorder_events.publish_from_thread(
            session_id,
            {
                "type": "launch-completed",
                "message": "Recorder session finished.",
                **summary_payload,
            },
        )
        return {
            "sessionId": session_id,
            "sessionDir": str(session_dir),
            "stdout": stdout,
            "stderr": stderr,
            "status": "completed",
            "autoFinalize": auto_finalize_result,
        }
    except subprocess.CalledProcessError as exc:
        recorder_events.publish_from_thread(
            session_id,
            {
                "type": "launch-failed",
                "message": f"Recorder run failed: {exc}",
                "sessionDir": str(session_dir),
                "stdout": stdout[-2000:],
                "stderr": stderr[-2000:],
            },
        )
        raise
    finally:
        _release_recorder_session(session_id)


@celery_app.task(base=JobTask, bind=True)
def stop_recorder_session_task(self, job_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    job_store.update_job(job_id, "running")
    session_id = payload["sessionId"]
    recorder_events.publish_from_thread(
        session_id,
        {"type": "stop-requested", "message": f"Stop requested for session '{session_id}'."},
    )
    process, _, session_dir = _get_recorder_runtime(session_id)
    if not process:
        recorder_events.publish_from_thread(
            session_id,
            {
                "type": "stop-ignored",
                "message": "Recorder session is not currently running.",
            },
        )
        return {"sessionId": session_id, "status": "not-running"}

    _mark_stop_requested(session_id)

    if process.poll() is not None:
        recorder_events.publish_from_thread(
            session_id,
            {
                "type": "stop-ignored",
                "message": "Recorder process already finished.",
                "sessionDir": str(session_dir) if session_dir else None,
            },
        )
        return {"sessionId": session_id, "status": "already-finished"}

    try:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        recorder_events.publish_from_thread(
            session_id,
            {
                "type": "stop-completed",
                "message": "Recorder process terminated.",
                "sessionDir": str(session_dir) if session_dir else None,
            },
        )
        # Attempt auto-finalize after stop
        auto_finalize_result: Optional[Dict[str, Any]] = None
        try:
            if session_dir and session_dir.exists():
                from .services.refined_flow_service import finalize_recorder_session as _finalize
                result_obj = _finalize(session_dir)
                auto_finalize_result = result_obj.to_dict()
                recorder_events.publish_from_thread(
                    session_id,
                    {
                        "type": "auto-finalized",
                        "message": "Recorder session auto-finalized and ingested.",
                        "autoIngest": auto_finalize_result.get("autoIngest") if isinstance(auto_finalize_result, dict) else None,
                    },
                )
        except Exception:
            pass
        return {"sessionId": session_id, "status": "stopping", "autoFinalize": auto_finalize_result}
    except Exception as exc:  # noqa: BLE001
        recorder_events.publish_from_thread(
            session_id,
            {
                "type": "stop-failed",
                "message": f"Failed to terminate recorder process: {exc}",
                "sessionDir": str(session_dir) if session_dir else None,
            },
        )
        raise RuntimeError(f"Unable to terminate recorder session '{session_id}': {exc}") from exc


@celery_app.task(base=JobTask, bind=True)
def ingest_jira_task(self, job_id: str, jql: str) -> Dict[str, Any]:
    job_store.update_job(job_id, "running")
    results = ingest_jira(jql)
    return {"ingested": len(results)}


@celery_app.task(base=JobTask, bind=True)
def ingest_website_task(self, job_id: str, url: str, max_depth: int) -> Dict[str, Any]:
    job_store.update_job(job_id, "running")
    results = ingest_web_site(url, max_depth)
    return {"ingested": len(results)}


@celery_app.task(base=JobTask, bind=True)
def ingest_documents_task(self, job_id: str, paths: List[str]) -> Dict[str, Any]:
    job_store.update_job(job_id, "running")
    count = 0
    for file_path in paths:
        ingest_document(file_path)
        count += 1
    return {"ingested": count}


@celery_app.task(base=JobTask, bind=True)
def vector_delete_by_id_task(self, job_id: str, doc_id: str) -> Dict[str, Any]:
    job_store.update_job(job_id, "running")
    client = VectorDBClient()
    client.delete_document(doc_id)
    return {"deleted": doc_id}


@celery_app.task(base=JobTask, bind=True)
def vector_delete_by_source_task(self, job_id: str, source: str) -> Dict[str, Any]:
    job_store.update_job(job_id, "running")
    client = VectorDBClient()
    client.delete_by_source(source)
    return {"deletedSource": source}


def enqueue_recorder_launch(payload: Dict[str, Any]) -> Tuple[str, str]:
    session_id = payload.get("sessionId") or uuid4().hex
    payload = {**payload, "sessionId": session_id}
    job_id = job_store.create_job("recorder.launch", payload)
    launch_recorder_session_task.delay(job_id, payload)
    return job_id, session_id


def enqueue_recorder_stop(session_id: str) -> str:
    payload = {"sessionId": session_id}
    job_id = job_store.create_job("recorder.stop", payload)
    stop_recorder_session_task.delay(job_id, payload)
    return job_id


def enqueue_ingest_jira(jql: str) -> str:
    job_id = job_store.create_job("ingest.jira", {"jql": jql})
    ingest_jira_task.delay(job_id, jql)
    return job_id


def enqueue_ingest_website(url: str, max_depth: int) -> str:
    job_id = job_store.create_job("ingest.website", {"url": url, "maxDepth": max_depth})
    ingest_website_task.delay(job_id, url, max_depth)
    return job_id


def enqueue_ingest_documents(paths: Iterable[str]) -> str:
    paths = list(paths)
    job_id = job_store.create_job("ingest.documents", {"paths": paths})
    ingest_documents_task.delay(job_id, paths)
    return job_id


def enqueue_vector_delete_by_id(doc_id: str) -> str:
    job_id = job_store.create_job("vector.delete_id", {"docId": doc_id})
    vector_delete_by_id_task.delay(job_id, doc_id)
    return job_id


def enqueue_vector_delete_by_source(source: str) -> str:
    job_id = job_store.create_job("vector.delete_source", {"source": source})
    vector_delete_by_source_task.delay(job_id, source)
    return job_id
