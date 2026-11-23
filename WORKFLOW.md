# How AI IQ 300 works

> [Türkçe](WORKFLOW.tr.md) · [README](README.md) · [Project state](PROJECT_STATE.md)

This page shows the path a message takes, from the message box to the finished answer. The diagrams are Mermaid
code, so GitHub draws them; the same code also draws in the app's chat.

## 1. Overview

```mermaid
flowchart TD
  U(["💬 User message<br/>text · files · @agent · /skill · #MCP"]) --> R

  subgraph P1["1 · Read the request"]
    direction TB
    R["Language and intent<br/>small talk · work · web · browser"] --> G["Tool groups the task needs<br/>(need_tools: core + only what fits)"]
    G --> SP["System prompt<br/>identity · rules · skills · agents"]
  end

  SP --> M{"Which model?"}
  M -->|"Local"| L["Ollama / LM Studio<br/>RAM-VRAM guard"]
  M -->|"Cloud"| C["Cloud provider<br/>quota check · auto switch"]
  M -->|"Team"| T[["Agent team<br/>stages on pool models"]]
  L --> LOOP
  C --> LOOP
  T --> LOOP

  subgraph P2["2 · Tool loop"]
    direction TB
    LOOP["Model turn streams<br/>thinking · text · tool calls"] --> SPL["Stream parser<br/>no call syntax in the chat"]
    SPL --> Q{"Tool call?"}
    Q -->|"Yes"| AP{"Needs approval?"}
    AP -->|"Yes"| ASK[/"Ask the user"/]
    ASK --> RUN
    AP -->|"No"| RUN["Run the tools<br/>parallel jobs · to-do list kept in step"]
    RUN --> GD["Guards<br/>repeat · loop · babble · file shrink · near-duplicate search"]
    GD --> LOOP
  end

  Q -->|"No: an answer"| V

  subgraph P3["3 · Check and finish"]
    direction TB
    V{"Is the work really done?<br/>files · pages · tests · promises"} -->|"No"| FIX["Back to work<br/>debugger hint, real error text"]
    V -->|"Yes"| SAVE["Checkpoint and chat ledger<br/>resume after a stop · nothing forgotten"]
  end

  FIX --> LOOP
  SAVE --> A(["✅ Answer + steps<br/>diagrams · files · previews"])

  classDef ok fill:#dcfce7,stroke:#16a34a,color:#14532d
  classDef warn fill:#fef3c7,stroke:#d97706,color:#78350f
  classDef ext fill:#ede9fe,stroke:#7c3aed,color:#3b0764
  class A ok
  class FIX,ASK warn
  class T,C ext
```

- **Read the request.** The reply language and the intent come first. The prompt carries only the tool groups this
  conversation needs, so small and local models get a short prompt.
- **Pick the model.** A local model is loaded only when the machine has the memory for it. A cloud model is checked
  against its quota, and the task moves to another model when the quota runs out. A team splits the work into stages.
- **Tool loop.** The model streams its reasoning, text and tool calls. The parser hides every call format from the chat.
  Tools run (in parallel when they can), the to-do list follows the work, and guards stop repeats, loops, babble and
  file rewrites that would lose content.
- **Check and finish.** A reply that only promises work, or claims files and tests that do not exist, goes back to the
  loop with the real error. A finished task is saved as a checkpoint and shown with its steps. The app also writes the chat ledger (files,
  commands, environment, failures), so the next task starts knowing what was done.

## 2. One model turn

```mermaid
sequenceDiagram
  autonumber
  actor U as User
  participant O as Orchestrator
  participant S as Streaming + parser
  participant P as Provider adapter
  participant T as Tools
  U->>O: Message
  O->>O: Prompt, tool groups, history (older steps shortened)
  O->>S: Start a turn
  S->>P: Request (native tools or tag protocol)
  P-->>S: Thinking · text · tool calls (stream)
  S-->>U: Live text and steps (no call syntax)
  alt the turn has tool calls
    S->>O: Parsed calls
    O->>T: Run (approval, repeat and file guards)
    T-->>O: Results
    O->>S: Next turn with the results
  else a final answer
    O->>O: Checks: promises, missing files, unfinished to-dos
    O-->>U: Answer + steps
  end
```

## 3. Agent team (cloud multi-model)

```mermaid
flowchart LR
  MAIN["Main agent<br/>plans the stages"] --> S1
  subgraph S1["Stage 1 · parallel"]
    direction TB
    A1["Member A<br/>pool model 1"]
    A2["Member B<br/>pool model 2"]
  end
  S1 --> S2
  subgraph S2["Stage 2 · uses stage 1 files"]
    direction TB
    B1["Member C<br/>pool model 3"]
  end
  S2 --> CHK{"Report and files OK?"}
  CHK -->|"Yes"| DONE(["Main agent writes the answer"])
  CHK -->|"No"| MAIN
  classDef ok fill:#dcfce7,stroke:#16a34a,color:#14532d
  class DONE ok
```

Each member runs its own tool loop on a model from the pool. Members of one stage work in parallel; a later stage
reads the files of the earlier ones. A model that hits its quota is swapped for another one in the pool.

## 4. Edge cases

What the app does when things do not go to plan. Each diagram follows the code as it is; the module names are in the
table below.

### 4.1 Stop in the middle of a task

```mermaid
flowchart TD
  S(["⏹ User presses Stop"]) --> C["The model stream is cancelled"]
  C --> K["Cleaned up at once:<br/>pending approvals · visible browser ·<br/>running commands · this task's servers"]
  K --> R["Running steps are marked stopped<br/>the steps done are kept for Continue"]
  R --> L["Chat ledger records the task as cancelled"]
  L --> M(["Message: Stopped<br/>buttons: Continue · Undo this task's file changes"])
  M -->|"Continue"| RES["Resume: the record of done steps<br/>goes to the model, nothing is redone"]
  M -->|"Undo"| U{"Is the file still exactly<br/>as the task left it?"}
  U -->|"Yes"| B["Put back: old content restored,<br/>new files removed, deleted files back"]
  U -->|"No, changed since"| KEEP["Left as it is and listed"]
  classDef warn fill:#fef3c7,stroke:#d97706,color:#78350f
  classDef ok fill:#dcfce7,stroke:#16a34a,color:#14532d
  class KEEP warn
  class B,RES ok
```

- **Undone:** files changed by `write_file`, `edit_file` and `delete_file`. The state before the task's first change to
  each file is kept for the last 5 tasks of the chat.
- **Not undone:** changes made by shell commands (a build, `npm install`, a script). In a project, the git time machine
  under Files covers those.
- A file the user (or a later task) changed after the task is never overwritten by an undo.

### 4.2 Two agents change the same file

```mermaid
flowchart TD
  A["Agent A writes app.js"] --> V["The app notes app.js version 2, written by A"]
  B["Agent B (read version 1) rewrites the whole app.js"] --> CHK{"Did B see version 2?"}
  V --> CHK
  CHK -->|"No"| REF["Refused: changed by A after you read it<br/>read it again, change only your part"]
  REF --> RD["B: read_file, then edit_file"]
  RD --> LOCK
  CHK -->|"Yes"| LOCK["Per-file lock: one writer at a time"]
  LOCK --> AT["Atomic replace: temp file, then swap<br/>bytes on disk checked; old content back on a mismatch"]
  AT --> OK(["Both changes are kept"])
  classDef warn fill:#fef3c7,stroke:#d97706,color:#78350f
  classDef ok fill:#dcfce7,stroke:#16a34a,color:#14532d
  class REF warn
  class OK ok
```

- `edit_file` and `write_file append` always apply to the file as it is under the lock, so they never lose another
  agent's change.
- A full rewrite is refused only when another agent **of the same task** changed the file after this agent last read
  it. A later task of the chat is not a parallel writer.
- The rewrite goes through on the third try, so a file too big to read whole is never a dead end. Its earlier version
  is in `.aiiq/backups`.

### 4.3 The model changes in the middle of a task

```mermaid
flowchart TD
  E{"Quota out, provider busy<br/>or connection dropped"} -->|"Multi-model on, auto switch"| P["Pick the most available pool model<br/>(at most 3 switches per task)"]
  E -->|"Off"| W["Wait and retry the same model<br/>or stop with a resumable error"]
  P --> H["Same conversation + handover note:<br/>exact to-do list, items marked [x] are done"]
  H --> D["Record of calls already made<br/>+ files written (they exist on disk)"]
  D --> G["Repeat guards: the same call with the same result<br/>is not run again"]
  G --> CUT{"Was a file being written?"}
  CUT -->|"Yes"| SV["The written part is saved<br/>the new model continues with append"]
  CUT -->|"No"| GO(["The new model continues from the current item"])
  SV --> GO
  classDef ok fill:#dcfce7,stroke:#16a34a,color:#14532d
  class GO ok
```

### 4.4 A fix that does not work

The user's rule: **no circuit breaker**. Errors are part of coding, so a count of failures never stops a task or
switches off the file and command tools. What the app prevents is the *same* thing happening again and again.

```mermaid
flowchart TD
  F["A tool call fails"] --> S1{"The exact same call already failed<br/>twice with the same error?"}
  S1 -->|"Yes"| NR["Not run a third time:<br/>change the route, not the flags"]
  S1 -->|"No"| S2{"Same error kind back for the<br/>3rd, 6th, 9th… time?"}
  S2 -->|"Yes"| EX["The model is told: your fixes miss the cause.<br/>Here is what you tried. Read the error and its line,<br/>name the root cause, search the exact message"]
  S2 -->|"No"| S3{"Seen in an earlier task<br/>of this chat?"}
  S3 -->|"Yes"| PR["Named: this error also stopped task N"]
  S3 -->|"No"| ON(["The model sees the error and keeps working"])
  NR --> ON
  EX --> ON
  PR --> ON
  classDef warn fill:#fef3c7,stroke:#d97706,color:#78350f
  classDef ok fill:#dcfce7,stroke:#16a34a,color:#14532d
  class NR,EX,PR warn
  class ON ok
```

- **Every 4 failing turns in a row:** "you are stuck, take a different route".
- **The same call with the same result 3 times:** turned into a failure with an explanation.
- **Tools that are not needed for the work itself** (for example a search API that keeps refusing) are switched off for the task after 3 identical errors. File, command and read tools never are.
- **The step limit** (Settings > Agent, 60 by default, unlimited possible) ends the task; "Continue" resumes it with the record of what already ran.

## 5. Where it lives in the code

| Step | Module |
|---|---|
| Language, intent, tool groups, answer checks | `backend/app/agents/checks.py` |
| System prompt (identity, rules, capability map) | `agents/prompts.py`, `agents/prompting.py` |
| Run loop, final checks | `agents/orchestrator.py` |
| One streamed turn, stalls, loops | `agents/streaming.py`, `agents/stream_parser.py` |
| Running tools, to-do list, repeat guard | `agents/tooling.py` |
| Output guards (repeat, babble, word salad) | `agents/guards.py` |
| Checkpoints, resume, cut files | `agents/continuity.py` |
| Chat ledger (what earlier tasks did; `recall`) | `agents/ledger.py` |
| File locks, atomic writes, parallel-change check | `tools/safe_io.py` |
| Undo of a task's file changes | `tools/undo.py` |
| Recurring-error notes, repeat guards | `agents/tooling.py` |
| Handover after a model switch | `agents/continuity.py` (`_handover`), `agents/orchestrator.py` |
| Agent teams | `agents/team.py` |
| Providers, routing, quotas, model families | `llm/providers.py`, `llm/router.py`, `llm/usage.py`, `llm/families.py` |
| RAM / VRAM guard for local models | `llm/memguard.py` |
| Tools (files, shell, web, browser, docs, media, diagrams, system) | `backend/app/tools/` |
| Chat, diagrams, previews | `frontend/src/components/` |
