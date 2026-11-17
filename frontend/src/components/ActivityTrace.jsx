import { memo, useEffect, useState } from "react";
import {
  AlertTriangle, Archive, Brain, Bug, Check, ChevronDown, ChevronRight, FileCode2, FileText, FolderTree, GitCommit, Globe,
  Image, ListChecks, Loader2, MessageSquareText, Play, Search, ShieldAlert, Terminal, X, Trash2, Square, Cloud, Sparkles, RotateCw,
  FilePen, FileSearch, Users, BookMarked, Plug, Camera, MapPin, CornerDownRight, Cpu,
} from "lucide-react";
import { useStore, useT } from "../lib/store";
import { api } from "../lib/api";
import CodeBlock from "./CodeBlock";
import Markdown from "./Markdown";

const KIND = {
  thinking: [Brain, "thinking"], plan: [ListChecks, "step_plan"], file: [FileCode2, "step_file"],
  read: [FileText, "step_read"], list: [FolderTree, "step_list"], command: [Terminal, "step_command"],
  process: [Play, "step_process"], search: [Search, "step_search"], fetch: [Globe, "step_fetch"],
  visual: [Image, "step_visual"], debug: [Bug, "step_debug"], git: [GitCommit, "step_git"],
  document: [FileText, "step_document"], approval: [ShieldAlert, "approval_needed"], policy: [ShieldAlert, "approval_needed"],
  note: [MessageSquareText, "step_note"], compress: [Archive, "step_compress"], prepare: [Loader2, "step_prepare"],
  delete: [Trash2, "step_delete"], stop: [Square, "step_stop"], fallback: [Cloud, "step_fallback"],
  budget: [AlertTriangle, "step_budget"], skill: [Sparkles, "step_skill"], retry: [RotateCw, "step_retry"],
  edit: [FilePen, "step_edit"], grep: [FileSearch, "step_grep"], delegate: [Users, "step_delegate"], memory: [BookMarked, "step_memory"],
  mcp: [Plug, "step_mcp"], team: [Users, "step_team"], screenshot: [Camera, "step_screenshot"], catalog: [Sparkles, "step_catalog"],
  places: [MapPin, "step_places"], photo: [Image, "step_photo"], system: [Cpu, "step_system"], system_info: [Cpu, "step_system"],
};

// Internal titles that only repeat the step kind are not shown; error codes (retry) are shown by their name.
const HIDDEN_TITLES = new Set(["thinking", "tools", "context", "planner", "debugger", "approval", "policy", "process", "language",
  "iteration budget exhausted", "unavailable"]);
const shownTitle = (t, step) => {
  if (step.kind === "retry") { const k = `cd_${step.title}`; const v = t(k); return v === k ? step.title : v; }
  return step.title === step.kind || HIDDEN_TITLES.has(step.title) ? "" : step.title;
};

// While a file step runs (e.g. waiting for approval) nothing has changed yet: present tense.
const RUNNING_KEY = { photo: "step_photo_running", file: "step_file_running", edit: "step_edit_running", delete: "step_delete_running", screenshot: "step_screenshot_running" };

// Unified diff (edit_file step, approval card): added lines green, removed red, hunk headers muted.
export function DiffView({ diff, height = "max-h-80" }) {
  const lines = diff.split("\n").filter((l) => !l.startsWith("--- ") && !l.startsWith("+++ "));
  return (
    <pre className={`${height} overflow-auto rounded-xl border border-line bg-code py-1.5 font-mono text-xs leading-relaxed`}>
      {lines.map((l, i) => (
        <div key={i} className={`px-2.5 ${l.startsWith("+") ? "bg-ok/10 text-ok" : l.startsWith("-") ? "bg-danger/10 text-danger"
          : l.startsWith("@@") ? "text-subtle" : "text-muted"}`}>{l || " "}</div>
      ))}
    </pre>
  );
}

// A compress step's detail is a small JSON object ({before, after, compressed, mode}), never shown raw: a plain
// sentence with the token drop and, for a summary pass, how many messages were folded into it.
function CompressSummary({ detail, t }) {
  let c;
  try { c = JSON.parse(detail); } catch { c = null; }
  if (!c || typeof c.before !== "number" || typeof c.after !== "number") {
    return <pre className="max-h-72 overflow-auto whitespace-pre-wrap rounded-xl border border-line bg-code p-2.5 font-mono text-xs text-muted">{detail}</pre>;
  }
  const pct = c.before > 0 ? Math.round((1 - c.after / c.before) * 100) : 0;
  return (
    <div className="rounded-xl border border-line bg-panel/60 px-3 py-2 text-xs text-muted">
      <div className="font-mono text-fg/80">
        {c.before.toLocaleString()} → {c.after.toLocaleString()} {t("unit_tokens")}
        {pct > 0 && <span className="ml-1.5 text-ok">(−%{pct})</span>}
      </div>
      {c.mode === "summary" && c.compressed != null && (
        <div className="mt-0.5 text-subtle">{t("compress_messages_folded", { n: c.compressed })}</div>
      )}
      {c.mode === "trim" && <div className="mt-0.5 text-subtle">{t("compress_trim_desc")}</div>}
    </div>
  );
}

const Step = memo(function Step({ step: given }) {
  const t = useT();
  const [open, setOpen] = useState(false);
  // A stored step whose long detail came cut (see the messages API): the whole of it loads when it is opened.
  const [full, setFull] = useState(null);
  useEffect(() => {
    if (!open || full || !given.lazy) return;
    api.get(`/api/messages/${given.lazy.mid}/steps/${given.lazy.i}`).then(setFull).catch(() => {});
  }, [open, full, given.lazy]);
  const step = full || given;
  if (step.kind === "note" && step.title === "steer") {
    // A message the user sent while the task ran: shown as the user's own words, where the model picked it up.
    return (
      <div className="fade-in my-1 flex items-start gap-2 rounded-xl border border-accent/30 bg-accent-soft/60 px-2.5 py-1.5 text-[13px]">
        <span className="mt-px grid h-5 w-5 shrink-0 place-items-center rounded-md bg-accent text-accent-fg"><CornerDownRight size={12} /></span>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-accent">
            {t("steer_applied")}<Check size={12} />
          </div>
          <div className="whitespace-pre-wrap break-words text-fg/90">{step.detail}</div>
        </div>
      </div>
    );
  }
  const [Icon, key0] = KIND[step.kind] || [AlertTriangle, step.kind];
  // A stream that stopped mid-file is not a busy provider: its own heading (the file is kept and continued).
  const key = step.kind === "retry" && step.title === "stalled" ? "step_retry_stalled" : key0;
  const d = step.data || {};
  const running = step.status === "running";
  const showTitle = !["thinking", "note", "compress"].includes(step.kind);
  const noteLine = step.kind === "note" ? (step.detail || "").split("\n").find((l) => l.trim())?.replace(/[#*`>]/g, "").trim() : "";
  const lines = (step.kind === "edit" || step.kind === "file") && step.status === "done" && d.added != null ? ` · +${d.added} −${d.removed}` : "";
  // The live label already names the file and its characters: only the elapsed time is added here (it was shown twice).
  const chars = step.kind === "retry" ? ` · ${d.seconds} ${t("unit_s")} · #${d.attempt}` : step.kind !== "prepare" ? ""
    : (d.seconds ? ` · ${fmtDur(t, d.seconds * 1000)}` : "");
  return (
    <div className="text-[13px]">
      <button onClick={() => step.detail && setOpen(!open)}
        className="group flex w-full items-center gap-2 rounded-lg px-1.5 py-1 text-left text-muted hover:bg-hover">
        <span className={`grid h-5 w-5 shrink-0 place-items-center rounded-md ${step.status === "error" ? "bg-danger/10 text-danger" : running ? "bg-accent-soft text-accent" : "bg-hover"}`}>
          {running ? <Loader2 size={12} className="animate-spin" /> : <Icon size={12} />}
        </span>
        <span className={`shrink-0 font-medium ${running ? "shimmer" : "text-fg/80"}`}>{t(running && RUNNING_KEY[step.kind] || key)}</span>
        {noteLine && <span className="truncate text-xs text-subtle">{noteLine}</span>}
        {showTitle && <span className="truncate font-mono text-xs text-subtle">{step.kind === "prepare" ? prepareLabel(t, d, step.title) : shownTitle(t, step)}{chars}{lines}</span>}
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
          ) : d.tool === "edit_file" && d.diff ? (
            <>
              <DiffView diff={d.diff} />
              <button onClick={() => useStore.getState().openFile(d.path)} className="text-xs text-accent hover:underline">{t("open_editor")}</button>
            </>
          ) : step.kind === "note" ? (
            <div className="note-md max-h-80 overflow-auto rounded-xl border border-line bg-panel/60 px-3 py-1.5"><Markdown text={step.detail} /></div>
          ) : step.kind === "compress" ? (
            <CompressSummary detail={step.detail} t={t} />
          ) : ["run", "start"].includes(d.tool) && (d.command || d.args?.argv) ? (
            <>
              {/* The exact command that ran (shell, folder), then its output. */}
              <div className="mb-1 flex flex-wrap items-center gap-x-2 text-[11px] text-subtle">
                <span className="rounded bg-hover px-1.5 py-px font-mono">{d.args?.shell || (d.args?.argv ? "exec" : "")}</span>
                {d.args?.cwd && <span className="truncate font-mono">{d.args.cwd}</span>}
              </div>
              <CodeBlock code={d.command || (Array.isArray(d.args.argv) ? d.args.argv.join(" ") : String(d.args.argv))}
                language={{ powershell: "powershell", powershell5: "powershell", pwsh: "powershell", bash: "shell", cmd: "bat", python: "python", node: "javascript", php: "php" }[d.args?.shell] || "shell"} />
              <pre className="mt-1 max-h-72 overflow-auto whitespace-pre-wrap rounded-xl border border-line bg-code p-2.5 font-mono text-xs text-muted">{step.detail}</pre>
            </>
          ) : (
            <pre className="max-h-72 overflow-auto whitespace-pre-wrap rounded-xl border border-line bg-code p-2.5 font-mono text-xs text-muted">{step.detail}</pre>
          )}
        </div>
      )}
    </div>
  );
});

// Screenshots the model took while working, shown inline (also while the step list is collapsed);
// a click opens them in the image viewer.
export const shotsOf = (steps) => (steps || []).filter((s) => s.kind === "screenshot" && s.status === "done" && s.data?.screenshot
  && /\.(png|jpe?g)$/i.test(s.data.screenshot));
const rawUrl = (path) => useStore.getState().fileApi(`/fs/raw?path=${encodeURIComponent(path)}`);

function ShotStrip({ shots }) {
  const t = useT();
  const paths = shots.map((s) => s.data.screenshot);
  return (
    <div className="ml-2 mt-1.5 flex flex-wrap gap-2 pl-2">
      {shots.map((s, i) => {
        const [w, h] = s.data.size || [];
        let host = s.data.url || "";
        try { host = new URL(host).host || host; } catch {}
        return (
          <button key={s.id} onClick={() => useStore.getState().viewImages(paths, i)} title={`${t("open_image")} · ${s.data.title || s.data.url || ""}`}
            className="group w-[min(100%,300px)] overflow-hidden rounded-xl border border-line bg-elev text-left shadow-[0_1px_4px_rgb(0_0_0/0.05)] transition hover:border-accent/50 hover:shadow-md">
            <div className="relative h-[168px] overflow-hidden bg-panel">
              <img src={rawUrl(s.data.screenshot)} alt={s.data.title || host} loading="lazy"
                className="h-full w-full object-cover object-top transition duration-300 group-hover:scale-[1.02]" />
              <span className="absolute right-1.5 top-1.5 rounded-md bg-black/55 px-1.5 py-0.5 text-[10px] font-medium text-white opacity-0 transition group-hover:opacity-100">{t("open_image")}</span>
            </div>
            <div className="flex items-center gap-1.5 border-t border-line px-2.5 py-1.5">
              <Camera size={12} className="shrink-0 text-subtle" />
              <span className="min-w-0 flex-1 truncate text-[11.5px] font-medium text-fg/80">{s.data.title || host}</span>
              {w && h && <span className="shrink-0 font-mono text-[10.5px] text-subtle">{w}×{h}</span>}
            </div>
          </button>
        );
      })}
    </div>
  );
}

// Steps are always grouped under one header. While a run is live the group stays collapsed and shows only the
// current step, so a long task never turns into a long list; a click opens every step (live or finished).
const sec = (ms) => (ms >= 10000 ? (ms / 1000).toFixed(0) : (ms / 1000).toFixed(1));

// "42 sn", "1 dk 30 sn", "1 sa 4 dk": how long a task has been (or was) running.
export function fmtDur(t, ms) {
  const s = Math.max(0, Math.round(ms / 1000));
  if (s < 60) return `${s} ${t("unit_s")}`;
  if (s < 3600) return `${Math.floor(s / 60)} ${t("unit_m")} ${s % 60} ${t("unit_s")}`;
  return `${Math.floor(s / 3600)} ${t("unit_h")} ${Math.floor((s % 3600) / 60)} ${t("unit_m")}`;
}

// Ticks every second while the task runs.
function Elapsed({ since }) {
  const t = useT();
  const [, tick] = useState(0);
  useEffect(() => { const i = setInterval(() => tick((n) => n + 1), 1000); return () => clearInterval(i); }, []);
  return <span className="font-mono text-[12px] tabular-nums text-accent">· {fmtDur(t, Date.now() - (since || Date.now()))}</span>;
}

// What the model is doing while a "preparing" step shows: waiting for the first token, writing the answer or a tool
// call (streamed or sent at the end by the provider).
function prepareLabel(t, d, title) {
  const tok = d.prompt_tokens ? (d.prompt_tokens >= 1000 ? `${(d.prompt_tokens / 1000).toFixed(1)}K` : d.prompt_tokens) : "?";
  // The model only while waiting for its first answer (which one is slow to start); while it writes, the file and
  // its size say everything ("auto · 15.5K" repeated what was already there).
  const model = d.model && d.phase === "first" ? ` · ${String(d.model).split(":").slice(1).join(":")}` : "";
  // Always concrete: which file and how many characters so far, or how long nothing came and what happens next.
  const kb = (n) => (n >= 1000 ? `${(n / 1000).toFixed(1)}K` : String(n));
  const target = d.target ? ` · ${d.target}` : "";
  const text = d.phase === "first" ? t("prep_first", { tok })
    : d.phase === "tool_stream" ? `${t("prep_tool_stream")}: ${t(`tool_${title}`)}${target} · ${t("prep_chars", { n: kb(d.chars || 0) })}`
      : d.phase === "tool_silent"
        ? (d.local ? t("prep_tool_silent_local", { s: d.idle || 0 })
          : d.switch_in != null ? t("prep_tool_silent_switch", { s: d.idle || 0, left: d.switch_in })
            : t("prep_tool_silent_wait", { s: d.idle || 0 }))
        : d.phase === "stalled" ? (d.stall_in != null ? t("prep_stalled", { s: d.idle || 0, left: d.stall_in }) : t("prep_stalled_local", { s: d.idle || 0 }))
          : d.phase === "writing" ? t("prep_writing") : t(`tool_${title}`);
  return text + model;
}

// Where a finished task spent its time: first answer, the model (waiting for its first token), tools, team, overhead.
function TimingRow({ timing }) {
  const t = useT();
  const u = t("unit_s");
  const tools = Object.entries(timing.tools || {}).sort((a, b) => b[1].ms - a[1].ms).slice(0, 4);
  const parts = [
    timing.first_ms != null && [t("timing_first"), `${sec(timing.first_ms)} ${u}`],
    [t("timing_model"), `${sec(timing.model_ms)} ${u}` + (timing.turns ? ` · ${t("timing_turns", { n: timing.turns })}` : "")
      + (timing.model_wait_ms ? ` · ${t("timing_wait")} ${sec(timing.model_wait_ms)} ${u}` : "")],
    timing.tools_ms > 0 && [t("timing_tools"), `${sec(timing.tools_ms)} ${u}` + (tools.length ? " (" + tools.map(([k, v]) => `${k} ${sec(v.ms)}${v.n > 1 ? `×${v.n}` : ""}`).join(", ") + ")" : "")],
    timing.team_ms > 0 && [t("timing_team"), `${sec(timing.team_ms)} ${u}`],
    timing.side_ms > 0 && [t("timing_side"), `${sec(timing.side_ms)} ${u}`],
    timing.retry_ms > 0 && [t("timing_retry"), `${sec(timing.retry_ms)} ${u}`],
    [t("timing_app"), `${sec(timing.overhead_ms)} ${u}`],
  ].filter(Boolean);
  return (
    <div className="mb-1 ml-2 flex flex-wrap gap-x-3 gap-y-0.5 border-l border-line pl-2 text-[11.5px] text-subtle">
      {parts.map(([k, v]) => <span key={k}><span className="text-muted">{k}</span> {v}</span>)}
    </div>
  );
}

const STEP_WINDOW = 60;

function ActivityTrace({ steps, live, timing, started }) {
  const t = useT();
  const [open, setOpen] = useState(false);
  const [all, setAll] = useState(false);
  if (!steps?.length) return null;
  // Long tasks have hundreds of steps: the open list shows the latest ones (older on demand), so the browser does
  // not lay out and re-render every step on each live update.
  const shown = open && !all && steps.length > STEP_WINDOW ? steps.slice(-STEP_WINDOW) : steps;
  const errors = steps.filter((s) => s.status === "error").length;
  const current = live ? [...steps].reverse().find((s) => s.status === "running") || steps[steps.length - 1] : null;
  const shots = shotsOf(steps);
  return (
    <div className="mb-2">
      <button onClick={() => setOpen(!open)} className="flex items-center gap-1.5 rounded-lg px-1.5 py-0.5 text-[13px] text-muted hover:bg-hover">
        {open ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
        {live && <Loader2 size={12} className="animate-spin text-accent" />}
        {t(live ? "steps_live" : "steps", { n: steps.length })}
        {errors > 0 && <span className="rounded bg-danger/10 px-1 text-[11px] text-danger">{errors}</span>}
        {live && <Elapsed since={started} />}
        {!live && timing?.total_ms != null && <span className="text-[12px] text-subtle">· {fmtDur(t, timing.total_ms)}</span>}
      </button>
      {open && timing?.total_ms != null && <TimingRow timing={timing} />}
      {(open || current) && (
        <div className="ml-2 mt-1 border-l border-line pl-2">
          {open && shown.length < steps.length && (
            <button onClick={() => setAll(true)} className="mb-1 rounded-lg px-1.5 py-0.5 text-[12px] text-accent hover:bg-hover">
              {t("steps_earlier", { n: steps.length - shown.length })}
            </button>
          )}
          {open ? shown.map((s) => <Step key={s.id} step={s} />) : <Step key={current.id} step={current} />}
        </div>
      )}
      {shots.length > 0 && <ShotStrip shots={shots} />}
    </div>
  );
}

export default memo(ActivityTrace);
