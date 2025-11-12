"""Client helper to publish recorder events to the FastAPI backend."""

from __future__ import annotations

import os
from typing import Any, Dict

import requests


BACKEND_BASE_URL = os.getenv("BACKEND_BASE_URL", "http://localhost:8000")


def publish_recorder_event(session_id: str, message: str, level: str = "info", **details: Any) -> None:
    """Send a recorder event to the backend event stream, ignoring network failures."""

    if not session_id:
        return
    url = f"{BACKEND_BASE_URL.rstrip('/')}/api/recorder/{session_id}/events"
    payload: Dict[str, Any] = {"message": message, "level": level}
    if details:
        payload["details"] = details
    try:
        requests.post(url, json=payload, timeout=2)
    except requests.RequestException:
        # Backend may not be running yet during local dev; fail silently.
        return

