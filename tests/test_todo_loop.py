"""Round 2026-11-22e: the to-do list a model can always tick, and never loop on.
nemotron called todo 117 times in 66 turns: every shape it used to tick an item was answered "No change".
Run: python -m pytest tests/test_todo_loop.py"""
import json

from app.agents import tooling
from app.agents.runstate import Run
from app.tools import registry  # noqa: F401

PLAN = ["Google Drive'da 'fatura' geçen dosyaları arama", "Yeni bir Google Sheets tablosu oluşturma",
        "Dosya listesini Sheets'e yazma", "Kullanıcıya sonucu bildirme"]


def _run():
    run = Run.__new__(Run)
    for f, d in Run.__dataclass_fields__.items():
        if d.default_factory is not tooling.__builtins__.get("MISSING", object()) and callable(d.default_factory):
            setattr(run, f, d.default_factory())
        elif d.default is not getattr(__import__("dataclasses"), "MISSING"):
            setattr(run, f, d.default)
    run.todos = [{"content": c, "status": s} for c, s in zip(PLAN, ["completed", "in_progress", "pending", "pending"])]
    return run


def _intent(spec, body=""):
    run = _run()
    spec = dict(spec)
    body = tooling.todo_intent(spec, body, run.todos)
    return spec, body


def test_shapes_models_use_to_tick():
    assert _intent({"id": 2, "status": "completed"})[0]["done"] == [2]
    assert _intent({}, '{"id": "3", "status": "done"}')[0]["done"] == [3]
    spec, body = _intent({}, '{"content": "Yeni bir Google Sheets tablosu oluşturma", "status": "completed"}')
    assert spec["done"] == [2] and body == ""
    assert _intent({"completed": [2, 3]})[0]["done"] == [2, 3]
    assert _intent({"status": "completed"})[0].get("advance") is True
    assert _intent({"item": "step 4", "status": "in_progress"})[0]["start"] == 4
    # the whole list again with new statuses: ticks, not a new plan
    full = json.dumps([{"content": c, "status": "completed"} for c in PLAN[:3]] + [{"content": PLAN[3], "status": "pending"}])
    spec, body = _intent({}, full)
    assert spec["done"] == [1, 2, 3] and body == ""
    # a genuinely new plan stays a new plan
    new = json.dumps([{"content": f"Yeni iş {i}", "status": "pending"} for i in range(4)])
    spec, body = _intent({}, new)
    assert body == new and "done" not in spec


def test_no_change_twice_closes_the_list():
    run = _run()
    r1 = tooling.todo_noop(run, "No change.")
    assert not run.todo_closed and r1.output == "No change."
    r2 = tooling.todo_noop(run, "No change.")
    assert run.todo_closed and "closed" in r2.output and "Do not call todo again" in r2.output
