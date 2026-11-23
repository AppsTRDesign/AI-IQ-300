# Agent Evaluation

**English** · [Türkçe](README.tr.md)

The same five tasks for every model, scored only from what really exists after the task. What the model *says* it did
is never counted.

| Task | What the model is asked | How it is checked |
|---|---|---|
| `web_app` | A to-do web app in `todo/` (input, Add button, list, localStorage), tested in the browser | The files exist; a real Chromium opens the page, types, clicks Add, reloads; no console errors, no failed requests |
| `fix_python` | `stats.py` is broken (a syntax error and four logic bugs); fix it, run the tests, leave the tests alone | `test_stats.py` unchanged; the given tests and a hidden test file of the same spec pass |
| `multi_file` | Rename `price` to `unit_price` across five modules, add `low_stock()`, a report section, update the README | No old name left; all five modules changed; README updated; hidden tests (rename, new method, report, CLI) pass |
| `documents` | A report as Word and PDF with three named sections, then open and verify both | `python-docx` and `pypdfium2` open them; the sections are real headings; ≥ 120 words; no Markdown left (`#`, `**`, ```) |
| `net_drop` | Four files, one per planet, written one at a time | The runner really cuts the model's connection mid-task for 8 s; all four files are complete; the app noticed the drop and continued; no finished file was written again; same model kept |

## Run it

```powershell
.venv\Scripts\python.exe eval\run_eval.py --models mock
```

```powershell
.venv\Scripts\python.exe eval\run_eval.py --models "evren:auto,nvidia:nvidia/nemotron-3.5-super-vl-120b-a12b"
```

```powershell
.venv\Scripts\python.exe eval\run_eval.py --models evren:auto --tasks fix_python,documents --lang en
```

- `--models mock` is the self-test: a scripted model solves every task with real tool calls, so every check must pass.
  CI runs it on every push.
- Model ids are `provider:model`, as in the model picker. Several models run one after another.
- `--lang tr|en` is the language of the prompts and the report.
- `--timeout` is seconds per task (default 1800). A task that runs over is stopped by the runner. This is an
  evaluation limit only: the app itself never stops a task for failures or budgets.
- `--keep` keeps the temporary data folder (chats, app log) to look into a failure.

## Your data stays yours

Each run starts its own app instance with a temporary data folder, on port 8390 (`--port`), next to your running app.
Your `data/` folder is only read: `settings.json` and `secrets.json` are copied into the temporary folder so your
providers work, and the copy is deleted at the end (also with `--keep`, keys stay only in that temporary folder until
you delete it). Permission mode is "full" in the evaluation instance; your own settings are not changed.

## Report

`eval/reports/<date-time>/`:

- `report.md`: a summary per model (score, tasks fully passed, time, output tokens, tool calls and errors), one row per
  task (status, turns, retries, model switches), every failed check, error kinds by tool, and every check.
- `report.json`: the same data, for comparing runs.
- `traces/<model>__<task>.jsonl`: each task's trace (see below).

Score = passed checks / all checks.

## Traces

Every task in the app (not only in an evaluation) writes `chat/<id>/.session/traces/<run id>.jsonl`:

```
{"type": "run",  "run": "…", "model": "…", "status": "ok", "request": "…", "timing": {…}, "files": [...]}
{"type": "turn", "i": 1, "wait_ms": 900, "total_ms": 2000, "out_tokens": 120, "tps": 30.0}
{"type": "step", "t": 1763870000.1, "ms": 12, "kind": "file", "tool": "write_file", "args": {…}, "status": "done"}
{"type": "step", …, "status": "error", "error": "ModuleNotFoundError: No module named 'flask'"}
```

It is written by the app from its own records, never by the model; long values are cut and secrets in commands are
already hidden. The last 30 traces of a chat are kept. `GET /api/sessions/<chat id>/traces/<run id>` returns one with
its counts.

## Add a task

Add a `Task` to `eval/tasks.py`: its prompt in Turkish and English, an optional seed folder under `eval/tasks/`, and a
check function that looks at the folder and the trace and returns `(name, ok, info)` rows. Then teach
`eval/mock_solver.py` to solve it, so the self-test keeps passing.
