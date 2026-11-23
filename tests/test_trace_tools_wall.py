"""Parallel tool calls count by wall time in the time split, not by the sum of their durations."""
from app.agents.trace import time_split


def test_parallel_tools_are_wall_time():
    lines = [{"type": "run", "timing": {"tools_ms": 80000}},
             *({"type": "step", "tool": "research", "t": 100.0 + i, "ms": 20000} for i in range(4)),
             {"type": "step", "tool": "write_file", "t": 200.0, "ms": 1000}]
    assert time_split(lines)["tools_s"] == 24.0


def test_without_step_times_the_recorded_sum_is_used():
    assert time_split([{"type": "run", "timing": {"tools_ms": 1500}}])["tools_s"] == 1.5
