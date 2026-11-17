import { memo, useMemo, useState } from "react";
import {
  ChevronDown, ChevronRight, FileCode2, FileImage, FileText, FileSpreadsheet, Film, Database, Archive, File as FileIcon,
  Code2, GitCompareArrows, Search, SquareArrowOutUpRight, X,
} from "lucide-react";
import { useStore, useT } from "../lib/store";
import { fileCategory, fileType } from "../lib/fileTypes";
import { fileCounts, opsByFile } from "../lib/changes";
import { DiffView } from "./ActivityTrace";

const STATUS = {
  added: ["A", "bg-ok/12 text-ok"], modified: ["M", "bg-warn/15 text-warn"], deleted: ["D", "bg-danger/12 text-danger"],
};
const OP_KEY = { write_file: "step_file", edit_file: "step_edit", make_doc: "step_document", delete_file: "step_delete", stock_photo: "step_photo" };
const kb = (n) => (n >= 1048576 ? `${(n / 1048576).toFixed(1)} MB` : n < 1024 ? `${n || 0} B` : `${Math.round(n / 1024)} KB`); // a 0-byte "video" must not look like 1 KB
// Groups in the order they are shown; each file goes to the group of its type.
const GROUPS = [
  ["document", FileText], ["code", FileCode2], ["sheet", FileSpreadsheet], ["image", FileImage], ["media", Film],
  ["data", Database], ["archive", Archive], ["other", FileIcon],
];

const Lines = ({ added, removed }) => (
  <span className="shrink-0 font-mono text-[11px]"><span className="text-ok">+{added}</span> <span className="text-danger">−{removed}</span></span>
);

// One operation of a file. With several operations, a whole-file write (hundreds of green lines) starts folded, so the
// edits after it - the + and − that matter - are seen at once.
function OpDiff({ o, i, many }) {
  const t = useT();
  const lines = (o.diff || "").split("\n").length;
  const [show, setShow] = useState(!(many && lines > 60 && o.tool === "write_file"));
  return (
    <div className="mb-2 last:mb-0">
      {many && (
        <button onClick={() => setShow(!show)} className="mb-1 flex w-full items-center gap-2 text-left text-[11px] text-muted hover:text-fg">
          {show ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
          <span className="font-medium text-fg/80">{i + 1}. {t(OP_KEY[o.tool] || o.tool)}</span>
          {o.added != null && <Lines added={o.added} removed={o.removed} />}
          {!show && <span className="text-subtle">· {t("diffs_show")}</span>}
        </button>
      )}
      {show && (o.diff ? <DiffView diff={o.diff} height="max-h-[28rem]" /> : <div className="text-[11.5px] text-subtle">{t("diffs_no_diff")}</div>)}
    </div>
  );
}

// One file: an accordion. Open, it shows the file's diff - its total change, or each operation one by one.
function Row({ f, ops, open, onToggle, view }) {
  const t = useT();
  const [letter, cls] = STATUS[f.status] || STATUS.modified;
  const ft = fileType(f.path);
  const list = ops || [];
  const net = f.diff || (list.length === 1 ? list[0].diff : "");
  const byOps = view === "ops" || !net;
  const hasDiff = !f.binary && (net || list.some((o) => o.diff));
  return (
    <div className="border-t border-line first:border-t-0">
      <div className="flex min-w-0 items-center gap-2 px-3 py-1.5 text-[12.5px]">
        <button onClick={onToggle} disabled={!hasDiff} className="flex min-w-0 flex-1 items-center gap-2 text-left disabled:cursor-default">
          {hasDiff ? (open ? <ChevronDown size={13} className="shrink-0 text-subtle" /> : <ChevronRight size={13} className="shrink-0 text-subtle" />)
            : <ft.icon size={13} className="shrink-0" style={{ color: ft.color }} />}
          <span className={`grid h-4 w-4 shrink-0 place-items-center rounded text-[10px] font-bold ${cls}`} title={t(`change_${f.status}`)}>{letter}</span>
          <span className={`truncate font-mono ${f.status === "deleted" ? "text-muted line-through" : ""}`} title={f.path}>{f.path}</span>
        </button>
        {list.length > 1 && <span className="shrink-0 rounded-md bg-hover px-1.5 py-px text-[10.5px] text-muted" title={t("changes_edits_hint")}>{t("changes_edits", { n: list.length })}</span>}
        {f.source && (
          <span className={`hidden shrink-0 rounded-md px-1.5 py-px text-[10.5px] font-medium sm:inline ${f.source === "command" ? "bg-accent-soft text-accent" : "bg-hover text-muted"}`}
            title={t(f.source === "command" ? "change_by_command_hint" : "change_by_tool_hint")}>
            {t(f.source === "command" ? "change_by_command" : "change_by_tool")}
          </span>
        )}
        {f.binary ? <span className="shrink-0 text-[11px] text-subtle">{f.size != null ? (f.status === "modified" ? `${kb(f.size_before)} → ${kb(f.size)}` : kb(f.size)) : ""}</span>
          : <Lines {...fileCounts(f, list)} />}
        {f.status !== "deleted" && (
          <button onClick={() => useStore.getState().openFile(f.path)} title={t("open")} className="shrink-0 rounded p-0.5 text-subtle hover:bg-hover hover:text-fg">
            <SquareArrowOutUpRight size={12} />
          </button>
        )}
      </div>
      {open && hasDiff && (
        <div className="px-3 pb-2.5">
          {f.status !== "deleted" && (
            <div className="mb-1.5 flex justify-end">
              <button onClick={() => useStore.getState().openFile(f.path, true)}
                className="flex items-center gap-1 rounded-md border border-line bg-elev px-2 py-0.5 text-[11px] font-medium text-muted hover:border-accent hover:text-accent">
                <Code2 size={12} />{t("open_editor")}
              </button>
            </div>
          )}
          {byOps && list.some((o) => o.diff) ? list.map((o, i) => (
            <OpDiff key={o.id} o={o} i={i} many={list.length > 1} />
          )) : <DiffView diff={net} height="max-h-[28rem]" />}
        </div>
      )}
    </div>
  );
}

function Group({ id, Icon, files, ops, openSet, toggle, view, start }) {
  const t = useT();
  const [open, setOpen] = useState(start);
  const text = files.filter((f) => !f.binary);
  const sum = text.reduce((a, f) => { const c = fileCounts(f, ops[f.path]); return { added: a.added + c.added, removed: a.removed + c.removed }; }, { added: 0, removed: 0 });
  const bytes = files.filter((f) => f.binary).reduce((n, f) => n + (f.size || 0), 0);
  return (
    <div className="border-t border-line first:border-t-0">
      <button onClick={() => setOpen(!open)} className="flex w-full items-center gap-2 bg-panel/60 px-3 py-1.5 text-left text-[12px] font-medium hover:bg-hover">
        {open ? <ChevronDown size={13} className="text-subtle" /> : <ChevronRight size={13} className="text-subtle" />}
        <Icon size={13} className="text-muted" />
        <span>{t(`cat_${id}`)}</span>
        <span className="rounded-full bg-hover px-1.5 text-[10.5px] text-muted">{files.length}</span>
        <span className="ml-auto font-normal">{text.length ? <Lines {...sum} /> : bytes ? <span className="text-[11px] text-subtle">{kb(bytes)}</span> : null}</span>
      </button>
      {open && files.map((f) => <Row key={f.path} f={f} ops={ops[f.path]} open={openSet.has(f.path)} onToggle={() => toggle(f.path)} view={view} />)}
    </div>
  );
}

// Review card: every file the task added, changed or deleted, by tools or by commands/scripts, grouped by type
// (code, documents, images...). The same card shows the files of a running task, updated with every operation, and
// the final review. Line counts add up every operation of the task, the same numbers its steps show (written +597,
// edited +2 −2 twice: +601 −4); changes made by commands use the net diff. Each file is an accordion; "Open all
// diffs" opens them all in place, with a search and a total / by-operation view.
function ChangesCard({ changes, steps, live = false }) {
  const t = useT();
  const files = changes.files;
  const many = files.length > 8;
  const [open, setOpen] = useState(live || files.length <= 12);
  const [openSet, setOpenSet] = useState(() => new Set());
  const [review, setReview] = useState(false);
  const [query, setQuery] = useState("");
  // A file written and then edited shows each operation by default: its edits (+ and −) are what was changed; the
  // total of a new file is only its whole content in green.
  const [view, setView] = useState(() => (Object.values(opsByFile(steps)).some((l) => l.length > 1) ? "ops" : "net"));
  const ops = useMemo(() => opsByFile(steps), [steps]);
  const byCommand = files.filter((f) => f.source === "command").length;
  const totals = useMemo(() => files.filter((f) => !f.binary).reduce((a, f) => {
    const c = fileCounts(f, ops[f.path]);
    return { added: a.added + c.added, removed: a.removed + c.removed };
  }, { added: 0, removed: 0 }), [files, ops]);
  const shown = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return files;
    return files.filter((f) => f.path.toLowerCase().includes(q) || (f.diff || "").toLowerCase().includes(q)
      || (ops[f.path] || []).some((o) => (o.diff || "").toLowerCase().includes(q)));
  }, [files, ops, query]);
  const groups = useMemo(() => {
    const by = {};
    for (const f of shown) (by[fileCategory(f.path)] ||= []).push(f);
    return GROUPS.filter(([id]) => by[id]?.length).map(([id, Icon]) => [id, Icon, by[id]]);
  }, [shown]);
  const toggle = (p) => setOpenSet((s) => { const n = new Set(s); n.has(p) ? n.delete(p) : n.add(p); return n; });
  const openAll = () => {
    if (review) { setReview(false); setOpenSet(new Set()); return; }
    setReview(true); setOpen(true);
    setOpenSet(new Set(files.filter((f) => !f.binary).map((f) => f.path)));
  };
  return (
    <div className="my-2 overflow-hidden rounded-2xl border border-line bg-elev">
      <div className="flex items-center gap-2 px-3 py-2">
        <button onClick={() => setOpen(!open)} className="flex min-w-0 flex-1 items-center gap-1.5 text-left text-[13px] font-medium">
          {open ? <ChevronDown size={14} className="text-subtle" /> : <ChevronRight size={14} className="text-subtle" />}
          <GitCompareArrows size={15} className="text-accent" />
          {t(live ? "changes_live" : "changes_title", { n: files.length + (changes.more || 0) })}
          <span className="text-[11.5px] font-normal"><Lines {...totals} /></span>
          {live && <span className="flex items-center gap-1 rounded-full bg-accent-soft px-1.5 py-px text-[10.5px] font-medium text-accent"><span className="h-1.5 w-1.5 animate-pulse rounded-full bg-accent" />{t("diffs_live")}</span>}
          {byCommand > 0 && <span className="hidden truncate text-[11.5px] font-normal text-subtle sm:inline">· {t("changes_by_commands", { n: byCommand })}</span>}
        </button>
        {!open && groups.length > 1 && (
          <span className="hidden shrink-0 gap-1 md:flex">
            {groups.map(([id, Icon, list]) => (
              <span key={id} className="flex items-center gap-1 rounded-md bg-hover px-1.5 py-px text-[10.5px] text-muted"><Icon size={11} />{list.length}</span>
            ))}
          </span>
        )}
        {files.some((f) => !f.binary) && (
          <button onClick={openAll} className="shrink-0 rounded-lg px-2 py-0.5 text-[11.5px] text-accent hover:bg-hover">{t(review ? "changes_collapse" : "changes_expand")}</button>
        )}
      </div>
      {open && review && (
        <div className="flex flex-wrap items-center gap-2 border-t border-line bg-panel/40 px-3 py-1.5">
          <label className="flex min-w-[180px] flex-1 items-center gap-1.5 rounded-lg border border-line bg-elev px-2 py-1 text-[12px] focus-within:border-accent">
            <Search size={13} className="shrink-0 text-subtle" />
            <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder={t("diffs_search")}
              className="min-w-0 flex-1 bg-transparent outline-none placeholder:text-subtle" />
            {query && <button onClick={() => setQuery("")} className="text-subtle hover:text-fg"><X size={12} /></button>}
          </label>
          <div className="flex items-center gap-0.5 rounded-lg bg-hover p-0.5 text-[11.5px]">
            {["net", "ops"].map((v) => (
              <button key={v} onClick={() => setView(v)} className={`rounded-md px-2 py-0.5 ${view === v ? "bg-elev font-medium shadow-sm" : "text-muted hover:text-fg"}`}>{t(`diffs_view_${v}`)}</button>
            ))}
          </div>
          {query && <span className="text-[11px] text-subtle">{t("diffs_found", { n: shown.length })}</span>}
        </div>
      )}
      {open && (
        <div className={`${review ? "max-h-[75vh]" : "max-h-[420px]"} overflow-y-auto border-t border-line`}>
          {groups.length > 1 || many
            ? groups.map(([id, Icon, list]) => <Group key={`${id}-${review}`} id={id} Icon={Icon} files={list} ops={ops} openSet={openSet} toggle={toggle} view={view} start={review || !many || list.length <= 4} />)
            : shown.map((f) => <Row key={f.path} f={f} ops={ops[f.path]} open={openSet.has(f.path)} onToggle={() => toggle(f.path)} view={view} />)}
          {!shown.length && <div className="px-3 py-3 text-[12px] text-subtle">{t("diffs_none")}</div>}
          {(changes.more > 0 || changes.partial) && (
            <div className="border-t border-line px-3 py-1.5 text-[11.5px] text-subtle">
              {changes.more > 0 && t("changes_more", { n: changes.more })} {changes.partial && t("changes_partial")}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default memo(ChangesCard);
