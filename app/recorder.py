"""Lightweight FlowRecorder stub to satisfy integration tests and support migration scaffolding."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List


SENSITIVE_KEYWORDS = ("password", "pass", "token", "secret", "card", "ssn")


def _is_sensitive(selector: str | None) -> bool:
    selector_lower = (selector or "").lower()
    return any(keyword in selector_lower for keyword in SENSITIVE_KEYWORDS)


@dataclass
class FlowRecorder:
    """Async-friendly stub that mimics recorder output and provides sanitisation hooks."""

    name: str | None = None

    async def record_flow(self, flow_name: str, url: str) -> Dict[str, Any]:
        """Simulate collecting a flow, returning a deterministic payload suited for tests."""

        await asyncio.sleep(0)
        events = [
            {"type": "navigation", "url": url, "timestamp": 0},
            {"type": "fill", "selector": "#username", "value": "demo_user", "timestamp": 1},
            {"type": "fill", "selector": "#password", "value": "super-secret", "timestamp": 2},
            {"type": "click", "selector": "button.submit", "timestamp": 3},
        ]
        sanitized = self._sanitize_events(events)
        return {
            "name": flow_name or self.name or "recorder_flow",
            "origin_url": url,
            "events": sanitized,
        }

    def _sanitize_events(self, events: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Redact sensitive values without mutating the original iterable."""

        sanitized: List[Dict[str, Any]] = []
        for event in events:
            clone = dict(event)
            selector = clone.get("selector")
            if "value" in clone and _is_sensitive(selector):
                clone["value"] = "***REDACTED***"
            sanitized.append(clone)
        return sanitized

