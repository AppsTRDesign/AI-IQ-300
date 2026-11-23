"""A git repository with no commit yet: the run result says so (empty git branch, failing checkout)."""
import shutil
import subprocess

import pytest

from app.tools import registry  # noqa: F401 - loads the tool modules in their order
from app.tools.shell_tools import git_unborn_note

pytestmark = pytest.mark.skipif(not shutil.which("git"), reason="git not installed")


def _git(root, *args):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=root, check=True,
                   capture_output=True)


def test_unborn_branch_is_explained(tmp_path):
    _git(tmp_path, "init", "--initial-branch=main")
    note = git_unborn_note(tmp_path, None, "git branch -a", "exit_code=0 state=exited\n")
    assert "no commit yet" in note and "'main'" in note
    err = "error: pathspec 'main' did not match any file(s) known to git"
    assert "no commit yet" in git_unborn_note(tmp_path, ".", 'git checkout main', err)


def test_after_the_first_commit_nothing_is_added(tmp_path):
    _git(tmp_path, "init", "--initial-branch=main")
    (tmp_path / "a.txt").write_text("a")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "first")
    assert git_unborn_note(tmp_path, None, "git branch", "") == ""


def test_other_commands_and_real_output_are_left_alone(tmp_path):
    _git(tmp_path, "init")
    assert git_unborn_note(tmp_path, None, "python a.py", "") == ""
    assert git_unborn_note(tmp_path, None, "git status", "On branch main\nNo commits yet") == ""
