---
name: flowchart
title: Flowcharts and diagrams
title_tr: Akış şeması ve diyagram
title_en: Flowcharts and diagrams
description: Professional flowcharts, workflow, architecture, sequence, state and ER diagrams, mind maps, timelines and Gantt charts as Mermaid code the chat draws.
description_tr: Profesyonel akış şemaları; iş akışı, mimari, sıralama, durum ve ER diyagramları, zihin haritası, zaman çizelgesi ve Gantt şemaları. Sohbet bunları Mermaid kodundan çizer.
description_en: Professional flowcharts, workflow, architecture, sequence, state and ER diagrams, mind maps, timelines and Gantt charts as Mermaid code the chat draws.
tools: read_file, list_dir, search_code, write_file, render_diagram, make_doc
---
Draw the diagram as Mermaid code in a ```mermaid block in your answer. The chat renders it in the app's own style
(rounded soft nodes, pill edge labels, light/dark) with zoom, live code editing and PNG/SVG download. Never use
generate_image or matplotlib for a diagram: an image model writes unreadable fake text.

## 1. Understand before drawing
- Find the real steps first: for a codebase read the entry points (search_code / read_file), for a process the
  user's own words. Never invent steps, systems or numbers. Name things the way the user / the code does.
- Pick the right type:
  - process, algorithm, decision logic, "how it works" -> `flowchart TD` (long chains) or `flowchart LR` (wide, few steps)
  - who talks to whom over time (API calls, sign-in, request/response) -> `sequenceDiagram`
  - states and transitions (order status, connection) -> `stateDiagram-v2`
  - data model / tables -> `erDiagram`; classes -> `classDiagram`
  - plan with dates -> `gantt`; history / roadmap -> `timeline`; idea tree -> `mindmap`
  - user experience steps with scores -> `journey`; shares -> `pie`; 2x2 matrix -> `quadrantChart`

## 2. Flowchart craft (what makes it look professional)
- One clear start and end: `S(["🚀 Start"])` ... `E(["✅ Done"])` (stadium shape).
- Shapes carry meaning:
  `[Process]`, `{"Decision?"}`, `[("Database")]`, `[["Sub-process"]]`, `[/"Input / output"/]`, `(("Event"))`,
  `>"Signal"]`. Decisions are questions ending in "?" with labelled exits: `-->|Yes|` / `-->|No|`.
- Short ids (`A1`, `chk`, `db`), the text in quotes: `A1["Load the project context"]`. Quotes are REQUIRED when a
  label has ( ) [ ] { } : ; # / , or non-ASCII letters (Turkish ç ğ ı ö ş ü). Line break inside a label: `<br/>`.
  A quote inside a label: `#quot;`.
- Labels are short verb phrases (2-6 words), all in the user's language, the same tense everywhere.
- Edges: `-->` normal, `==>` the main / happy path, `-.->` optional, async or fallback; `-->|label|` for conditions.
- Group phases with subgraphs, titled in the user's language:
  ```
  subgraph P1["1 · Preparation"]
    direction TB
    A1 --> A2
  end
  ```
  Every `subgraph` needs its own `end`. Never use the bare word `end` as a node id (use `E`, `done`).
- Loops go back to an earlier node (`fix --> run`), not to a copy of it.
- Semantic colour, sparingly (2-4 classes; these read well in light and dark):
  ```
  classDef ok fill:#dcfce7,stroke:#16a34a,color:#14532d
  classDef err fill:#fee2e2,stroke:#dc2626,color:#7f1d1d
  classDef warn fill:#fef3c7,stroke:#d97706,color:#78350f
  classDef ext fill:#ede9fe,stroke:#7c3aed,color:#3b0764
  class E ok
  class X1,X2 err
  ```
- Size: up to about 25-30 nodes in one diagram. Larger: an overview diagram plus one diagram per phase.
- Layout: keep the main path straight down (TD) or across (LR); put error / fix branches to the side.

## 3. Other types, minimal correct forms
```
sequenceDiagram
  autonumber
  actor U as User
  participant A as App
  participant M as Model
  U->>A: Message
  A->>M: Prompt + tools
  M-->>A: Tool call
  alt tool fails
    A-->>M: Error
  else ok
    A-->>U: Answer
  end
```
```
stateDiagram-v2
  [*] --> Draft
  Draft --> Review: submit
  Review --> Done: approve
  Done --> [*]
```
```
gantt
  title Plan
  dateFormat YYYY-MM-DD
  section Design
  Wireframes :a1, 2026-01-05, 5d
  section Build
  Frontend :after a1, 10d
```
```
mindmap
  root((Topic))
    Idea A
      Detail
    Idea B
```

## 4. Check before you answer
- Every `subgraph` has `end`, every `alt/loop/opt` in a sequence has `end`.
- Node ids are unique; each id's label is written once (later references use the bare id).
- Every label with special characters or non-ASCII letters is in double quotes.
- No markdown inside the block (no ** or backticks); no trailing explanation inside the fence.

## 5. Answer layout
One short sentence on what the diagram shows, the ```mermaid block, then 3-6 bullets explaining the key paths or
decisions. Mention that the diagram can be zoomed, edited ("Edit code") and downloaded as PNG/SVG from its menu.

## 6. When a file is asked for
- Markdown / GitHub (README, docs): write the same ```mermaid block into the .md file; GitHub draws it.
- An image file (PNG/SVG) on disk, "export it as a picture": `render_diagram` with the code (or source= the .md
  file that holds the ```mermaid block) and path="diagrams/<name>.png" (or .svg; theme="dark" for a dark one). It
  draws in the same style as the chat. Never matplotlib, never generate_image.
- In a PDF / Word document: render_diagram to a PNG first, then put that PNG in the document as an image.
