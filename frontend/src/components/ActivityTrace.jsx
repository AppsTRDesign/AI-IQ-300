import { memo, useState } from "react";
import {
  AlertTriangle, Archive, Brain, Bug, Check, ChevronDown, ChevronRight, FileCode2, FileText, FolderTree, GitCommit, Globe,
  Image, ListChecks, Loader2, MessageSquareText, Play, Search, ShieldAlert, Terminal, X, Trash2, Square, Cloud, Sparkles,
} from "lucide-react";
import { useStore, useT } from "../lib/store";
import CodeBlock from "./CodeBlock";

const KIND = {
  thinking: [Brain, "thinking"], plan: [ListChecks, "step_plan"], file: [FileCode2, "step_file"],
  read: [FileText, "step_read"], list: [FolderTree, "step_list"], command: [Terminal, "step_command"],
  process: [Play, "step_process"], search: [Search, "step_search"], fetch: [Globe, "step_fetch"],
  visual: [Image, "step_visual"], debug: [Bug, "step_debug"], git: [GitCommit, "step_git"],
  document: [FileText, "step_document"], approval: [ShieldAlert, "approval_needed"], policy: [ShieldAlert, "approval_needed"],
  note: [MessageSquareText, "step_note"], compress: [Archive, "step_compress"], prepare: [Loader2, "step_prepare"],
  delete: [Trash2, "step_delete"], stop: [Square, "step_stop"], fallback: [Cloud, "step_fallback"],
  budget: [AlertTriangle, "step_budget"], skill: [Sparkles, "step_skill"],
};

const Step = memo(function Step({ step }) {
  const t = useT();
  const [open, setOpen] = useState(false);
  const [Icon, key] = KIND[step.kind] || [AlertTriangle, step.kind];
  const d = step.data || {};
  const running = step.status === "running";
  const showTitle = !["thinking", "note", "compress"].includes(step.kind);
  const chars = step.kind !== "prepare" ? "" : (d.chars ? ` · ${d.chars > 999 ? (d.chars / 1000).toFixed(1) + "K" : d.chars} ${t("chars")}` : "")
    + (d.seconds ? ` · ${d.seconds} ${t("unit_s")}` : "");
  return (
    <div className="text-[13px]">
      <button onClick={() => step.detail && setOpen(!open)}
        className="group flex w-full items-center gap-2 rounded-lg px-1.5 py-1 text-left text-muted hover:bg-hover">
        <span className={`grid h-5 w-5 shrink-0 place-items-center rounded-md ${step.status === "error" ? "bg-danger/10 text-danger" : running ? "bg-accent-soft text-accent" : "bg-hover"}`}>
          {running ? <Loader2 size={12} className="animate-spin" /> : <Icon size={12} />}
        </span>
        <span className={`shrink-0 font-medium ${running ? "shimmer" : "text-fg/80"}`}>{t(key)}</span>
        {showTitle && <span className="truncate font-mono text-xs text-subtle">{step.kind === "prepare" ? t(`tool_${step.title}`) : step.title}{chars}</span>}
        <span className="ml-auto flex shrink-0 items-center gap-1">
          {step.status === "error" && <X size={13} className="text-danger" />}
          {step.status === "done" && step.kind !== "thinking" && <Check size={13} className="text-ok opacity-0 group-hover:opacity-100" />}
          {step.detail && (open ? <ChevronDown size={13} /> : <ChevronRight size={13} />)}
        </span>
      </button>
      {open && step.detail && (
        <div className="fade-in ml-7 mt-1">
          {d.tool === "write_file" ? (
            <>
              <CodeBlock code={step.detail} language={d.language} path={d.path} />
              <button onClick={() => useStore.getState().openFile(d.path)} className="text-xs text-accent hover:underline">{t("open_editor")}</button>
            </>
          ) : (
            <pre className="max-h-72 overflow-auto whitespace-pre-wrap rounded-xl border border-line bg-code p-2.5 font-mono text-xs text-muted">{step.detail}</pre>
          )}
        </div>
      )}
    </div>
  );
});

// Steps are always grouped under one header. While a run is live the group stays collapsed and shows only the
// current step, so a long task never turns into a long list; a click opens every step (live or finished).
function ActivityTrace({ steps, live }) {
  const t = useT();
  const [open, setOpen] = useState(false);
  if (!steps?.length) return null;
  const errors = steps.filter((s) => s.status === "error").length;
  const current = live ? [...steps].reverse().find((s) => s.status === "running") || steps[steps.length - 1] : null;
  return (
    <div className="mb-2">
      <button onClick={() => setOpen(!open)} className="flex items-center gap-1.5 rounded-lg px-1.5 py-0.5 text-[13px] text-muted hover:bg-hover">
        {open ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
        {live && <Loader2 size={12} className="animate-spin text-accent" />}
        {t(live ? "steps_live" : "steps", { n: steps.length })}
        {errors > 0 && <span className="rounded bg-danger/10 px-1 text-[11px] text-danger">{errors}</span>}
      </button>
      {(open || current) && (
        <div className="ml-2 mt-1 border-l border-line pl-2">
          {open ? steps.map((s) => <Step key={s.id} step={s} />) : <Step key={current.id} step={current} />}
        </div>
      )}
    </div>
  );
}

export default memo(ActivityTrace);
