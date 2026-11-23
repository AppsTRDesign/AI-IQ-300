// Mermaid diagram text: a ```mermaid fence, or a plain/untagged fence (or a whole pasted message) whose first real
// line is a Mermaid diagram header (flowchart TD, sequenceDiagram, gantt…). Front matter (---) and %%{init}%% lines
// before the header are allowed, as Mermaid itself allows them.
const HEAD = /^(flowchart|graph|sequenceDiagram|classDiagram(-v2)?|stateDiagram(-v2)?|erDiagram|journey|gantt|pie|mindmap|timeline|gitGraph|quadrantChart|requirementDiagram|C4(Context|Container|Component|Dynamic|Deployment)|xychart(-beta)?|sankey(-beta)?|block(-beta)?|architecture(-beta)?|packet(-beta)?|kanban|radar(-beta)?|treemap(-beta)?)\b/;

export function isMermaid(text) {
  if (!text) return false;
  let s = String(text).replace(/^﻿/, "").trimStart();
  if (s.startsWith("---")) { // front matter: --- title: x --- (closed)
    const end = s.indexOf("\n---", 3);
    if (end < 0) return false;
    s = s.slice(end + 4).trimStart();
  }
  while (/^%%/.test(s)) s = s.replace(/^%%[^\n]*\n?/, "").trimStart(); // %%{init: …}%% and %% comments
  if (!HEAD.test(s)) return false;
  // "graph" / "pie" / "journey" are also English words: a diagram header line is short and the text has a 2nd line.
  const first = s.split("\n", 1)[0];
  return first.length <= 80 && s.includes("\n");
}

// The language tag of a fenced block that holds a diagram ("mermaid", "mmd", or no tag with a Mermaid header).
export function mermaidLang(lang, code) {
  const l = (lang || "").toLowerCase();
  if (l === "mermaid" || l === "mmd") return true;
  return (!l || l === "text" || l === "txt" || l === "plaintext") && isMermaid(code);
}
