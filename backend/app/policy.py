"""Execution policy: classifies requested side effects and decides allow / ask / deny per permission mode.

This is controlled HOST execution, not an isolation sandbox. Textual classification is advisory:
arbitrary scripts can bypass it. The approval mode is the real gate; the fence below only raises the
bar for obviously destructive commands even in 'full' mode.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

MODES = ("ask", "auto", "full")

# Never executed, regardless of mode or approval.
FORBIDDEN = [
    r"\bformat(\.com)?\s+[a-z]:", r"\bdiskpart\b", r"\bmkfs(\.\w+)?\b", r"\bdd\s+if=.*\bof=/dev/",
    r"\bbcdedit\b", r"\bvssadmin\s+delete\b", r"\bcipher\s+/w\b", r":\(\)\s*\{\s*:\|:&\s*\};:",
    r"\breg\s+delete\s+hk(lm|ey_local_machine)\b", r"Set-ExecutionPolicy\b.*-Scope\s+LocalMachine",
]
# Destructive / sensitive: always require approval, even in 'full' mode (the smart safety fence).
DANGEROUS = [
    r"\brm\s+(-\w*[rf]\w*\s+)+", r"\brmdir\s+/s\b", r"\brd\s+/s\b", r"\bdel\s+(/\w\s+)*.*(/s|/q)",
    r"Remove-Item\b.*-Recurse", r"\bos\.(remove|unlink|rmdir|removedirs)\b", r"\bshutil\.rmtree\b",
    r"\bgit\s+(push\s+.*--force|reset\s+--hard|clean\s+-\w*f)", r"\bshutdown\b", r"\bStop-Computer\b",
    r"\btaskkill\b", r"\bStop-Process\b", r"\breg\s+(add|delete)\b", r"\bnet\s+user\b", r"\bicacls\b",
    r"\btakeown\b", r"\bInvoke-Expression\b|\biex\b", r"\bcurl\b.*\|\s*(sh|bash|iex)", r"\bschtasks\b",
]
NETWORK = [
    r"\b(pip|pip3)\s+install\b", r"\bnpm\s+(i|install|ci|add)\b", r"\b(yarn|pnpm)\s+(add|install)\b",
    r"\bcomposer\s+(install|require)\b", r"\bgit\s+(clone|pull|push|fetch)\b", r"\bcurl\b", r"\bwget\b",
    r"Invoke-WebRequest|Invoke-RestMethod|\biwr\b|\birm\b", r"\bwinget\b|\bchoco\b|\bscoop\b",
]
READ_ONLY = [
    r"^\s*(ls|dir|pwd|cd|echo|type|cat|where|which|whoami|git\s+(status|log|diff|show|branch))\b",
    r"^\s*(python|node|npm|php|git|pip)\s+(-V|--version|-v)\s*$", r"^\s*Get-(ChildItem|Content|Location)\b",
]


@dataclass
class Decision:
    action: str  # allow | ask | deny
    category: str
    reasons: list[str] = field(default_factory=list)


def _match(patterns: list[str], text: str) -> list[str]:
    return [p for p in patterns if re.search(p, text, re.IGNORECASE)]


def classify_command(text: str) -> tuple[str, list[str]]:
    if hits := _match(FORBIDDEN, text):
        return "forbidden", hits
    if hits := _match(DANGEROUS, text):
        return "dangerous", hits
    if hits := _match(NETWORK, text):
        return "network", hits
    if _match(READ_ONLY, text):
        return "read", []
    return "exec", []


def decide_command(text: str, mode: str) -> Decision:
    cat, reasons = classify_command(text)
    if cat == "forbidden":
        return Decision("deny", cat, reasons)
    if cat == "dangerous":
        return Decision("ask", cat, reasons)
    if mode in ("full", "auto") or cat == "read":
        # 'auto': routine build/run/install inside the project are within the user's request.
        return Decision("allow", cat, reasons)
    return Decision("ask", cat, reasons)  # 'ask' mode: confirm anything non-read-only


def resolve_in(base: Path, rel: str, allow_outside: bool = False) -> Path:
    """Resolve a path (following symlinks/junctions) and reject escapes from base unless allowed."""
    base = base.resolve()
    p = Path(rel)
    target = (p if p.is_absolute() else base / p).resolve()
    if not allow_outside and target != base and base not in target.parents:
        raise PermissionError(f"Path escapes workspace: {rel}")
    return target


def decide_file_write(target: Path, workspace: Path, mode: str) -> Decision:
    ws = workspace.resolve()
    if target == ws or ws in target.parents:
        return Decision("ask" if mode == "ask" else "allow", "write")
    return Decision("allow" if mode == "full" else "ask", "external-write", [str(target)])


SAFE_ENV_KEYS = {"PATH", "PATHEXT", "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC", "TEMP", "TMP",
                 "USERPROFILE", "HOMEDRIVE", "HOMEPATH", "APPDATA", "LOCALAPPDATA", "PROGRAMFILES",
                 "PROGRAMFILES(X86)", "PROGRAMDATA", "NUMBER_OF_PROCESSORS", "PROCESSOR_ARCHITECTURE",
                 "HOME", "LANG", "TERM", "OS"}


def minimal_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    """Child processes get a minimal environment; host API keys are not inherited."""
    env = {k: v for k, v in os.environ.items() if k.upper() in SAFE_ENV_KEYS}
    env["PYTHONIOENCODING"] = "utf-8"
    env.update(extra or {})
    return env
