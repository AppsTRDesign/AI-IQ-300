import { memo, useState } from "react";
import { AlertCircle, ArrowRight, Circle, CheckCircle2, ChevronDown, ChevronRight, Clock, FileCode2, ListChecks, Loader2, MessagesSquare, Users } from "lucide-react";
import { useT } from "../lib/store";

const STATE = {
  queued: [Clock, "text-subtle", "team_queued"], running: [Loader2, "text-accent", "team_running"],
  done: [CheckCircle2, "text-ok", "team_done"], error: [AlertCircle, "text-danger", "team_error"],
};

function Member({ c, staged }) {
  const t = useT();
  const [open, setOpen] = useState(false);
  const [Icon, color, key] = STATE[c.state] || STATE.queued;
  return (
    <div className="min-w-0 rounded-xl border border-line bg-bg p-2.5">
      <div className="flex items-center gap-1.5">
        <Icon size={14} className={`shrink-0 ${color} ${c.state === "running" ? "animate-spin" : ""}`} />
        {staged && <span className="shrink-0 rounded-md bg-hover px-1.5 text-[10.5px] font-medium text-muted">{t("team_stage", { n: c.stage })}</span>}
        <span className="truncate text-[13px] font-medium">{c.title}</span>
        <span className={`ml-auto shrink-0 text-[11px] ${color}`}>{t(key)}</span>
      </div>
      <div className="mt-1 truncate font-mono text-[11px] text-subtle" title={c.model}>{c.model || "—"}</div>
      <div className="mt-1 flex items-center gap-2 text-[11px] text-muted">
        <span>{t("team_steps", { n: c.steps })}</span>
        {c.last && c.state === "running" && <span className="truncate font-mono">{c.last}</span>}
      </div>
      {c.files?.length > 0 && (
        <div className="mt-1.5 flex flex-wrap gap-1">
          {c.files.slice(0, 6).map((f) => <span key={f} className="flex items-center gap-1 rounded-md bg-hover px-1.5 py-0.5 font-mono text-[10.5px] text-muted"><FileCode2 size={10} />{f}</span>)}
        </div>
      )}
      {c.report && (
        <button onClick={() => setOpen(!open)} className="mt-1.5 flex items-center gap-1 text-[11px] text-accent hover:underline">
          {open ? <ChevronDown size={11} /> : <ChevronRight size={11} />}{t("team_report")}
        </button>
      )}
      {open && <div className="mt-1 max-h-48 overflow-auto whitespace-pre-wrap text-xs leading-relaxed text-muted">{c.report}</div>}
    </div>
  );
}

// Live task board of a parallel agent team (the 'team' step of a run).
function TaskBoard({ steps }) {
  const t = useT();
  const step = [...(steps || [])].reverse().find((s) => s.kind === "team" && s.data?.members);
  if (!step) return null;
  const members = step.data.members;
  const done = members.filter((m) => m.state === "done").length;
  const staged = new Set(members.map((m) => m.stage || 1)).size > 1;
  return (
    <div className="fade-in my-2 rounded-2xl border border-line bg-elev p-3">
      <div className="mb-2 flex items-center gap-1.5 text-[13px] font-semibold">
        <Users size={15} className="text-accent" />{t("team_board")}
        <span className="ml-auto text-xs font-normal text-muted">{done}/{members.length}</span>
      </div>
      <div className="grid gap-2 sm:grid-cols-2">{members.map((c, i) => <Member key={i} c={c} staged={staged} />)}</div>
      {(step.data.tasks?.length > 0 || step.data.messages?.length > 0) && (
        <div className="mt-2 grid gap-2 sm:grid-cols-2">
          {step.data.tasks?.length > 0 && (
            <div className="min-w-0 rounded-xl border border-line bg-bg p-2.5">
              <div className="mb-1.5 flex items-center gap-1.5 text-xs font-medium text-muted"><ListChecks size={13} />{t("team_tasks")}</div>
              {step.data.tasks.map((x) => (
                <div key={x.id} className="flex items-start gap-1.5 py-0.5 text-xs">
                  {x.status === "done" ? <CheckCircle2 size={13} className="mt-px shrink-0 text-ok" />
                    : x.status === "in_progress" ? <Loader2 size={13} className="mt-px shrink-0 animate-spin text-accent" />
                    : <Circle size={13} className="mt-px shrink-0 text-subtle" />}
                  <span className={`min-w-0 flex-1 ${x.status === "done" ? "text-muted line-through" : ""}`}>{x.text}</span>
                  {x.owner && x.owner !== x.text && <span className="shrink-0 text-[11px] text-subtle">{x.owner}</span>}
                </div>
              ))}
            </div>
          )}
          {step.data.messages?.length > 0 && (
            <div className="min-w-0 rounded-xl border border-line bg-bg p-2.5">
              <div className="mb-1.5 flex items-center gap-1.5 text-xs font-medium text-muted"><MessagesSquare size={13} />{t("team_messages")}</div>
              <div className="max-h-48 space-y-1.5 overflow-auto">
                {step.data.messages.map((x, i) => (
                  <div key={i} className="text-xs leading-snug">
                    <span className="inline-flex items-center gap-1 font-medium">{x.from}<ArrowRight size={10} className="text-subtle" />{x.to === "all" ? t("team_to_all") : x.to}</span>
                    <div className="text-muted">{x.text}</div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default memo(TaskBoard);
