from __future__ import annotations

from typing import AsyncGenerator, Dict

from starlette.responses import StreamingResponse


def _format_sse(event: Dict) -> bytes:
    # Minimal SSE framing: only data; clients can parse JSON strings
    import json

    payload = json.dumps(event, ensure_ascii=False)
    return f"data: {payload}\n\n".encode("utf-8")


def sse_response(generator: AsyncGenerator[Dict, None]) -> StreamingResponse:
    """Wrap an async generator yielding dict events into an SSE StreamingResponse."""

    return StreamingResponse(generator, media_type="text/event-stream")
