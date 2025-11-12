from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
import os
from pydantic import BaseModel


router = APIRouter(prefix="/vector", tags=["vector"])


class VectorQueryRequest(BaseModel):
    query: str
    topK: int = 5
    where: Optional[Dict[str, Any]] = None


class VectorRecord(BaseModel):
    id: Optional[str] = None
    content: str
    metadata: Dict[str, Any] = {}


class VectorQueryResponse(BaseModel):
    results: List[VectorRecord]


@router.post("/query", response_model=VectorQueryResponse)
async def query(req: VectorQueryRequest) -> VectorQueryResponse:
    try:
        from ...vector_db import VectorDBClient
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=500, detail=f"Import failure: {exc}") from exc

    client = VectorDBClient(path=os.getenv("VECTOR_DB_PATH", "./vector_store"))  # type: ignore[name-defined]
    # The above uses os from the global scope if available; fallback to default path if not.
    try:
        top_k = max(1, req.topK)
        query_str = (req.query or "").strip()
        where = req.where or None
        # When query string is empty, treat as a listing operation for admin UX.
        if not query_str:
            if where:
                # Use get_where (list semantics) instead of similarity search.
                raw = client.get_where(where=where, limit=top_k)
            else:
                raw = client.list_all(limit=top_k)
        else:
            if where:
                raw = client.query_where(query_str, where=where, top_k=top_k)
            else:
                raw = client.query(query_str, top_k=top_k)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Vector query failed: {exc}") from exc

    records: List[VectorRecord] = []
    for item in raw or []:
        content = item.get("content")
        if content is None:
            continue
        records.append(
            VectorRecord(
                id=item.get("id"),
                content=str(content),
                metadata=item.get("metadata") or {},
            )
        )
    return VectorQueryResponse(results=records)
