// Every file operation of a task (write_file, edit_file, make_doc, delete_file, stock photos) with its own line
// counts, in order. The review card and the diff view add these up like Claude Code does: a file written (+597) and
// then edited twice (+2 −2, +2 −2) shows +601 −4, the sum of what each operation changed.
const FILE_TOOLS = new Set(["write_file", "edit_file", "make_doc", "delete_file"]);

export function opsByFile(steps) {
  const out = {};
  for (const s of steps || []) {
    const d = s.data || {};
    if (s.status !== "done") continue;
    const paths = d.tool === "stock_photo" ? d.files || [] : FILE_TOOLS.has(d.tool) && d.path ? [d.path] : [];
    for (const p of paths) {
      (out[p] ||= []).push({
        id: `${s.id}:${p}`, tool: d.tool, added: d.added ?? null, removed: d.removed ?? null,
        diff: d.tool === "stock_photo" ? "" : d.diff || "", created: d.tool === "stock_photo" || !!d.created,
      });
    }
  }
  return out;
}

// Line counts of one file: the sum of its operations when they carry counts; else the net diff (changes made by
// commands or scripts have no operation of their own).
export function fileCounts(f, ops) {
  const counted = (ops || []).filter((o) => o.added != null);
  if (counted.length) return { added: counted.reduce((n, o) => n + o.added, 0), removed: counted.reduce((n, o) => n + o.removed, 0) };
  return { added: f?.added || 0, removed: f?.removed || 0 };
}

// The files a running task has changed so far, from its steps alone (the review card arrives when it ends).
export function liveFiles(steps) {
  const ops = opsByFile(steps);
  return Object.entries(ops).map(([path, list]) => {
    const deleted = list[list.length - 1].tool === "delete_file";
    const binary = list.every((o) => o.added == null);
    return { path, status: deleted ? "deleted" : list[0].created ? "added" : "modified", binary, ...fileCounts(null, list), diff: "" };
  });
}
