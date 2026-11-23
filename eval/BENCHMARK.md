# Benchmark

**English** · [Türkçe](BENCHMARK.tr.md)

Results of [the agent evaluation](README.md) on real models. Each row is one run of one task, scored from real output only. Newest first.

## 2026-11-23 · v0.20.0 · `evren:auto` · Turkish prompts · CPU-only PC (the model runs in the cloud)

| Task | Checks | Status | Time | Turns | Output tokens | Tool calls (errors) | Retries | Model switches |
|---|---|---|---|---|---|---|---|---|
| Web app (3rd run, after the folder fix) | **8/8** | ok | 1022 s | 22 | 4,696 | 16 (0) | 1 | 0 |
| Fix broken Python | **3/3** | ok | 262 s | 8 | 2,064 | 8 (0) | 0 | 0 |
| Five-file change | **4/4** ¹ | ok | 1008 s | 21 | 4,585 | 18 (1) | 0 | 0 |
| Word + PDF | **7/7** | ok | 537 s | 12 | 2,552 | 8 (2) | 0 | 0 |
| Connection drop | **9/9** | ok | 268 s | 7 | 2,161 | 5 (0) | 1 | 0 |

**All five tasks pass: 31/31 checks.**

### What the runs found, and what was fixed

| Run | Result | Cause | Fix in v0.20.0 |
|---|---|---|---|
| Web app, 1st | 0/4, stopped at 1200 s | The files were written to the chat's root, not `todo/`; `browser_key {"key": "F5", "keys": ""}` was refused 3 times | `browser_key` takes the key from `key` / `ref` |
| Web app, 2nd | 5/8 | The app works (Add, reload, no console errors), but the files were in the root again | The app checks that files listed for a named folder are in it; at the end of the task the model is told and moves them |
| Web app, 3rd | 8/8 | The model wrote to the root, was told, moved the files into `todo/` with one command, and tested `todo/index.html` again | – |
| Five-file change | 3/4 → 4/4 | The checker counted the English word "price" in a docstring as a leftover | Checker fixed (Python names only); the model's change was right |

¹ Scored with the fixed checker on the same files.

**Connection drop:** the runner cut the model's stream 97 s into the task, 71 KB into a reply, for 8 s. The app noticed, waited, and continued with the same model. All four files were complete and none was written twice.

**Tool errors that the model recovered from by itself:** two `edit_file` calls in a form the app did not recognise (the next call worked), and one Python script of the model's that exited with an error.

## Run it yourself

```powershell
.venv\Scripts\python.exe eval\run_eval.py --models "evren:auto,nvidia:nvidia/nemotron-3.5-super-vl-120b-a12b"
```

The report is written to `eval/reports/<date-time>/` (`report.md`, `report.json`, traces). Add your results here with the date, version, model and language.
