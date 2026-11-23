# Agent Evaluation

**English** · [Türkçe](README.tr.md)

The same nine tasks for every model, scored only from what really exists after the task. What the model *says* it did
is never counted.

| Task | What the model is asked | How it is checked |
|---|---|---|
| `web_app` | A to-do web app in `todo/` (input, Add button, list, localStorage), tested in the browser | The files exist; a real Chromium opens the page, types, clicks Add, reloads; no console errors, no failed requests |
| `fix_python` | `stats.py` is broken (a syntax error and four logic bugs); fix it, run the tests, leave the tests alone | `test_stats.py` unchanged; the given tests and a hidden test file of the same spec pass |
| `multi_file` | Rename `price` to `unit_price` across five modules, add `low_stock()`, a report section, update the README | No old name left; all five modules changed; README updated; hidden tests (rename, new method, report, CLI) pass |
| `documents` | A report as Word and PDF with three named sections, then open and verify both | `python-docx` and `pypdfium2` open them; the sections are real headings; ≥ 120 words; no Markdown left (`#`, `**`, ```) |
| `net_drop` | Four files, one per planet, written one at a time | The runner really cuts the model's connection mid-task for 8 s; all four files are complete; the app noticed the drop and continued; no finished file was written again; same model kept |
| `research` | Complex web research: four facts (two release dates, a PEP number, a licence) and a day count computed from them, each with its source URL on the same line, ≥ 4 sources from ≥ 3 sites | Each fact is right; the day count is right; every fact has its source beside it; the checker opens every cited URL itself (a 404 or a dead site is an invented source); the trace shows ≥ 2 web tool calls |
| `skill_review` | Review a small app for bugs and security problems, report by severity in `review.md`, change no code | The four planted problems are named with their file (SQL injection, path traversal, hard-coded secret, off-by-one paging); SQL injection rated critical / high; code unchanged |
| `skill_flowchart` | A Mermaid flowchart of an order process with two decisions and a restock loop, saved to `diagrams/order.mmd` | The app's own Mermaid parses and draws it in a real browser; ≥ 7 steps; two diamond decisions; Yes / No exits; the loop really goes back (a cycle in the graph) |
| `skill_git` | Start a repository on `main`, `.gitignore` for `.env` and `__pycache__`, first commit, a `feature/login` branch with `login.py`, back to `main` | Checked with git itself: branches, the commit message, `.env` and `__pycache__` never committed, `login.py` only on the branch, HEAD on `main`, nothing uncommitted |

In the three skill tasks the prompt does not name the skill. Whether the model loaded the matching skill is shown in the report as a note, not scored: the app leaves that choice to the model, and a model that does the job right without the skill passes.

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

- `report.html`: the interactive report. It holds:
  - score tiles
  - an assessment per model: the success rate first, then how much of the time was the provider (first-token wait,
    rate limits), the model writing, tools and the app, and whether the app itself had any problem. The success
    rate and no app errors are what count; a slow provider queue is named as such and does not change the score.
  - three charts with hover details (light and dark)
  - the full table
  - every check
- `report.md`: the same, with the charts as SVG images. It has:
  - a summary per model
  - where the time went, per task
  - one row per task: status, turns, retries, model switches
  - every failed check
  - error kinds by tool
  - every check
- `charts/*.svg`: the charts:
  - `scores`: the three scores by model
  - `heatmap`: task × model, checks passed
  - `time`: where each task's time went
- `report.json`: the same data, for comparing runs, with `scores` per model.
- `traces/<model>__<task>.jsonl`: each task's trace (see below).

Models run apart (in parallel or on different days) can be combined into one report:

```powershell
.venv\Scripts\python.exe eval\run_eval.py --merge "eval\reports\<a>,eval\reports\<b>"
```

A run kept with `--keep` can be scored again after a checker fix, on the files it really left, without running the
models again (the report is marked "re-scored"):

```powershell
.venv\Scripts\python.exe eval\run_eval.py --rescore "eval\reports\<a>" --kept "<the kept temporary folder>"
```

### Three scores, kept apart

They answer different questions, so all three are shown:

| Score | What it is | Answers |
|---|---|---|
| Per task (equal weight) | mean of each task's passed / its checks | how well the model does an average task |
| Per check (pooled) | all passed checks / all checks | how many single requirements it met; a task with many checks weighs more |
| Fully passed | tasks with every check passed / tasks | how often the whole job was really done |

Example: 5/8, 3/3, 2/4, 7/7, 5/5 gives the following:
- per task: 82.5 %
- per check: 22/27 = 81.5 %
- fully passed: 3/5 = 60 %

### Where the time went

Each task's time is split into the following parts. All of them come from the app's own clock:

| Part | What it covers |
|---|---|
| wait | until each request's first token: provider queue plus reading the prompt |
| generation | streaming after the first token |
| tools | running the tools (wall time: calls that run in parallel count once) |
| wait after errors | waiting after provider errors such as rate limits |
| app | the rest |

Two more numbers come with each task:
- **longest single wait**
- **wait per 1K prompt tokens:** the median over the task's requests. A slow task with a high wait per 1K on small prompts means the provider was slow, not the model's work.

## Traces

Every task in the app (not only in an evaluation) writes `chat/<id>/.session/traces/<run id>.jsonl`:

```
{"type": "run",  "run": "…", "model": "…", "status": "ok", "request": "…", "timing": {…}, "files": [...]}
{"type": "turn", "i": 1, "wait_ms": 900, "total_ms": 2000, "in_tokens": 6200, "out_tokens": 120, "tps": 30.0}
{"type": "step", "t": 1763870000.1, "ms": 12, "kind": "file", "tool": "write_file", "args": {…}, "status": "done"}
{"type": "step", …, "status": "error", "error": "ModuleNotFoundError: No module named 'flask'"}
```

It is written by the app from its own records, never by the model; long values are cut and secrets in commands are
already hidden. The last 30 traces of a chat are kept. `GET /api/sessions/<chat id>/traces/<run id>` returns one with
its counts.

## Add a task

Add a `Task` to `eval/tasks.py` with the following:
- its prompt in Turkish and English
- an optional seed folder under `eval/tasks/`
- an optional `setup` for files a git seed cannot carry, such as `.env`
- a check function that looks at the folder and the trace and returns `(name, ok, info)` rows. Then teach
`eval/mock_solver.py` to solve it, so the self-test keeps passing.
