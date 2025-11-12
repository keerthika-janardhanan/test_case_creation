from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field


router = APIRouter(prefix="/manual", tags=["manual"])


class ManualTableRequest(BaseModel):
    story: str = Field(...)
    dbQuery: str = Field("", description="Optional vector DB query override")
    scope: str = Field("", description="Optional scope hint")
    coverage: str = Field("grouped", pattern="^(grouped|full)$")
    includeUnlabeled: bool = False
    includeLogin: bool = False


class ManualTableResponse(BaseModel):
    markdown: str


@router.post("/table", response_model=ManualTableResponse)
async def generate_manual_table(req: ManualTableRequest) -> ManualTableResponse:
    # Lazy import to avoid circulars during app startup
    try:
        from ...test_case_generator import TestCaseGenerator  # type: ignore
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=500, detail=f"Import failure: {exc}") from exc

    tcg = TestCaseGenerator()
    try:
        md = tcg.generate_manual_table(
            story=req.story.strip(),
            db_query=req.dbQuery.strip() or None,
            scope=req.scope.strip() or None,
            coverage=req.coverage.strip().lower(),
            include_unlabeled=bool(req.includeUnlabeled),
            include_login=bool(req.includeLogin),
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ManualTableResponse(markdown=md)
