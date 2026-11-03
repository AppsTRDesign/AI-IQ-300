"""In-process event bus: monotonic sequence, bounded per-subscriber queues, bounded replay buffer."""
from __future__ import annotations

import asyncio
import itertools
import time
from collections import deque
from typing import Any

REPLAY_LIMIT = 5000
QUEUE_LIMIT = 2000


class EventBus:
    def __init__(self) -> None:
        self._seq = itertools.count(1)
        self._history: deque[dict] = deque(maxlen=REPLAY_LIMIT)
        self._subs: set[asyncio.Queue] = set()

    def publish(self, topic: str, type_: str, payload: dict[str, Any]) -> dict:
        evt = {"seq": next(self._seq), "ts": time.time(), "topic": topic, "type": type_, "payload": payload}
        self._history.append(evt)
        for q in list(self._subs):
            if q.full():
                # Slow client: drop oldest and mark the gap rather than blocking producers.
                try:
                    q.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                q.put_nowait({"seq": evt["seq"], "ts": evt["ts"], "topic": "system", "type": "gap", "payload": {}})
            q.put_nowait(evt)
        return evt

    def subscribe(self, since: int = 0) -> tuple[asyncio.Queue, list[dict], bool]:
        q: asyncio.Queue = asyncio.Queue(maxsize=QUEUE_LIMIT)
        self._subs.add(q)
        replay = [e for e in self._history if e["seq"] > since]
        truncated = bool(since and self._history and self._history[0]["seq"] > since + 1)
        return q, replay, truncated

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subs.discard(q)


bus = EventBus()
