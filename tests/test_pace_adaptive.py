"""A 429 while paced lowers the provider's per-minute cap for a while (another user of the same key)."""
import time

from app.llm import usage


def test_429_lowers_the_cap_then_it_recovers(monkeypatch):
    pid = "test-prov"
    usage._SENT[pid] = [time.time() - i for i in range(20)]  # 20 requests in the last minute, then a 429
    usage._LOWER.pop(pid, None)
    assert usage.effective_rpm(pid, 40) == 40
    usage.note_rate_limit(pid, 40)
    low = usage.effective_rpm(pid, 40)
    assert 2 <= low <= 15
    usage.note_rate_limit(pid, 40)  # another 429: lower again, never below 2
    assert 2 <= usage.effective_rpm(pid, 40) <= low
    real = time.time
    monkeypatch.setattr(usage.time, "time", lambda: real() + 601)
    assert usage.effective_rpm(pid, 40) == 40
    usage._SENT.pop(pid, None)
    usage._LOWER.pop(pid, None)
