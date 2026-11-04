import { memo, useState } from "react";
import { ChevronDown, ChevronRight, FileCode2, GitCompareArrows, SquareArrowOutUpRight } from "lucide-react";
import { useStore, useT } from "../lib/store";
import { DiffView } from "./ActivityTrace";

const STATUS = {
  added: ["A", "bg-ok/12 text-ok"], modified: ["M", "bg-warn/15 text-warn"], deleted: ["D", "bg-danger/12 text-danger"],
};
const kb = (n) => (n >= 1048576 ? `${(n / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1024))} KB`);

function Row({ f, openAll }) {
  const t = useT();
  const [open, setOpen] = useState(false);
  const shown = open || openAll;
  const [letter, cls] = STATUS[f.status] || STATUS.modified;
  const canOpen = f.status !== "deleted";
  return (
    <div className="border-t border-line first:border-t-0">
      <div className="flex min-w-0 items-center gap-2 px-3 py-1.5 text-[12.5px]">
        <button onClick={() => setOpen(!open)} disabled={!f.diff} className="flex min-w-0 flex-1 items-center gap-2 text-left disabled:cursor-default">
          {f.diff ? (shown ? <ChevronDown size={13} className="shrink-0 text-subtle" /> : <ChevronRight size={13} className="shrink-0 text-subtle" />)
            : <FileCode2 size={13} className="shrink-0 text-subtle" />}
          <span className={`grid h-4 w-4 shrink-0 place-items-center rounded text-[10px] font-bold ${cls}`} title={t(`change_${f.status}`)}>{letter}</span>
          <span className={`truncate font-mono ${f.status === "deleted" ? "text-muted line-through" : ""}`} title={f.path}>{f.path}</span>
        </button>
        <span className={`shrink-0 rounded-md px-1.5 py-px text-[10.5px] font-medium ${f.source === "command" ? "bg-accent-soft text-accent" : "bg-hover text-muted"}`}
          title={t(f.source === "command" ? "change_by_command_hint" : "change_by_tool_hint")}>
          {t(f.source === "command" ? "change_by_command" : "change_by_tool")}
        </span>
        {f.binary ? <span className="shrink-0 text-[11px] text-subtle">{f.status === "modified" ? `${kb(f.size_before)} → ${kb(f.size)}` : kb(f.size)}</span>
          : <span className="shrink-0 font-mono text-[11px]"><span className="text-ok">+{f.added}</span> <span className="text-danger">−{f.removed}</span></span>}
        {canOpen && (
          <button onClick={() => useStore.getState().openFile(f.path)} title={t("open_in_editor")} className="shrink-0 rounded p-0.5 text-subtle hover:bg-hover hover:text-fg">
            <SquareArrowOutUpRight size={12} />
          </button>
        )}
      </div>
      {shown && f.diff && <div className="px-3 pb-2"><DiffView diff={f.diff} height="max-h-96" /></div>}
    </div>
  );
}

// Review card: every file the task added, changed or deleted in its folder, by tools or by commands/scripts.
function ChangesCard({ changes }) {
  const t = useT();
  const [open, setOpen] = useState(changes.files.length <= 6);
  const [all, setAll] = useState(false);
  const byCommand = changes.files.filter((f) => f.source === "command").length;
  return (
    <div className="my-2 overflow-hidden rounded-2xl border border-line bg-elev">
      <div className="flex items-center gap-2 px-3 py-2">
        <button onClick={() => setOpen(!open)} className="flex min-w-0 flex-1 items-center gap-1.5 text-left text-[13px] font-medium">
          {open ? <ChevronDown size={14} className="text-subtle" /> : <ChevronRight size={14} className="text-subtle" />}
          <GitCompareArrows size={15} className="text-accent" />
          {t("changes_title", { n: changes.files.length + (changes.more || 0) })}
          <span className="font-mono text-[11.5px] font-normal"><span className="text-ok">+{changes.added}</span> <span className="text-danger">−{changes.removed}</span></span>
          {byCommand > 0 && <span className="truncate text-[11.5px] font-normal text-subtle">· {t("changes_by_commands", { n: byCommand })}</span>}
        </button>
        {open && changes.files.some((f) => f.diff) && (
          <button onClick={() => setAll(!all)} className="shrink-0 rounded-lg px-2 py-0.5 text-[11.5px] text-accent hover:bg-hover">{t(all ? "changes_collapse" : "changes_expand")}</button>
        )}
      </div>
      {open && (
        <div className="border-t border-line">
          {changes.files.map((f) => <Row key={f.path} f={f} openAll={all} />)}
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
