"""Benchmark measures (v0.20.1): three separate scores and where a task's time went."""
import sys
from pathlib import Path

from app.agents import trace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "eval"))
import run_eval  # noqa: E402


def _r(passed, total):
    return {"passed": passed, "total": total, "score": round(passed / total, 3), "full_pass": passed == total}


def test_three_scores_are_kept_apart():
    # 5/8, 3/3, 2/4, 7/7, 5/5 -> per task 82.5 %, per check 22/27 = 81.5 %, fully passed 3/5 = 60 %
    rs = [_r(5, 8), _r(3, 3), _r(2, 4), _r(7, 7), _r(5, 5)]
    s = run_eval.scores(rs)
    assert abs(s["by_task"] - 0.825) < 0.001
    assert (s["checks_passed"], s["checks"]) == (22, 27) and abs(s["by_check"] - 22 / 27) < 0.001
    assert s["full_pass_rate"] == 0.6 and s["full_passed"] == 3


def test_time_split_separates_provider_wait_from_generation():
    lines = [{"type": "run", "timing": {"tools_ms": 4000, "retry_ms": 0, "overhead_ms": 1500}},
             {"type": "turn", "i": 1, "wait_ms": 300000, "total_ms": 320000, "in_tokens": 6000},
             {"type": "turn", "i": 2, "wait_ms": 10000, "total_ms": 30000, "in_tokens": 8000},
             {"type": "turn", "i": 3, "wait_ms": 2000, "total_ms": 2500, "in_tokens": 100}]  # too small to rate
    x = trace.time_split(lines)
    assert x["wait_s"] == 312.0 and x["gen_s"] == 40.5 and x["tools_s"] == 4.0 and x["app_s"] == 1.5
    assert x["max_wait_s"] == 300.0
    assert x["wait_per_1k"] == 50.0  # median of 50 s/1K and 1.25 s/1K (upper middle of two)
    assert trace.summary(lines)["wait_s"] == 312.0


def test_time_split_without_turns_falls_back_to_timing():
    x = trace.time_split([{"type": "run", "timing": {"model_wait_ms": 5000, "model_ms": 9000, "slowest_wait_ms": 4000}}])
    assert x["wait_s"] == 5.0 and x["gen_s"] == 4.0 and x["max_wait_s"] == 4.0 and x["wait_per_1k"] is None
