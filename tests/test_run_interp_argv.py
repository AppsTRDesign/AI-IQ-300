"""shell="python" with argv=["-m", "pkg.mod"] means `python -m pkg.mod` (nemotron-3-ultra: "program '-m' is not
installed", nothing ran)."""
import asyncio
from pathlib import Path

from app.tools.registry import TOOLS, ToolContext


def _run(root: Path, args: dict):
    return asyncio.run(TOOLS["run"].fn(ToolContext("t", root, "full", asyncio.Event()), args, ""))


def test_python_flags_in_argv_run_with_python(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "pkg" / "cli.py").write_text("print('cli ran 42')\n", encoding="utf-8")
    res = _run(tmp_path, {"shell": "python", "argv": ["-m", "pkg.cli"]})
    assert res.ok and "cli ran 42" in res.output, res.output


def test_python_script_in_argv_runs_with_python(tmp_path):
    (tmp_path / "hello.py").write_text("print('hello 7')\n", encoding="utf-8")
    res = _run(tmp_path, {"shell": "python", "argv": ["hello.py"]})
    assert res.ok and "hello 7" in res.output, res.output


def test_full_argv_is_left_alone(tmp_path):
    res = _run(tmp_path, {"shell": "python", "argv": ["python", "-c", "print(5 * 5)"]})
    assert res.ok and "25" in res.output, res.output
