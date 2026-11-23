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
    V -->|"Yes"| SAVE["Checkpoint and history<br/>resume after a stop"]
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
  loop with the real error. A finished task is saved as a checkpoint and shown with its steps.

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

## 4. Where it lives in the code

| Step | Module |
|---|---|
| Language, intent, tool groups, answer checks | `backend/app/agents/checks.py` |
| System prompt (identity, rules, capability map) | `agents/prompts.py`, `agents/prompting.py` |
| Run loop, final checks | `agents/orchestrator.py` |
| One streamed turn, stalls, loops | `agents/streaming.py`, `agents/stream_parser.py` |
| Running tools, to-do list, repeat guard | `agents/tooling.py` |
| Output guards (repeat, babble, word salad) | `agents/guards.py` |
| Checkpoints, resume, cut files | `agents/continuity.py` |
| Agent teams | `agents/team.py` |
| Providers, routing, quotas, model families | `llm/providers.py`, `llm/router.py`, `llm/usage.py`, `llm/families.py` |
| RAM / VRAM guard for local models | `llm/memguard.py` |
| Tools (files, shell, web, browser, docs, media, diagrams, system) | `backend/app/tools/` |
| Chat, diagrams, previews | `frontend/src/components/` |
