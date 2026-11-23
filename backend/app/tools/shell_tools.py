"""Commands and servers: run, start, stop - shells, PowerShell 5.1 shims, argv building, ports, the real places of missing files and the lines around a reported error.

Split out of registry.py (round 2026-11-20). registry imports this module at its end and re-exports every name, so registry.X keeps working; import tools from registry, not from here."""
from __future__ import annotations
import asyncio
import base64
import hashlib
import json
import os
import re
import shlex
import shutil
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Awaitable, Callable
from .. import approvals, policy
from ..config import LANG_DIR, load_settings
from ..process_manager import manager

from .registry import S, SHELLS, ToolContext, ToolResult, _path, _rel, clip, gate, tool  # noqa: F401


def _did_you_mean(ctx, name: str) -> str:
    """Up to five paths in the working folder with the same file / folder name (for a not-found answer)."""
    from ..workspace import IGNORED
    if not name:
        return ""
    hits: list[str] = []
    seen = 0
    low = name.lower()
    for d, dirs, files in os.walk(ctx.root):
        dirs[:] = [x for x in dirs if x not in IGNORED]
        seen += len(dirs) + len(files)
        hits += [_rel(ctx, Path(d) / x) for x in dirs + files if x.lower() == low]
        if len(hits) >= 5 or seen > 20000:  # a huge folder: stop looking, the hint is only a help
            break
    hits = hits[:5]
    return (". It exists at: " + ", ".join(hits) + " (use that path)") if hits else ""


DEFAULT_SHELL = "powershell" if sys.platform == "win32" else "bash"


POWERSHELLS = ("powershell", "powershell5", "pwsh")


# Python scripts run with the app's own interpreter (its packages: Pillow, python-docx, openpyxl, reportlab...).
PYTHON = sys.executable or "python"


SCRIPT_SHELLS = {"powershell": ".ps1", "powershell5": ".ps1", "pwsh": ".ps1", "python": ".py", "node": ".js", "php": ".php",
                 "bash": ".sh"}


# A bash heredoc (cat > f <<'EOF' ... EOF, python - <<EOF ...) is bash syntax: PowerShell and cmd fail on it.
HEREDOC = re.compile(r"<<-?[ \t]*(['\"]?)([A-Za-z_][\w-]*)\1[^\n]*\n(?:.*\n)*?[ \t]*\2[ \t]*(?:\n|$)")


# PowerShell here-strings must close at the start of a line ('@ / "@); models often indent the closing mark.
HERE_CLOSE = re.compile(r"(?m)^[ \t]+(['\"]@)")


def route_heredoc(shell: str, command: str) -> tuple[str, str]:
    """A bash heredoc sent to PowerShell/cmd runs in bash (Git Bash on Windows), where it means what the model wrote.
    Without bash, a simple 'cat > file <<EOF' becomes a PowerShell file write and other heredocs are piped as input."""
    if shell not in POWERSHELLS + ("cmd",) or not HEREDOC.search(command):
        return shell, command
    from ..hostinfo import git_bash
    if git_bash():
        return "bash", command
    lines, out, i = command.split("\n"), [], 0
    while i < len(lines):
        m = re.search(r"^(.*?)<<-?[ \t]*(['\"]?)([A-Za-z_][\w-]*)\2(.*)$", lines[i])
        end = next((k for k in range(i + 1, len(lines)) if lines[k].strip() == (m.group(3) if m else None)), None)
        if not m or end is None:
            out.append(lines[i])
            i += 1
            continue
        body = "\n".join(lines[i + 1:end]) + "\n"
        head, tail = m.group(1).strip(), m.group(4).strip()
        literal = "@'\n" + body.replace("\n'@", "\n '@") + "'@"
        redirect = re.search(r"(>>?)\s*(\S+)", head + " " + tail)
        if head in ("cat", "tee") or (head.startswith(("cat", "tee")) and redirect):
            path = redirect.group(2) if redirect else ""
            verb = "Add-Content" if redirect and redirect.group(1) == ">>" else "Set-Content"
            out.append(f"{verb} -LiteralPath '{path}' -Encoding utf8 -Value {literal}" if path else f"Write-Output {literal}")
        else:
            out.append(f"{literal} | {head} {tail}".strip())
        i = end + 1
    return "powershell" if shell == "cmd" else shell, "\n".join(out)


def _powershell(shell: str) -> tuple[str, bool]:
    """(executable, is PowerShell 7+): powershell = pwsh when installed, powershell5 = Windows PowerShell 5.1."""
    pwsh = shutil.which("pwsh")
    if shell == "pwsh" or (shell == "powershell" and pwsh):
        if pwsh:
            return pwsh, True
    return shutil.which("powershell") or "powershell", False


# Windows PowerShell 5.1 (the built-in one) has no && / || and its aliases reject the Unix/cmd habits models write
# (rm -rf, del /s /q, rmdir /s /q, mkdir -p a b, ls -la, touch). The shims below step in ONLY for such arguments;
# native use (Remove-Item -Recurse, ls -Filter *.txt, dir | Where-Object ...) goes to the real cmdlet unchanged.
# One deliberate exception: mkdir of a folder that already exists succeeds (like mkdir -p), so chains such as
# 'mkdir app && cd app && ...' work the second time too.
PS_SHIM = r"""$ErrorActionPreference = 'Continue'
try { [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false } catch {}
$OutputEncoding = New-Object System.Text.UTF8Encoding $false
foreach ($__c in 'Get-Content','Import-Csv','Select-String') { $PSDefaultParameterValues["${__c}:Encoding"] = 'UTF8' }
foreach ($__a in 'rm','rmdir','rd','del','erase','mkdir','md','ls','dir','touch') { Remove-Item "Alias:$__a" -Force -ErrorAction SilentlyContinue }
$global:__aiiq_failed = $false; $global:__aiiq_err = $false
function global:__aiiq_isflag($x) { "$x" -cmatch '^(--?[A-Za-z][A-Za-z0-9-]*|/[a-zA-Z])$' }
# Native use: every flag is a real parameter of the cmdlet, and either a flag is given or there is at most one path.
function global:__aiiq_native($a, $known) { $n = 0; foreach ($x in $a) { if (__aiiq_isflag $x) { if ("$x" -notmatch $known) { return $false }; $n++ } }; return ($n -gt 0 -or @(__aiiq_paths $a).Count -le 1) }
function global:__aiiq_paths($a) { @($a | Where-Object { -not (__aiiq_isflag $_) }) }
function global:__aiiq_rm($a) { $f = @($a | Where-Object { __aiiq_isflag $_ }) -join ' '; $quiet = $f -match '(^|\s)(-\w*f\w*|--force|/[qQ])'; foreach ($x in (__aiiq_paths $a)) { if (Test-Path -Path $x) { Remove-Item -Path $x -Recurse -Force } elseif (-not $quiet) { Write-Error "rm: not found: $x"; $global:__aiiq_err = $true } } }
$global:__aiiq_rmnative = '^-(Path|LiteralPath|Filter|Include|Exclude|Recurse|Force|Confirm|WhatIf|ErrorAction|Stream|Credential|r|R|f)$'
function rm { if (__aiiq_native $args $__aiiq_rmnative) { Microsoft.PowerShell.Management\Remove-Item @args; if (-not $?) { $global:__aiiq_err = $true } } else { __aiiq_rm $args } }
function rmdir { rm @args }
function rd { rm @args }
function del { rm @args }
function erase { rm @args }
function mkdir { $p = @(__aiiq_paths $args); if (-not ($args | Where-Object { __aiiq_isflag $_ }) -and $p.Count -eq 1 -and (Test-Path -LiteralPath $p[0] -PathType Container)) { return }; if (__aiiq_native $args '^-(Path|Name|Force|Value|Confirm|WhatIf|ErrorAction)$') { New-Item -ItemType Directory @args; if (-not $?) { $global:__aiiq_err = $true } } else { foreach ($x in $p) { New-Item -ItemType Directory -Force -Path $x | Out-Null } } }
function md { mkdir @args }
function touch { foreach ($x in (__aiiq_paths $args)) { if (Test-Path -LiteralPath $x) { (Get-Item -LiteralPath $x).LastWriteTime = Get-Date } else { New-Item -ItemType File -Path $x -Force | Out-Null } } }
function ls { if (__aiiq_native $args '^-(Path|LiteralPath|Filter|Include|Exclude|Recurse|Depth|Force|Name|File|Directory|Hidden|ReadOnly|System|Attributes|ErrorAction)$') { Microsoft.PowerShell.Management\Get-ChildItem @args; if (-not $?) { $global:__aiiq_err = $true } } else { $f = @($args | Where-Object { __aiiq_isflag $_ }) -join ' '; $p = __aiiq_paths $args; $a = @{}; if ($f -match '(^|\s)(-\w*a\w*|/a)') { $a.Force = $true }; if ($f -cmatch '(^|\s)(-\w*R\w*|/s)') { $a.Recurse = $true }; if ($p.Count) { Microsoft.PowerShell.Management\Get-ChildItem -Path $p @a } else { Microsoft.PowerShell.Management\Get-ChildItem @a } } }
function dir { ls @args }
# head / tail / wc do not exist in PowerShell ('rea-video --help 2>&1 | head -20', 'wc -l index.html' failed), and
# 'curl -s URL' hit the Invoke-WebRequest alias ("missing mandatory parameters: Uri"): the real curl.exe answers instead.
function global:__aiiq_nargs($a) { $n = 10; $f = @(); for ($i = 0; $i -lt $a.Count; $i++) { $x = "$($a[$i])"; if ($x -ceq '-n' -and $i + 1 -lt $a.Count) { $i++; $n = [int]"$($a[$i])".TrimStart('+') } elseif ($x -match '^-n?(\d+)$') { $n = [int]$Matches[1] } elseif ($x -match '^--lines=(\d+)$') { $n = [int]$Matches[1] } elseif ($x -notmatch '^-') { $f += $x } }; return @{ n = $n; files = $f } }
function head { $p = __aiiq_nargs $args; if ($p.files.Count) { foreach ($x in $p.files) { Get-Content -LiteralPath $x -TotalCount $p.n } } else { $input | Select-Object -First $p.n } }
function tail { $p = __aiiq_nargs $args; if ($p.files.Count) { foreach ($x in $p.files) { Get-Content -LiteralPath $x -Tail $p.n } } else { $input | Select-Object -Last $p.n } }
function wc { $f = (@($args | Where-Object { "$_" -match '^-[lwcm]+$' }) -join ''); $files = @($args | Where-Object { "$_" -notmatch '^-' }); $one = { param($t, $name) $o = @(); if (-not $f -or $f -match 'l') { $o += @($t).Count }; if (-not $f -or $f -match 'w') { $o += @((@($t) -join ' ') -split '\s+' | Where-Object { $_ }).Count }; if (-not $f -or $f -match '[cm]') { $o += (@($t) -join "`n").Length }; (($o -join ' ') + " $name").Trim() }; if ($files.Count) { foreach ($x in $files) { & $one @(Get-Content -LiteralPath $x) $x } } else { & $one @($input) '' } }
if (Get-Command curl.exe -CommandType Application -ErrorAction SilentlyContinue) { Remove-Item Alias:curl -Force -ErrorAction SilentlyContinue }
"""


# A program run with 2>&1 that only logged to stderr (INFO lines) and exited 0: Windows PowerShell 5.1 turns each stderr
# line into a NativeCommandError record and sets $? to false, so 'rea-video decompose ... 2>&1' (done, report written)
# came back as exit 1 / failed and the model and the app called a finished step broken. Such a run is a success.
PS_NATIVE_OK = "($LASTEXITCODE -eq 0 -and $Error.Count -gt 0 -and \"$($Error[0].FullyQualifiedErrorId)\" -like 'NativeCommandError*')"

# The script's exit code: Windows PowerShell exits 0 even when the last native command failed.
PS_TRAILER = r"""
$__ok = $? -or """ + PS_NATIVE_OK + r"""
if ($global:__aiiq_failed -or $global:__aiiq_err -or -not $__ok) { if ($LASTEXITCODE) { exit $LASTEXITCODE } else { exit 1 } }
"""


def _split_chain(line: str) -> list[str] | None:
    """Split a line at top-level && / || (outside quotes): [cmd, op, cmd, op, cmd...] or None."""
    parts, buf, quote, i = [], "", "", 0
    while i < len(line):
        ch = line[i]
        if quote:
            quote = "" if ch == quote else quote
        elif ch in "'\"":
            quote = ch
        elif line[i:i + 2] in ("&&", "||"):
            parts += [buf.strip(), line[i:i + 2]]
            buf, i = "", i + 2
            continue
        buf += ch
        i += 1
    if len(parts) < 2 or not buf.strip() or any(not x for x in parts[::2]):
        return None
    return parts + [buf.strip()]


def ps_chain(line: str) -> str:
    """'a && b || c' -> PowerShell 5.1 statements with the shell's left-to-right short-circuit meaning."""
    parts = _split_chain(line)
    if not parts:
        return line
    ok = f"$__s = ($? -or {PS_NATIVE_OK}) -and -not $global:__aiiq_err"  # the shims above report their own failures
    out = f"{parts[0]}; {ok}"
    for op, seg in zip(parts[1::2], parts[2::2]):
        out += f"; if ({'' if op == '&&' else '-not '}$__s) {{ $global:__aiiq_err = $false; {seg}; {ok} }}"
    return out + "; $global:__aiiq_failed = -not $__s"


# "Remove-Item x -ErrorAction SilentlyContinue", "Get-Command ruflo -ea 0", "ls a, b 2>$null": the error was silenced
# on purpose (delete if there, look if it exists), yet PowerShell still sets $? to false and the run came back as
# exit 1 / failed - the app then started debugging and held the final answer as "the last command failed".
PS_QUIET = re.compile(r"-(?:ErrorAction|EA)\s*:?\s*(?:SilentlyContinue|Ignore|0)\b|\b2>\s*\$null\b|\*>\s*\$null\b", re.I)


def _last_statement(command: str) -> str:
    lines = [l for l in command.strip().split("\n") if l.strip() and not l.strip().startswith("#")]
    return (lines[-1].rsplit(";", 1)[-1] if lines else "")


def ps_script(command: str, pwsh: bool) -> str:
    """Script text for PowerShell: compatibility shims, && / || chains (5.1 only) and a real exit code."""
    quiet = bool(PS_QUIET.search(_last_statement(command)))
    if not pwsh and "@'" not in command and '@"' not in command:  # here-strings stay as written
        command = "\n".join(ps_chain(l) if ("&&" in l or "||" in l) and not l.rstrip().endswith("`") else l
                            for l in command.split("\n"))
    if quiet:  # a silenced cmdlet error is not a failure; a native program's own exit code still counts
        return (PS_SHIM + _bash_shim() + command
                + "\nif ($LASTEXITCODE -and -not $global:__aiiq_failed) { exit $LASTEXITCODE }"
                + "\nif ($global:__aiiq_failed) { exit 1 }\nexit 0\n")
    return PS_SHIM + _bash_shim() + command + PS_TRAILER


def _bash_shim() -> str:
    """'bash script.sh' typed in PowerShell runs System32\\bash.exe (WSL): with no Linux installed it printed a
    UTF-16 "no distribution installed" message read as 'L i n u x  i ç i n ...' and failed. Git Bash runs it instead."""
    if sys.platform != "win32":
        return ""
    from ..hostinfo import git_bash
    gb = git_bash()
    if not gb:
        return ""
    gb = gb.replace("'", "''")
    return f"function bash {{ & '{gb}' @args }}\nfunction sh {{ & '{gb}' @args }}\n"


# One command line for a program (not source code of the language): "python --version", "node -v", "pip install x".
CLI_LINE = re.compile(r"\s*(python3?|py|pip3?|node|npm|npx|php|composer|git|winget|choco|scoop|dotnet|java|go|cargo|"
                      r"deno|bun|yarn|pnpm|where|which)(\.exe)?(\s+-{1,2}[\w-]+|\s+[\w./:\\-]+)*\s*$", re.I)


SCRIPT_ONLY = re.compile(r"\s*(?:\.[\\/])?([\w./\\-]+\.(py|php|js|mjs|cjs|ts|rb|pl|ps1|sh))((?:[ \t]+[^\n|&;<>]+)?)\s*",
                         re.I)


CD_ONLY = re.compile(r"\s*(?:cd|chdir|Set-Location|sl|pushd)(?:\s+/d)?\s+(?:-Path\s+)?(['\"]?)([^'\";&|<>\r\n]+?)\1\s*;?\s*")


PY_START = re.compile(r"(?:import [A-Za-z_][\w.]*(?:\s*,\s*[\w.]+)*(?: as \w+)?|from [A-Za-z_.][\w.]* import .+"
                      r"|def \w+\(.*\):|class \w+.*:|async def \w+\(.*\):)\s*$")


PS_HINT = re.compile(r"(?m)^\s*(?:\$\w+\s*=|[A-Z][a-z]+-[A-Z]\w+\b|param\s*\()")


FFMPEG_NO_Y = re.compile(r"(?m)(?:^|(?<=[;&|(]))\s*(?:&\s*)?[\"']?(?:[\w:\\/. -]*[\\/])?ffmpeg(?:\.exe)?[\"']?(?=\s)(?![^\n;&|]*\s-[yn]\b)")


def looks_python(command: str) -> bool:
    """Multi-line Python source (it starts with an import/def/class line and has no PowerShell syntax)."""
    lines = [ln for ln in command.strip().splitlines() if ln.strip() and not ln.lstrip().startswith("#")]
    return len(lines) > 1 and bool(PY_START.match(lines[0].strip())) and not PS_HINT.search(command)         and "<<" not in command


# pip / pip3 / python -m pip / py -m pip / python3 -m pip at the start of a command or after ; && || | (
PIP_CALL = re.compile(r"(?P<pre>^|[;&|(]\s*|\n\s*)(?:(?:python3?|py)(?:\.exe)?\s+(?:-\d(?:\.\d+)?\s+)?-m\s+pip3?|pip3?(?:\.exe)?)"
                      r"(?=\s)", re.I)


def venv_pip(command: str, shell: str) -> str:
    """Every pip call goes into the app's own Python environment (.venv): scripts run with shell="python" use that
    interpreter, so a package a model installed with a bare `pip` (the system Python's, a Store alias, another
    version) was missing there. The rewrite holds in PowerShell, cmd and bash, inside chains (a && pip install b)."""
    exe = PYTHON.replace("\\", "/") if shell == "bash" else PYTHON
    quoted = f"& \"{exe}\"" if shell in POWERSHELLS else f"\"{exe}\""

    def repl(m: re.Match) -> str:
        pre = m.group("pre")
        call = quoted if not (shell in POWERSHELLS and pre.strip()) else f"& \"{exe}\""
        return f"{pre}{call} -m pip"
    return PIP_CALL.sub(repl, command)


# One program call whose output goes to a file ("& "C:\...\adb.exe" exec-out screencap -p > shot.png"): no pipeline,
# no PowerShell variables or sub-expressions, so cmd runs it the same way.
NATIVE_REDIRECT = re.compile(
    r"(?:&\s*)?((?:\"[^\"]+\.(?:exe|com|bat|cmd)\"|[^\s\"|;$`()]+\.(?:exe|com)|adb|ffmpeg|ffprobe|sqlite3|git|"
    r"pg_dump|mysqldump|openssl|magick|convert)(?=\s))([^|;$`(){}\n]*?\s\d?>{1,2}\s*(?:\"[^\"]+\"|[^\s\"|;]+))", re.I)


def build_argv(ctx: ToolContext, shell: str, command: str) -> list[str]:
    """Turn a shell + command into an argv vector. Script shells use an explicit script file."""
    shell = (shell or DEFAULT_SHELL).lower()
    if shell != "python" and "ffmpeg" in command:
        # ffmpeg asks "File exists. Overwrite? [y/N]" and, with no input, gives up: models then delete files or
        # report a video that was never made. -y overwrites (a command that says -n keeps its choice).
        command = FFMPEG_NO_Y.sub(lambda m: m.group(0) + " -y", command)
    if shell == "python" and "\n" not in command.strip():
        # Models often send a shell line to the python "shell" ("python app.py", "app.py arg", "pip install x"),
        # which would run as Python source and fail: run it as the command it is.
        line = command.strip()
        if m := re.fullmatch(r"(?:(?:python3?|py)(?:\.exe)?\s+)?([\w./\\:-]+\.py)((?:\s+.*)?)", line, re.I):
            return [PYTHON, m.group(1), *shlex.split(m.group(2) or "", posix=sys.platform != "win32")]
        if m := re.fullmatch(r"(?:python3?|py)(?:\.exe)?\s+(-m\s+.+|-c\s+.+)", line, re.I):
            return [PYTHON, *shlex.split(m.group(1))]  # posix: quotes around -c code are removed
        if m := re.fullmatch(r"pip3?\s+(.+)", line, re.I):
            return [PYTHON, "-m", "pip", *shlex.split(m.group(1), posix=sys.platform != "win32")]
    if shell in POWERSHELLS + ("cmd", "bash") and looks_python(command):
        shell = "python"  # Python source sent without shell="python" (it failed as PowerShell before)
    if shell in POWERSHELLS + ("cmd", "bash"):
        command = venv_pip(command, shell)
    if sys.platform != "win32" and shell in POWERSHELLS + ("cmd",) and not shutil.which("pwsh"):
        shell = "bash"  # Linux/macOS without PowerShell: run the command in bash
    shell, command = route_heredoc(shell, command)
    if sys.platform == "win32" and shell in POWERSHELLS and (m := NATIVE_REDIRECT.fullmatch(command.strip())):
        # Windows PowerShell's ">" re-encodes a program's output as UTF-16 text: `adb exec-out screencap -p >
        # shot.png` wrote a broken PNG. cmd redirects the bytes as they are.
        shell, command = "cmd", m.group(1) + m.group(2)
    if shell in POWERSHELLS:
        command = HERE_CLOSE.sub(r"\1", command)
    if shell == "bash":
        from ..hostinfo import git_bash
        bash = git_bash() or "bash"
        if "\n" not in command.strip():
            return [bash, "-c", command]  # no login shell: profile scripts make every command slower
    if shell in SCRIPT_SHELLS:
        scripts = (ctx.session_dir or ctx.root / ".aiiq") / "scripts"
        scripts.mkdir(parents=True, exist_ok=True)
        f = scripts / f"{hashlib.sha256(f'{shell}:{command}'.encode()).hexdigest()[:12]}{SCRIPT_SHELLS[shell]}"
        if shell in POWERSHELLS:
            exe, seven = _powershell(shell)
            f.write_text(ps_script(command, seven), encoding="utf-8-sig")
            return [exe, "-NoLogo", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(f)]
        f.write_text(command if shell != "bash" else command.replace("\r\n", "\n"), encoding="utf-8", newline="\n")
        if shell == "bash":
            return [bash, str(f)]
        return [PYTHON if shell == "python" else shell, str(f)]
    if shell == "cmd":
        return ["cmd", "/d", "/s", "/c", command]
    argv = shlex.split(command, posix=sys.platform != "win32")  # "exec": direct argv
    if sys.platform == "win32":  # non-posix split keeps the quotes: "app\x.apk" must reach the program without them
        argv = [_unquote_arg(a) for a in argv]
    if argv and argv[0].lower() in ("python", "python3", "py"):
        argv[0] = PYTHON
    elif argv and argv[0].lower() in ("pip", "pip3"):
        argv[:1] = [PYTHON, "-m", "pip"]
    return argv


INSTALL_HINT = {
    "gh": "winget install --id GitHub.cli -e (macOS: brew install gh; Linux: apt install gh); it also needs `gh auth "
          "login` - without sign-in use fetch_url https://api.github.com/search/repositories?q=... instead",
    "git": "winget install --id Git.Git -e (macOS: xcode-select --install; Linux: apt install git), or download the "
           "repository ZIP with fetch_url save=...",
    "node": "winget install OpenJS.NodeJS.LTS (brew install node; apt install nodejs npm)",
    "npm": "winget install OpenJS.NodeJS.LTS (brew install node; apt install nodejs npm)",
    "npx": "winget install OpenJS.NodeJS.LTS (brew install node; apt install nodejs npm)",
    "php": "winget install PHP.PHP.8.3 (brew install php; apt install php-cli)",
    "composer": "the app installs Composer by itself when PHP is present; or brew install composer / apt install composer",
    "dotnet": "winget install Microsoft.DotNet.SDK.8 (brew install --cask dotnet-sdk; apt install dotnet-sdk-8.0)",
    "ffmpeg": "the app downloads ffmpeg by itself; or winget install Gyan.FFmpeg / brew install ffmpeg / apt install ffmpeg",
    "docker": "Docker Desktop (winget install Docker.DockerDesktop) - ask the user first",
    "wget": "not needed: use fetch_url url=... save=... (or curl.exe -L -o file URL)",
    "unzip": "not needed: use tar -xf file.zip (Windows 10+, macOS, Linux) or Expand-Archive",
    "make": "run the Makefile's steps one by one, or install it (choco install make / brew install make)",
    "go": "winget install GoLang.Go (brew install go; apt install golang)",
    "cargo": "winget install Rustlang.Rustup (curl https://sh.rustup.rs -sSf | sh)",
    "java": "winget install EclipseAdoptium.Temurin.21.JDK (brew install --cask temurin)",
    "ruby": "winget install RubyInstallerTeam.RubyWithDevKit.3.3 (brew install ruby)",
    "flutter": "see the mobile-app-test skill (Flutter SDK)",
    "adb": "Android platform-tools: see the mobile-app-test skill",
}


def _unquote_arg(x: str) -> str:
    """One argv item without the shell quoting a model wrapped around it: "\"a b\"" / '\\"a b\\"' / "'a b'" -> a b."""
    y = x.strip()
    m = re.fullmatch(r"(\\*[\"'])(.*)\1", y, re.S)
    while m and len(y) > 2:
        y = m.group(2)
        m = re.fullmatch(r"(\\*[\"'])(.*)\1", y, re.S)
    return y if y != x.strip() else x


def _shell_join(shell: str, argv: list[str]) -> str:
    """One command line for that shell from separate arguments (each stays one argument: spaces, (tabs) folders)."""
    if shell == "bash":
        return " ".join(shlex.quote(a) for a in argv)
    if shell == "cmd":
        return " ".join(a if re.fullmatch(r"[\w./\\:=-]+", a) else '"' + a.replace('"', '""') + '"' for a in argv)
    # PowerShell: parameter names (-Path) stay bare; anything else with special characters goes in single quotes.
    return " ".join(a if re.fullmatch(r"-\w+|[\w./\\:=-]+", a) else "'" + a.replace("'", "''") + "'" for a in argv)


async def _spawn(ctx: ToolContext, args: dict, body: str, background: bool):
    command = body.strip()
    shell = args.get("shell") or DEFAULT_SHELL
    direct = args.get("argv")
    if isinstance(direct, str) and direct.strip().startswith("["):
        try:
            direct = json.loads(direct)
        except ValueError:
            direct = None
    if isinstance(direct, list) and direct and all(isinstance(x, (str, int, float)) for x in direct):
        # A program with its arguments, started directly: no shell parsing, no quoting problems, fastest start.
        # Each item is already one argument: shell quotes a model wrapped around it ("\"simple cli\"", '\\"x\\"')
        # would reach the program as part of the text.
        direct = [_unquote_arg(str(x)) for x in direct]
        asked_shell = args.get("shell")
        interp = {"python": "python", "node": "node", "php": "php"}.get(asked_shell or "")
        if interp and Path(direct[0]).stem.lower() not in (interp, "python3", "py", "nodejs") \
                and (direct[0].startswith("-") or Path(direct[0]).suffix.lower() in (".py", ".js", ".mjs", ".cjs", ".php")):
            # shell="python" argv=["-m", "shop.cli"] means `python -m shop.cli`: "-m" was taken for a program
            # ("program '-m' is not installed", nemotron-3-ultra). The interpreter the shell names comes first.
            direct = [interp, *direct]
        if (asked_shell in ("bash", "powershell", "powershell5", "pwsh", "cmd")
                and not shutil.which(direct[0], path=policy.minimal_env().get("PATH"))
                and not Path(direct[0]).is_file()):
            # argv=["Move-Item", ...] with shell=powershell, argv=["mv", ...] with shell=bash: a cmdlet or a shell
            # command is no program on PATH, so started directly it "is not installed" and nothing ran. It belongs
            # to the shell that was named: run it there, each argument quoted for that shell.
            shell, command, direct = asked_shell, _shell_join(asked_shell, direct), None
        else:
            shell, command = "exec", " ".join(shlex.quote(x) if " " in x else x for x in direct)
    if not command:
        return None, ToolResult(False, "Give the command (or argv=[program, args...]).")
    if shell in ("python", "node", "php") and CLI_LINE.match(command) and "\n" not in command.strip():
        # A command line ("python --version", "pip install x") sent with shell=python would run as Python source
        # (NameError): it belongs to the system shell.
        shell = DEFAULT_SHELL
    cwd = _path(ctx, args.get("cwd") or ctx.shell_cwd or ".")
    if shell in ("python", "node", "php") and re.match(r"\s*-{1,2}[A-Za-z]", command) and "\n" not in command.strip():
        # shell=php with "-S 127.0.0.1:8000": the flags were run as PHP code, the "server" exited at once, and the
        # model concluded that servers cannot run here. They are the interpreter's arguments.
        command, shell = f"{'php' if shell == 'php' else 'node' if shell == 'node' else PYTHON} {command.strip()}", \
            DEFAULT_SHELL
        if shell == "powershell" and command.startswith(PYTHON):
            command = f'& "{PYTHON}"' + command[len(PYTHON):]
    if shell in ("python", "node", "php") and (sm := SCRIPT_ONLY.fullmatch(command)) and (cwd / sm.group(1)).is_file():
        # shell=php with "database.php" as the code: PHP printed the text "database.php" and nothing ran (exit 0).
        # The model meant the file: run it from the system shell with its interpreter (below).
        shell = DEFAULT_SHELL
    if shell in ("powershell", "cmd", "bash") and (sm := SCRIPT_ONLY.fullmatch(command)) \
            and (cwd / sm.group(1)).is_file():
        # "create_db.php" alone: Windows only opens the file with its associated app (exit 0, nothing ran) and a
        # weak model ran it 15 times wondering why the tables never appeared. Run it with its interpreter.
        ext = sm.group(2).lower()
        interp = {"py": ("& " if shell == "powershell" else "") + f'"{PYTHON}"',"php": "php", "js": "node", "mjs": "node", "cjs": "node", "ts": "npx tsx",
                  "rb": "ruby", "pl": "perl", "sh": "bash"}.get(ext)
        if ext == "ps1":
            command = f"& ./{sm.group(1)}" if shell == "powershell" else f"powershell -File {sm.group(1)}"
        elif interp:
            command = f"{interp} {sm.group(1)}" + (sm.group(3) or "")
    if shell in ("powershell", "cmd", "bash") and (m := CD_ONLY.fullmatch(command)):
        # Each command runs in its own process, so a lone "cd" would change nothing: remember it instead,
        # like a terminal does, and run the following commands there.
        want = m.group(2).strip().strip("'\"")
        target = _path(ctx, str(cwd / want))
        if not target.is_dir():
            # list_dir shows paths from the task folder, so a model writes "cd app" again while already in app/:
            # take the path from the task folder too, and say plainly when it is the folder we are in.
            from_root = _path(ctx, want)
            if from_root.is_dir():
                target = from_root
            elif cwd.name.lower() == Path(want.rstrip("/\\")).name.lower():
                return None, ToolResult(True, f"already in {_rel(ctx, cwd)}: commands run here now (no cd needed)")
            else:
                return None, ToolResult(False, f"cd: no such folder: {want} (commands run in {_rel(ctx, cwd)})"
                                        + _did_you_mean(ctx, Path(want.rstrip('/\\')).name))
        ctx.shell_cwd = str(target)
        return None, ToolResult(True, f"working folder for the next commands: {_rel(ctx, target)} (list_dir / read_file "
                                      "paths still start at the task folder)")
    op = {"tool": "start" if background else "run", "shell": shell, "cwd": str(cwd), "command": command}
    if msg := await gate(ctx, op, policy.decide_command(command, ctx.mode)):
        return None, ToolResult(False, msg)
    env = policy.minimal_env()  # the PATH as it is now (a program installed a moment ago is found)
    try:  # the app's Android / Kotlin toolchain (data/mobile): gradle, adb, emulator, sdkmanager work in commands
        from . import mobile
        mobile.add_to_run_env(env)
    except Exception:  # noqa: BLE001 - optional
        pass
    # Python scripts read other programs' output as UTF-8 and print UTF-8: with the Windows code page, a script that
    # ran php printed "VeritabanÄ± baÅŸarÄ±yla" (Turkish text decoded twice).
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    # Java programs (Maestro, Gradle's client, sdkmanager) print with the Windows code page: Maestro showed "Tanmsz"
    # for "Tanımsız" and 'Tap on ""' for ÷. Their start scripts read JAVA_OPTS (silently, unlike JAVA_TOOL_OPTIONS,
    # which prints a note on every start): UTF-8 output, the same as everything else the app reads.
    env.setdefault("JAVA_OPTS", "-Dfile.encoding=UTF-8 -Dstdout.encoding=UTF-8 -Dstderr.encoding=UTF-8 "
                                "-Dsun.stdout.encoding=UTF-8 -Dsun.stderr.encoding=UTF-8")
    if isinstance(direct, list) and direct and shell == "exec":
        argv = list(direct)
        exe = shutil.which(argv[0], path=env.get("PATH"))
        if Path(argv[0]).stem.lower() in ("pip", "pip3"):
            argv = [PYTHON, "-m", "pip", *argv[1:]]  # packages always go into the app's .venv (see venv_pip)
        elif argv[0].lower() in ("python", "python3", "py"):
            argv[0] = PYTHON
        elif exe:
            argv[0] = exe  # resolves npm -> npm.cmd on Windows
        elif not Path(argv[0]).is_file() and not (cwd / argv[0]).is_file():
            # Not on PATH: say so in plain words (the OS said only "WinError 2: the system cannot find the file").
            name = Path(argv[0]).stem.lower()
            how = INSTALL_HINT.get(name, "")
            return None, ToolResult(False, f"program '{argv[0]}' is not installed or not on PATH, so nothing ran."
                                    + (f" Install it: {how}." if how else " Install it (winget / brew / apt / npm / pip)")
                                    + " Or take another route that needs no extra program (fetch_url for web / GitHub "
                                    "API and downloads, tar for archives, python for scripts).")
    else:
        argv = build_argv(ctx, shell, command)
    ctx.commands.append(command)
    timeout = None if background else float(args.get("timeout") or load_settings()["agent"]["command_timeout"])
    info = await manager.start(argv, str(cwd), env, owner=ctx.owner or ctx.run_id, timeout=timeout,
                               background=background)
    # (No extra "process" step: the start tool's own step already shows the command; the copy appeared as a second,
    # untitled "Process started" line in the trace and the steps export.)
    return info, None


READ_TOOLS_AS_CMD = {"list_dir", "read_file", "search_code", "system_info", "hardware_info", "software_info", "mobile_info"}


async def _tool_as_command(ctx, args, body) -> ToolResult | None:
    """`run list_dir` / `run read_file app.py`: the model typed an app tool's name as a shell command and PowerShell
    answered "list_dir is not recognized" (a failed step and a debug turn). A read-only tool is called for real; any
    other gets a clear one-line correction."""
    import shutil
    from .registry import TOOLS
    cmd = (body or str(args.get("command") or "")).strip()
    if not cmd or "\n" in cmd or args.get("argv"):
        return None
    head, _, rest = cmd.partition(" ")
    if head not in TOOLS or head in ("run", "start", "stop") or shutil.which(head):
        return None
    tool_ = TOOLS[head]
    if head in READ_TOOLS_AS_CMD:
        rest = rest.strip().strip("'\"")
        res = await (tool_.fn(ctx, {}, rest) if tool_.main else tool_.fn(ctx, {"path": rest} if rest else {}, ""))
        return ToolResult(res.ok, f"[`{head}` is an app tool, not a shell command: it was called as the tool.]\n"
                          + res.output, res.data)
    return ToolResult(False, f"`{head}` is an app tool, not a shell command: call it directly as "
                             f"<tool name=\"{head}\" ...> instead of through run.")


ERR_AT = re.compile(r"((?:[A-Za-z]:)?[\w ./\\()~-]+?\.(?:js|mjs|cjs|jsx|ts|tsx|py|php|kt|kts|java|json|css|scss|html|vue|"
                    r"dart|swift|go|rs|rb|cs|xml|gradle|yaml|yml))[:(](\d{1,6})")


def error_context(ctx, out: str) -> str:
    """A failed command names a file and line (app.js:19, File "x.py", line 7, Main.kt:(12, 5)): those lines as they
    are on disk now go with the result. A weak model "fixed" a SyntaxError at app.js:19 five times from memory - "the
    brace is already there, the error goes on" - because it never saw line 19."""
    shown, parts = set(), []
    text = re.sub(r'File "([^"]+)", line (\d+)', r"\1:\2", out or "")
    for m in ERR_AT.finditer(text):
        raw, line = m.group(1).strip(), int(m.group(2))
        try:
            p = Path(raw) if Path(raw).is_absolute() else (ctx.root / raw)
            p = p.resolve()
            p.relative_to(ctx.root.resolve())
        except (OSError, ValueError):
            continue
        if not p.is_file() or (str(p), line) in shown or len(shown) >= 2 or p.stat().st_size > 2_000_000:
            continue
        shown.add((str(p), line))
        lines = p.read_text(encoding="utf-8", errors="replace").split("\n")
        lo, hi = max(1, line - 5), min(len(lines), line + 4)
        body = "\n".join(f"{'>' if i == line else ' '}{i:5d} | {lines[i - 1][:240]}" for i in range(lo, hi + 1))
        parts.append(f"\n[App: {_rel(ctx, p)} lines {lo}-{hi} as they are on disk now (> = the reported line; the "
                     f"cause is often a line or two before it)]\n{body}")
    return "".join(parts)


@tool("run", '<tool name="run" shell="powershell|powershell5|pwsh|cmd|bash|python|node|php|exec" cwd="." timeout="300">command or script</tool>',
      "Run a command or a whole script and wait for it; returns the exit code and the output tail. Builds, tests, "
      "installs, git, CLI scaffolding. Multi-line scripts: send the source with shell=python/node/powershell/bash (it "
      "runs as a script file, no quoting or heredoc needed). argv=[\"git\", \"log\", \"-1\"] starts a program directly "
      "without a shell (fastest, exact arguments). Heredocs (<<EOF) only with shell=bash; file contents go through "
      "write_file. Use the shell syntax of the versions listed under 'This computer'.",
      {"command": S("Command line or script source"), "shell": S("Interpreter", enum=SHELLS),
       "argv": {"type": "array", "items": {"type": "string"}, "description": "Program and arguments, run without a shell"},
       "cwd": S("Working directory, default '.'"), "timeout": {"type": "integer", "description": "Seconds"}},
      main="command", required=())
async def run(ctx, args, body):
    if redirected := await _tool_as_command(ctx, args, body):
        return redirected
    if SERVER_CMD.search(body or "") or SERVER_CMD.search(" ".join(map(str, args.get("argv") or []))):
        # A server never "finishes": with run the task would wait for the command timeout (minutes). It is started
        # in the background instead and returns once it is up (it is stopped later with stop, or automatically).
        res = await start(ctx, args, body)
        return ToolResult(res.ok, "[This is a server, so it was started in the background with start.]\n" + res.output,
                          res.data)
    t0 = time.time()
    info, denied = await _spawn(ctx, args, body, background=False)
    if denied:
        return denied
    waiter = asyncio.create_task(info.done.wait())
    canceller = asyncio.create_task(ctx.cancel.wait())
    detached = ""
    try:
        while True:
            done, _ = await asyncio.wait({waiter, canceller}, timeout=5, return_when=asyncio.FIRST_COMPLETED)
            if done:
                break
            # A command that runs on without a word (a server started from inside a script, a dev server the
            # pattern did not know, a program waiting for something): the task sat on "run" for minutes. After a
            # silence it goes on in the background and the model gets its id - it decides to wait, read or stop it.
            idle = time.monotonic() - (info.last_output or info.started_mono)
            serving = time.time() - t0 >= 15 and _listens(info.pid)
            if serving and not (serving := await asyncio.to_thread(_http_port, info.pid)):
                # A build or tool that opens a port of its own (the Gradle client talking to its daemon, adb's
                # server on 5037) is no web server: it was moved to the background after 15 s, the model waited on
                # the wrong process and ran the build again over the running one. It goes on until it ends (or
                # stays silent too long).
                serving = 0
            if serving or idle >= RUN_IDLE_DETACH:
                manager.detach(info)
                detached = (f"\n[App note: this command is still running after {int(time.time() - t0)} s"
                            + (f" and serves HTTP on port {serving}" if serving else f" with no output for {int(idle)} s")
                            + f"; it was moved to the background as process_id={info.id} so the task is not blocked. "
                            "Check it with process id=" + info.id + ", stop it with stop id=" + info.id
                            + (f". It is a server: use it now (web_screenshot / fetch_url http://127.0.0.1:{serving}).]"
                               if serving else ". Read its output later with process id=" + info.id
                               + " before running it again.]"))
                break
    except asyncio.CancelledError:  # the task was stopped while the command ran: never leave it running
        await asyncio.shield(manager.stop(info.id))
        raise
    finally:
        canceller.cancel()
        if not waiter.done():
            waiter.cancel()
    if detached:
        out = tidy_ps_errors("\n".join(info.tail))
        return ToolResult(True, f"state=running (background)\n{clip(out)}{detached}",
                          {"process_id": info.id, "exit_code": None})
    if ctx.cancel.is_set():
        await manager.stop(info.id)
    out = tidy_ps_errors("\n".join(info.tail))
    if info.exit_code == 1 and info.state == "failed" and (miss := probe_miss(body or " ".join(map(str, args.get("argv") or [])), out)):
        # "is it still installed?" -> not found: that is the answer, not an error (no debug turn, no held answer)
        return ToolResult(True, f"exit_code=1 state=exited\n{clip(out)}\n[App note: {miss}]",
                          {"process_id": info.id, "exit_code": 1, "probe_miss": True})
    # Files the command wrote are checked by type (a 1 KB "video", an empty PDF, a .docx that is no zip...):
    # exit code 0 alone does not mean the output is real.
    from .verify import check_outputs
    broken = "" if ctx.cancel.is_set() else await check_outputs(ctx.root, t0)
    where = _real_places(ctx, out) if info.exit_code not in (0, None) else ""
    if info.exit_code not in (0, None):
        where += error_context(ctx, out)
    where += git_unborn_note(ctx.root, args.get("cwd"), body or " ".join(map(str, args.get("argv") or [])), out)
    return ToolResult(info.state == "exited" and not broken,
                      f"exit_code={info.exit_code} state={info.state}\n{clip(out)}{broken}{where}",
                      {"process_id": info.id, "exit_code": info.exit_code})


_GIT_LOST = re.compile(r"does not have any commits yet|did not match any file\(s\) known to git|not a valid object name|"
                       r"unknown revision|ambiguous argument 'HEAD'", re.I)


def git_unborn_note(root, cwd, command: str, out: str) -> str:
    """A git repository with no commit yet: `git branch` prints nothing, `git log` fails and `git checkout main` says
    "pathspec did not match". nemotron-3-ultra skipped the first commit and ran git branch / log / reflog 60 times over
    26 minutes, reading the empty answers as a broken repository. The app says what the state really is."""
    if not re.match(r"\s*(?:&\s*)?git(?:\.exe)?\b", command or "") or re.search(r"\bcommit\b", command or ""):
        return ""
    text = re.sub(r"^exit_code=.*$", "", out or "", flags=re.M).strip()
    if text and not _GIT_LOST.search(text):
        return ""
    try:
        d = (Path(root) / (cwd or ".")).resolve()
        for p in (d, *d.parents):
            if (p / ".git" / "HEAD").is_file():
                git = p / ".git"
                break
        else:
            return ""
        head = (git / "HEAD").read_text(encoding="utf-8", errors="replace").strip()
        if not head.startswith("ref: "):
            return ""
        ref = head[5:].strip()
        packed = (git / "packed-refs").read_text(encoding="utf-8", errors="replace") if (git / "packed-refs").is_file() else ""
        if (git / ref).is_file() or f" {ref}" in packed:
            return ""
    except OSError:
        return ""
    branch = ref.removeprefix("refs/heads/")
    return (f"\n[App note: this repository has no commit yet (the current branch '{branch}' is unborn). Until the first "
            "`git commit`, git branch shows nothing, git log fails and no other branch can be checked out - nothing is "
            "broken. Stage the files (git add) and commit first.]")


# Lookups whose exit code 1 means "nothing found" (where / which / Get-Command / npm ls / pip show / grep...).
PROBE_HEAD = re.compile(r"^\s*(?:&\s*)?(?:get-command|gcm|where(?:\.exe)?|which|command\s+-v|type\s+-[ap]|test-path|"
                        r"npm(?:\.cmd)?\s+(?:ls|list)|pnpm\s+(?:ls|list)|yarn\s+list|pip3?\s+show|python3?\s+-m\s+pip\s+show|"
                        r"py\s+-m\s+pip\s+show|winget\s+list|choco\s+list|get-process|get-service|findstr|grep|rg|"
                        r"select-string|sls|get-package|conda\s+list|docker\s+ps|tasklist)\b", re.I)
PROBE_EMPTY = re.compile(r"\(empty\)|not found|could not find|no match|no packages? found|cannot find|"
                         r"is not recognized|bulunamad|no instances|no installed package", re.I)


def probe_miss(command: str, out: str) -> str:
    """A lookup that found nothing (exit 1, no output or a 'not found' line): the note for the model, or ''."""
    cmd = (command or "").strip()
    if not cmd or "\n" in cmd.strip() or not PROBE_HEAD.match(cmd.split(";")[-1].split("|")[0]):
        return ""
    text = re.sub(r"^exit_code=.*$", "", out or "", flags=re.M).strip()
    if text and (not PROBE_EMPTY.search(text) or len(text) > 1500):  # a real error message is left as a failure
        return ""
    return ("this lookup found nothing (exit 1 here means 'not found / no match'). That is the answer - e.g. it is "
            "not installed or not present - not an error to fix.")


_PS_AT = re.compile(r"^(\[stderr\] )?At [^\n]*\.ps1:\d+ char:\d+\s*$")
_PS_PLUS = re.compile(r"^(\[stderr\] )?\s*\+ ")
_PS_NATIVE = re.compile(r"^(\[stderr\] )?[\w.-]+(?:\.exe)? : (.*)$")


def tidy_ps_errors(out: str) -> str:
    """Windows PowerShell 5.1 wraps every stderr line of a program run with 2>&1 in an error record: 'java -version'
    (which prints to stderr) came back as "java : openjdk version ...", "At ...ps1:23 char:1", "+ CategoryInfo ...
    NativeCommandError" - five lines of noise per line, and models read a working program as a failure. The record's
    position lines go; a NativeCommandError keeps only the program's own text, other errors keep their message."""
    if "CategoryInfo" not in out and "FullyQualifiedErrorId" not in out:
        return out
    lines = out.split("\n")
    keep: list[str] = []
    i = 0
    while i < len(lines):
        if _PS_AT.match(lines[i]):
            j = i + 1
            while j < len(lines) and (_PS_PLUS.match(lines[j]) or not lines[j].replace("[stderr]", "").strip()):
                j += 1
            block = "\n".join(lines[i:j])
            if "NativeCommandError" in block:  # the program's own stderr text: drop the "name : " prefix
                k = len(keep) - 1
                while k >= 0 and keep[k].startswith("[stderr]") and not _PS_NATIVE.match(keep[k]):
                    k -= 1  # a long message wrapped onto several lines
                if k >= 0 and (m := _PS_NATIVE.match(keep[k])):
                    keep[k] = (m.group(1) or "") + m.group(2)
            i = j
            continue
        keep.append(lines[i])
        i += 1
    return "\n".join(keep)


MISSING_PATH = re.compile(r"Cannot find path '([^']+)'|No such file or directory[:,]? '?([^'\n]+?)'?(?:\n|$)|"
                          r"can't open file '([^']+)'|cannot find the (?:path|file) specified[^\n]*?([\w./\\-]+\.\w+)?|"
                          r"Could not open input file: (\S+)|ENOENT[^\n]*?'([^']+)'", re.I)


def _real_places(ctx, out: str) -> str:
    """A command failed on a path that does not exist (Move-Item index.php while the file is in ModaKahve/): name
    where files with that name really are, so the model fixes the path instead of guessing again."""
    names = []
    for m in MISSING_PATH.finditer(out or ""):
        p = next((g for g in m.groups() if g), "")
        if p:
            names.append(re.split(r"[\\/]", p.strip().rstrip("."))[-1])
    names = [n for n in dict.fromkeys(names) if n and "." in n][:3]
    if not names:
        return ""
    found = {}
    skip = {"node_modules", ".git", ".venv", "venv", "__pycache__", ".session", "vendor"}
    for dirpath, dirs, files in os.walk(ctx.root):
        dirs[:] = [d for d in dirs if d not in skip]
        for n in names:
            if n in files and len(found.setdefault(n, [])) < 4:
                found[n].append(_rel(ctx, Path(dirpath) / n))
    lines = [f"{n}: " + (", ".join(found[n]) if found.get(n) else "no file with this name exists in the project - "
                                                                    "it was never written; create it first") for n in names]
    cwd = _rel(ctx, _path(ctx, ctx.shell_cwd or "."))
    return (f"\n[App note: commands run in {cwd}. Where these files really are (paths from the task folder): "
            + "; ".join(lines) + "]")


RUN_IDLE_DETACH = 120  # seconds without any output before a still-running run goes to the background


def _speaks_http(port: int) -> bool:
    """Whether the local port answers like a web server (an HTTP status line within a second)."""
    import socket
    try:
        with socket.create_connection(("127.0.0.1", int(port)), timeout=1) as s:
            s.settimeout(1)
            s.sendall(b"HEAD / HTTP/1.0\r\nHost: 127.0.0.1\r\n\r\n")
            return s.recv(8).startswith(b"HTTP/")
    except OSError:
        return False


def _listen_ports(pid: int | None) -> list[int]:
    """The ports the process (or a child of it) listens on (psutil; without it nothing is detected)."""
    if not pid:
        return []
    out: list[int] = []
    try:
        import psutil
        procs = [psutil.Process(pid)]
        procs += procs[0].children(recursive=True)
        for p in procs:
            for c in p.net_connections(kind="inet"):
                if c.status == psutil.CONN_LISTEN and c.laddr and int(c.laddr.port) not in out:
                    out.append(int(c.laddr.port))
    except Exception:
        return out
    return out


def _listens(pid: int | None) -> int:
    """A port the process (or a child of it) listens on, 0 if none."""
    return (_listen_ports(pid) or [0])[0]


def _http_port(pid: int | None) -> int:
    """The first port of the process that answers HTTP, 0 if none (a dev server's HMR socket may come first)."""
    return next((p for p in _listen_ports(pid)[:6] if _speaks_http(p)), 0)


# Commands that start a server or a watcher (they run until stopped).
SERVER_CMD = re.compile(
    r"http\.server|\bphp\s+(-\w+\s+)*-S\s|\bnpm\s+(run\s+)?(dev|start|serve|watch|web|preview)\b|"
    r"\b(yarn|pnpm|bun)\s+(run\s+)?(dev|start|serve|web|preview)\b|\bexpo\s+start\b|\bflutter\s+run\b|"
    r"\bphp\s+artisan\s+serve\b|\bng\s+serve\b|"
    r"\bnpx\s+(--yes\s+)?(serve|http-server|vite|live-server|nodemon)\b|\bvite(\s|$)|\bnext\s+(dev|start)\b|"
    r"\buvicorn\b|\bflask\s+run\b|manage\.py\s+runserver|\brails\s+s(erver)?\b|\bhugo\s+server|\bjekyll\s+serve|"
    r"\bnodemon\b|\bhttp-server\b|\blive-server\b|webpack\s+serve|ng\s+serve|\bdotnet\s+(run|watch)\b.*--urls", re.I)


# A dev server says it is up ("Local: http://localhost:5173", "listening on 3000", "ready in 412 ms").
READY = re.compile(r"https?://(localhost|127\.0\.0\.1|0\.0\.0\.0|\[::\]?1?\]?)(:\d+)?|listening|ready in|ready on|"
                   r"started (server|on)|server (is )?running|compiled successfully|webpack compiled|"
                   r"application startup complete|press ctrl\+c|serving (http|on)", re.I)


async def wait_ready(info, limit: float = 15.0) -> str:
    """Return as soon as a background process shows it is up (a ready line), exits, or goes quiet after printing
    something; never longer than limit. Returns why it returned."""
    t0 = time.monotonic()
    while True:
        if info.done.is_set():
            return "exited"
        tail = list(info.tail)[-40:]
        if any(READY.search(line) for line in tail):
            await asyncio.sleep(0.15)  # the rest of the banner
            return "ready"
        quiet = time.monotonic() - (info.last_output or info.started_mono)
        elapsed = time.monotonic() - t0
        if info.last_output and quiet > 1.2 and elapsed > 1.5:
            return "quiet"
        if not info.last_output and elapsed > 4:
            return "no output yet"
        if elapsed > limit:
            return "still starting"
        await asyncio.sleep(0.1)


@tool("start", '<tool name="start" shell="powershell" cwd=".">npm run dev</tool>',
      "Start a long-running background process (dev servers, watchers). Returns as soon as it reports it is ready "
      "(or exits), with its process id and first output; it keeps running after this call.",
      {"command": S("Command line"), "shell": S("Interpreter", enum=SHELLS), "cwd": S("Working directory"),
       "argv": {"type": "array", "items": {"type": "string"}, "description": "Program and arguments, run without a shell"}},
      main="command", required=())
async def start(ctx, args, body):
    command = (body or "") + " " + " ".join(map(str, args.get("argv") or []))
    restarted = ""
    # The same server started again and again (npx expo start --web, six times): after the second start, while it
    # is still running, answer with the running one and its address instead of restarting it once more.
    starts = getattr(ctx, "start_counts", {})
    key = re.sub(r"\s+", " ", command).strip()
    starts[key] = starts.get(key, 0) + 1
    ctx.start_counts = starts
    chat = (ctx.owner or "").split(":")[0]
    if starts[key] > 2 and chat:
        alive = [p for p in manager._owned(chat)
                 if key and key in re.sub(r"\s+", " ", " ".join(p.argv) + _script_text(p))]
        if alive:
            p = alive[-1]
            addr = next(iter(re.findall(r"https?://(?:localhost|127\.0\.0\.1)(?::\d+)?[^\s'\"]*",
                                        "\n".join(p.tail))), "")
            return ToolResult(True, f"Already running (process_id={p.id}), not restarted"
                                    + (f": open {addr}" if addr else "") + ". Restarting the same server changes nothing - "
                                    "if the page fails, read the server output below and fix the cause.\n"
                                    + clip("\n".join(list(p.tail)[-30:]), 2500), {"process_id": p.id})
    if (port := _port_of(command)) and _port_busy(port):
        # A second "php -S localhost:8000" (after cd public) failed to bind while the first one kept answering 404,
        # and the model kept testing the old server. Our own earlier server on that port is replaced; a port held
        # by another program is reported with a free one.
        chat = (ctx.owner or "").split(":")[0]
        def says_port(p) -> bool:
            # the command line, or the script file a shell command was written to (powershell -File x.ps1)
            text = " ".join(p.argv)
            for a in p.argv[1:]:
                try:
                    f = Path(a)
                    if f.suffix.lower() in (".ps1", ".cmd", ".bat", ".sh") and f.is_file() and f.stat().st_size < 200_000:
                        text += " " + f.read_text(encoding="utf-8", errors="replace")
                except (OSError, ValueError):
                    continue
            return bool(re.search(rf"(?<!\d){port}(?!\d)", text))
        mine = [p for p in manager._owned(chat) if chat and says_port(p)]
        for p in mine:
            await manager.stop(p.id)
        for _ in range(20):
            if not _port_busy(port):
                break
            await asyncio.sleep(0.25)
        if _port_busy(port):
            free = next((q for q in range(port + 1, port + 50) if not _port_busy(q)), port + 1)
            return ToolResult(False, f"port {port} is already in use by another program; start it on a free port, "
                                     f"e.g. {free}")
        restarted = f"(stopped this chat's earlier server on port {port}: {', '.join(p.id for p in mine)})\n"
    info, denied = await _spawn(ctx, args, body, background=True)
    if denied:
        return denied
    why = await wait_ready(info)
    note = ("\nStop it with stop id=" + info.id + " when your check is done; if left running it is stopped "
            "automatically a few minutes after this task.") if info.state == "running" else ""
    return ToolResult(info.state in ("running", "exited"),
                      f"{restarted}process_id={info.id} state={info.state} ({why}) cwd={_rel(ctx, Path(info.cwd))}\n"
                      f"{clip(chr(10).join(info.tail), 3000)}{note}",
                      {"process_id": info.id, "ready": why})


def _script_text(p) -> str:
    """The text of the script file a shell command was written to (powershell -File x.ps1)."""
    for a in p.argv[1:]:
        try:
            f = Path(a)
            if f.suffix.lower() in (".ps1", ".cmd", ".bat", ".sh") and f.is_file() and f.stat().st_size < 200_000:
                return " " + f.read_text(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            continue
    return ""


def _port_of(command: str) -> int | None:
    """The port a server command asks for (php -S host:8000, --port 3000, -p 5173, PORT=8080, --urls http://..:5000)."""
    m = (re.search(r"(?:localhost|127\.0\.0\.1|0\.0\.0\.0|\[::\]|\*)?:(\d{2,5})(?!\d)", command)
         or re.search(r"(?:--port|--http-port|--listen|-p|-l|PORT=)[ =]?(\d{2,5})(?!\d)", command)
         # python -m http.server 8080 (the port is a bare argument: it was not seen, a second server started on a
         # port an old one still held and every request went to the old, broken one)
         or re.search(r"\b(?:http\.server|SimpleHTTPServer)\b(?:\s+-{1,2}[\w-]+(?:[ =](?!\d{2,5}(?:\s|$))\S+)?)*\s+(\d{2,5})(?:\s|$)",
                      command))
    return int(m.group(1)) if m and 1 <= int(m.group(1)) <= 65535 else None


def _port_busy(port: int) -> bool:
    import socket
    for host in ("127.0.0.1", "::1"):
        try:
            with socket.create_connection((host, port), timeout=0.3):
                return True
        except OSError:
            continue
    return False


@tool("stop", '<tool name="stop" id="PROCESS_ID"></tool>', "Stop a background process and its children.",
      {"id": S("Process id returned by start")}, required=("id",))
async def stop(ctx, args, body):
    pid = str(args.get("id") or body or "").strip()
    chat = (ctx.owner or "").split(":")[0]
    mine = manager._owned(chat) if chat else []
    if pid not in manager.procs:
        # "1", a port, a command or nothing: this chat's matching running server(s) instead of a silent failure
        pick = [p for p in mine if pid and (re.search(rf"(?<!\d){re.escape(pid)}(?!\d)", " ".join(p.argv)) or pid in p.id)]
        if not pick and len(mine) == 1:
            pick = mine
        if not pick:
            return ToolResult(False, f"no process {pid!r}. Running in this chat: "
                                     + (", ".join(f"{p.id} ({' '.join(p.argv)[-60:]})" for p in mine) or "none"))
        ok = all([await manager.stop(p.id) for p in pick])
        return ToolResult(ok, "stopped " + ", ".join(p.id for p in pick))
    info = manager.procs[pid]
    if info.state != "running":  # already ended (crashed, or stopped earlier): nothing to stop is not a failure
        return ToolResult(True, f"{pid} is not running any more (state={info.state}, exit_code={info.exit_code})")
    return ToolResult(await manager.stop(pid), f"stopped {pid}")
