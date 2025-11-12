from __future__ import annotations

import os
from fastapi import APIRouter


router = APIRouter(tags=["health"])


@router.get("/healthz")
async def healthcheck():
    return {
        "status": "ok",
        "service": "test-artifact-backend",
        "version": os.getenv("APP_VERSION", "dev"),
    }
