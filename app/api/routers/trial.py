from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from starlette.responses import StreamingResponse

from ..auth import jwt_required
from ..framework_resolver import resolve_framework_root
from ..sse import _format_sse
from ...trial_spec_adapter import (
    prepare_trial_spec_path,
    trial_env_overrides,
)


router = APIRouter(prefix="/trial", tags=["trial"], dependencies=[Depends(jwt_required)])


class TrialRunRequest(BaseModel):
    specPath: Optional[str] = Field(None, description="Relative path to a spec under the framework repo")
    code: Optional[str] = Field(None, description="Inline TypeScript spec content to run (temp file)")
    headed: bool = True
    frameworkRoot: Optional[str] = None
    scenario: Optional[str] = Field(None, description="Scenario/TestCaseID to select credentials from TestConfiguration")


@router.post("/run")
async def run(req: TrialRunRequest) -> Dict[str, Any]:
    repo_root = Path(req.frameworkRoot).resolve() if req.frameworkRoot else resolve_framework_root()
    if not repo_root.exists():
        raise HTTPException(status_code=404, detail="Framework root not found")

    temp_created: Optional[Path] = None
    cleanup_cb = None
    try:
        if req.code and req.code.strip():
            # Write inline spec to a temp file under tests directory if available
            tests_dir = (repo_root / 'tests') if (repo_root / 'tests').exists() else repo_root
            tests_dir.mkdir(parents=True, exist_ok=True)
            import tempfile
            fd, temp_path_str = tempfile.mkstemp(prefix="trial_inline_", suffix=".spec.ts", dir=str(tests_dir))
            os.close(fd)
            temp_created = Path(temp_path_str)
            temp_created.write_text(req.code, encoding='utf-8')
            spec_path = temp_created
        else:
            if not req.specPath:
                raise HTTPException(status_code=400, detail="Either specPath or code must be provided")
            candidate = (repo_root / req.specPath).resolve()
            # Ensure within repo root
            if os.path.commonpath([str(repo_root.resolve()), str(candidate)]) != str(repo_root.resolve()):
                raise HTTPException(status_code=400, detail="specPath must be inside framework root")
            if not candidate.exists():
                raise HTTPException(status_code=404, detail="Spec file not found")
            spec_path, cleanup_cb = prepare_trial_spec_path(candidate, repo_root)

        env = os.environ.copy()
        # Always consider TestConfiguration sheet for trial credentials, using provided scenario or inferring from spec
        env.update(trial_env_overrides(repo_root, case_id=(req.scenario or None), spec_path=spec_path))
        cmd = ["npx", "playwright", "test", str(spec_path), "--reporter=line"]
        if req.headed:
            cmd.append("--headed")
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(repo_root),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env=env,
        )
        stdout_bytes = await proc.stdout.read() if proc.stdout else b""
        returncode = await proc.wait()
        logs = stdout_bytes.decode("utf-8", errors="replace")
        status = "PASS" if returncode == 0 else "FAIL"
        return {"status": status, "logs": logs}
    finally:
        if cleanup_cb:
            try:
                cleanup_cb()
            except Exception:
                pass
        if temp_created:
            try:
                temp_created.unlink(missing_ok=True)  # type: ignore[arg-type]
            except Exception:
                pass


@router.get("/stream")
async def stream(spec: str, headed: bool = True, frameworkRoot: Optional[str] = None, scenario: Optional[str] = None) -> StreamingResponse:
    repo_root = Path(frameworkRoot).resolve() if frameworkRoot else resolve_framework_root()
    candidate = (repo_root / spec).resolve()
    if os.path.commonpath([str(repo_root.resolve()), str(candidate)]) != str(repo_root.resolve()):
        raise HTTPException(status_code=400, detail="spec must be inside framework root")
    if not candidate.exists():
        raise HTTPException(status_code=404, detail="Spec file not found")
    spec_path, cleanup_cb = prepare_trial_spec_path(candidate, repo_root)

    async def gen() -> AsyncGenerator[bytes, None]:
        try:
            env = os.environ.copy()
            # Apply trial-time environment from TestConfiguration; infer case id from spec if not provided
            env.update(trial_env_overrides(repo_root, case_id=(scenario or None), spec_path=spec_path))
            cmd = ["npx", "playwright", "test", str(spec_path), "--reporter=line"]
            if headed:
                cmd.append("--headed")
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(repo_root),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                env=env,
            )
            if proc.stdout:
                while True:
                    line = await proc.stdout.readline()
                    if not line:
                        break
                    try:
                        text = line.decode("utf-8", errors="replace").rstrip("\n")
                    except Exception:
                        text = str(line)
                    yield _format_sse({"message": text, "level": "info"})
            returncode = await proc.wait()
            status = "PASS" if returncode == 0 else "FAIL"
            yield _format_sse({"message": f"[status] {status}", "level": "info"})
        except Exception as exc:
            yield _format_sse({"message": f"[error] {exc}", "level": "error"})
        finally:
            if cleanup_cb:
                try:
                    cleanup_cb()
                except Exception:
                    pass

    return StreamingResponse(gen(), media_type="text/event-stream")
