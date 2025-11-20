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


class FlowListItem(BaseModel):
    flowName: str
    flowSlug: str
    timestamp: Optional[str] = None
    stepCount: int = 0


class FlowListResponse(BaseModel):
    flows: List[FlowListItem]


@router.get("/flows", response_model=FlowListResponse)
async def list_flows() -> FlowListResponse:
    """List all refined recorder flows from the vector database."""
    try:
        from ...vector_db import VectorDBClient
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Import failure: {exc}") from exc

    client = VectorDBClient(path=os.getenv("VECTOR_DB_PATH", "./vector_store"))
    
    try:
        # Query for all recorder_refined documents
        raw = client.get_where(where={"type": "recorder_refined"}, limit=1000)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Vector query failed: {exc}") from exc

    # Group by flow_slug to get unique flows
    flows_map: Dict[str, Dict[str, Any]] = {}
    for item in raw or []:
        metadata = item.get("metadata") or {}
        flow_slug = metadata.get("flow_slug")
        if not flow_slug:
            continue
        
        if flow_slug not in flows_map:
            flows_map[flow_slug] = {
                "flowName": metadata.get("flow_name") or flow_slug,
                "flowSlug": flow_slug,
                "timestamp": metadata.get("timestamp") or metadata.get("ingested_at"),
                "stepCount": 0
            }
        
        # Count steps
        flows_map[flow_slug]["stepCount"] += 1

    # Convert to list and sort by timestamp (newest first)
    flows = list(flows_map.values())
    flows.sort(key=lambda x: x.get("timestamp") or "", reverse=True)
    
    return FlowListResponse(flows=[FlowListItem(**f) for f in flows])
