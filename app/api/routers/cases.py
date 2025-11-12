from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional


router = APIRouter(prefix="/cases", tags=["cases"])


class CasesGenerateRequest(BaseModel):
    story: str = Field(...)
    llmOnly: bool = False


class CaseItem(BaseModel):
    type: str
    steps: List[str]
    expected: Optional[str] = None


class CasesGenerateResponse(BaseModel):
    cases: List[CaseItem]


@router.post("/generate", response_model=CasesGenerateResponse)
async def generate_cases(req: CasesGenerateRequest) -> CasesGenerateResponse:
    # Lazy import to keep routers light
    try:
        from ...services.test_case_service import TestCaseService, TestCaseGenerationError
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=500, detail=f"Import failure: {exc}") from exc

    service = TestCaseService()
    try:
        result = service.generate(req.story.strip(), llm_only=req.llmOnly)
    except TestCaseGenerationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    # Normalize to contract shape
    items: List[CaseItem] = []
    for rec in result.get("records", []):
        case_type = str(rec.get("type") or "").strip()
        steps_field = rec.get("steps")
        if isinstance(steps_field, list):
            steps = [str(s).strip() for s in steps_field if str(s).strip()]
        elif isinstance(steps_field, str):
            steps = [line.strip() for line in steps_field.split("\n") if line.strip()]
        else:
            # Derive from step_details if needed
            details = rec.get("step_details") or []
            steps = [
                (str(d.get("action") or d.get("navigation") or d)
                 if isinstance(d, dict) else str(d))
                for d in details
            ]
            steps = [s for s in steps if s]

        expected: Optional[str] = None
        if isinstance(rec.get("expected"), str) and rec.get("expected").strip():
            expected = rec.get("expected").strip()
        else:
            details = rec.get("step_details") or []
            if details and isinstance(details[-1], dict):
                exp = details[-1].get("expected")
                if isinstance(exp, str) and exp.strip():
                    expected = exp.strip()

        items.append(CaseItem(type=case_type, steps=steps, expected=expected))

    return CasesGenerateResponse(cases=items)
