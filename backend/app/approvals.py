"""Pending approvals. The backend blocks a tool call until the user answers in the UI.
Each approval is bound to a hash of the exact operation; the executed operation is that same object."""
from __future__ import annotations

import asyncio
import hashlib
import json
import uuid

from .events import bus

_pending: dict[str, tuple[asyncio.Future, str, str]] = {}  # id -> (future, op hash, run id)
_cards: dict[str, dict] = {}  # id -> the request as shown to the user (a client that reconnects gets it again)
APPROVAL_TIMEOUT = 600


def pending_for(run_id: str) -> list[dict]:
    """Approvals of a task that still wait for an answer (for the state a reconnecting client receives)."""
    return [c for aid, c in _cards.items() if c["run_id"] == run_id and aid in _pending and not _pending[aid][0].done()]


def op_hash(op: dict) -> str:
    return hashlib.sha256(json.dumps(op, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]


async def request(run_id: str, op: dict, category: str, reasons: list[str], preview: dict | None = None) -> bool:
    aid = uuid.uuid4().hex[:12]
    digest = op_hash(op)
    fut = asyncio.get_running_loop().create_future()
    _pending[aid] = (fut, digest, run_id)
    card = {"run_id": run_id, "approval_id": aid, "hash": digest, "op": op,
            "category": category, "reasons": reasons, "preview": preview}
    _cards[aid] = card
    bus.publish("run", "approval.request", card)
    try:
        return await asyncio.wait_for(fut, APPROVAL_TIMEOUT)
    except asyncio.TimeoutError:
        return False
    finally:
        _pending.pop(aid, None)
        _cards.pop(aid, None)
        bus.publish("run", "approval.resolved", {"run_id": run_id, "approval_id": aid})


def resolve(aid: str, digest: str, approved: bool) -> bool:
    item = _pending.get(aid)
    if not item or item[1] != digest or item[0].done():
        return False  # unknown, stale or changed operation
    item[0].set_result(approved)
    return True


def cancel_all_for(run_id: str) -> None:
    for fut, _, rid in list(_pending.values()):
        if rid == run_id and not fut.done():
            fut.set_result(False)
