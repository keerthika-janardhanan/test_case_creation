from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from ..auth import jwt_required
from ..framework_resolver import resolve_framework_root


router = APIRouter(prefix="/files", tags=["files"], dependencies=[Depends(jwt_required)])


@router.post("/upload")
async def upload(
    file: UploadFile = File(...),
    target: str = "uploads",
    frameworkRoot: Optional[str] = None,
) -> Dict[str, str]:
    if target not in {"uploads", "framework-data"}:
        raise HTTPException(status_code=400, detail="Invalid target")

    safe_name = Path(file.filename or "uploaded.bin").name
    if not safe_name:
        raise HTTPException(status_code=400, detail="Empty filename")
    data = await file.read()
    if not isinstance(data, (bytes, bytearray)):
        raise HTTPException(status_code=400, detail="Invalid file payload")

    if target == "uploads":
        base = Path("uploads").resolve()
        base.mkdir(parents=True, exist_ok=True)
        dest = (base / safe_name).resolve()
        if os.path.commonpath([str(base), str(dest)]) != str(base):
            raise HTTPException(status_code=400, detail="Invalid path")
        dest.write_bytes(bytes(data))
        return {"path": str(dest)}

    # framework-data: Save under <frameworkRoot>/data
    repo_root = Path(frameworkRoot).resolve() if frameworkRoot else resolve_framework_root()
    data_dir = (repo_root / "data").resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    dest = (data_dir / safe_name).resolve()
    if os.path.commonpath([str(repo_root.resolve()), str(dest)]) != str(repo_root.resolve()):
        raise HTTPException(status_code=400, detail="Invalid framework path")
    dest.write_bytes(bytes(data))
    rel = str(dest.relative_to(repo_root)).replace("\\", "/")
    return {"path": rel}
