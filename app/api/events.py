from __future__ import annotations

import asyncio
from typing import Any, Dict, Set


class RecorderEventBroker:
    """Manages recorder event subscribers for WebSocket/SSE streaming."""

    def __init__(self) -> None:
        self._listeners: Dict[str, Set[asyncio.Queue]] = {}
        self._lock = asyncio.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None

    async def connect(self, session_id: str) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        async with self._lock:
            listeners = self._listeners.setdefault(session_id, set())
            listeners.add(queue)
            self._loop = asyncio.get_running_loop()
        return queue

    async def disconnect(self, session_id: str, queue: asyncio.Queue) -> None:
        async with self._lock:
            listeners = self._listeners.get(session_id)
            if not listeners:
                return
            listeners.discard(queue)
            if not listeners:
                self._listeners.pop(session_id, None)

    async def publish(self, session_id: str, message: Dict[str, Any]) -> None:
        async with self._lock:
            queues = list(self._listeners.get(session_id, set()))
        for queue in queues:
            await queue.put(message)

    def publish_from_thread(self, session_id: str, message: Dict[str, Any]) -> None:
        """Allow synchronous contexts to enqueue events by scheduling on the captured loop."""

        loop = self._loop
        if not loop or loop.is_closed():
            return
        asyncio.run_coroutine_threadsafe(self.publish(session_id, message), loop)


recorder_events = RecorderEventBroker()

