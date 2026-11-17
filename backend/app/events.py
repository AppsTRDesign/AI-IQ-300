"""In-process event bus: monotonic sequence, bounded per-subscriber queues, bounded replay buffer."""
from __future__ import annotations

import asyncio
import itertools
import time
import uuid
from collections import deque
from typing import Any

REPLAY_LIMIT = 5000
QUEUE_LIMIT = 4000


class EventBus:
    def __init__(self) -> None:
        self._seq = itertools.count(1)
        self.last_seq = 0
        # Changes with every start of the app: a browser tab that was open before a restart sees another id and
        # reloads its state, instead of waiting for sequence numbers that start again at 1.
        self.boot = uuid.uuid4().hex[:12]
        self._history: deque[dict] = deque(maxlen=REPLAY_LIMIT)
        self._subs: set[asyncio.Queue] = set()

    def publish(self, topic: str, type_: str, payload: dict[str, Any]) -> dict:
        self.last_seq = next(self._seq)
        evt = {"seq": self.last_seq, "ts": time.time(), "topic": topic, "type": type_, "payload": payload}
        self._history.append(evt)
        for q in list(self._subs):
            if q.full():
                # A client that stopped reading (a suspended tab, a dead connection): its backlog is dropped and one
                # "gap" marker tells it to resync. Producers are never blocked and never fail (putting the marker AND
                # the event into the one freed slot used to raise QueueFull inside the running task).
                while True:
                    try:
                        q.get_nowait()
                    except asyncio.QueueEmpty:
                        break
                q.put_nowait({"seq": 0, "ts": evt["ts"], "topic": "system", "type": "gap", "payload": {}})
                continue
            q.put_nowait(evt)
        return evt

    def subscribe(self, since: int = 0) -> tuple[asyncio.Queue, list[dict], bool]:
        """(queue, events after `since`, truncated). truncated: the replay buffer no longer reaches back to `since`,
        or `since` is ahead of this process (the app restarted): the client needs the full state instead."""
        q: asyncio.Queue = asyncio.Queue(maxsize=QUEUE_LIMIT)
        self._subs.add(q)
        if since > self.last_seq:
            return q, [], True
        replay = [e for e in self._history if e["seq"] > since]
        oldest = self._history[0]["seq"] if self._history else self.last_seq + 1
        truncated = bool(since and oldest > since + 1)
        return q, ([] if truncated else replay), truncated

    def recent(self, topic: str) -> list[dict]:
        return [e for e in self._history if e["topic"] == topic]

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subs.discard(q)


bus = EventBus()
