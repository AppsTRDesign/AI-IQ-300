"""A stream of only blank lines is a stall (nemotron-3.5-super sent ~5,000 newlines over 14 minutes)."""
import types

import pytest

from app.agents import streaming
from app.llm.providers import ProviderError


def _run():
    return types.SimpleNamespace(stalls=0)


def test_long_whitespace_run_is_cut():
    run, blank = _run(), {"n": 0, "since": 0.0}
    with pytest.raises(ProviderError) as e:
        for _ in range(2000):
            streaming._blank_check(blank, "\n", "m", run)
    assert e.value.code == "stalled" and run.stalls == 1


def test_visible_text_resets_the_count():
    run, blank = _run(), {"n": 0, "since": 0.0}
    for _ in range(50):
        streaming._blank_check(blank, "\n" * 20, "m", run)  # 1,000 blank characters
        streaming._blank_check(blank, "x", "m", run)       # then a real one
    assert run.stalls == 0 and blank["n"] == 0


def test_escaped_blank_in_native_call_arguments_is_cut():
    # a native call's argument deltas are JSON: blank output arrives as the two characters \ n
    run, blank = _run(), {"n": 0, "since": 0.0}
    with pytest.raises(ProviderError):
        for _ in range(2000):
            streaming._blank_check(blank, streaming.re.sub(r"\\[nrt]", " ", "\\n"), "m", run)


def test_after_call_limit_is_well_above_a_normal_note():
    assert streaming.AFTER_CALL_CHARS >= 20000


def test_slow_blank_stream_is_cut_by_time(monkeypatch):
    run, blank = _run(), {"n": 0, "since": 0.0}
    clock = [1000.0]
    monkeypatch.setattr(streaming.time, "monotonic", lambda: clock[0])
    with pytest.raises(ProviderError):
        for _ in range(300):
            clock[0] += 1.0  # one newline a second
            streaming._blank_check(blank, "\n", "m", run)
    assert blank["n"] < streaming.BLANK_CHARS
