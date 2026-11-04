import { memo, useEffect, useLayoutEffect, useRef, useState } from "react";
import { ArrowDown, FileUp, Folder, Laptop, MessageSquareText, ShieldAlert, Square, Volume2 } from "lucide-react";
import TaskBoard from "./TaskBoard";
import ChangesCard from "./ChangesCard";
import { onSpeech, speak, speakingId, speechOpts, speechSupported, stopSpeech } from "../lib/speech";
import { useStore, useT } from "../lib/store";
import Markdown from "./Markdown";
import ActivityTrace, { DiffView, shotsOf } from "./ActivityTrace";
import Composer from "./Composer";
import { Thinking, Logo } from "./Brand";
import { FileChip } from "./ui";
import { ErrorNote } from "./Feedback";
import TodoList from "./TodoList";
import { DocCard } from "./DocPreview";
import OutputGallery from "./OutputGallery";

// Screenshots already show inline in the step trace, so the gallery under the answer leaves them out.
const withoutShots = (outputs, steps) => {
  const shots = new Set(shotsOf(steps).map((s) => s.data.screenshot));
  return shots.size ? (outputs || []).filter((p) => !shots.has(p)) : outputs;
};

// What a file write will change, shown before the user decides: new file, overwrite, edit or deletion.
function ChangePreview({ p }) {
  const t = useT();
  const [full, setFull] = useState(false);
  return (
    <div>
      <div className="mb-1.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs">
        <span className={`rounded-md px-1.5 py-0.5 font-medium ${p.kind === "delete" ? "bg-danger/10 text-danger" : p.kind === "new" ? "bg-ok/10 text-ok" : "bg-accent-soft text-accent"}`}>
          {t(`preview_${p.kind}`)}</span>
        <span className="min-w-0 truncate font-mono text-muted" title={p.path}>{p.path}</span>
        {!p.binary && <span className="font-mono tabular-nums"><span className="text-ok">+{p.added}</span> <span className="text-danger">−{p.removed}</span></span>}
        {p.diff && <button onClick={() => setFull(!full)} className="ml-auto text-accent hover:underline">{t(full ? "preview_collapse" : "preview_expand")}</button>}
      </div>
      {p.binary ? <div className="rounded-xl bg-elev p-2.5 text-xs text-muted">{t("preview_binary")}</div>
        : p.diff ? <DiffView diff={p.diff} height={full ? "max-h-[70vh]" : "max-h-72"} />
        : <div className="rounded-xl bg-elev p-2.5 text-xs text-muted">{t("preview_empty")}</div>}
      {p.truncated && <div className="mt-1 text-[11px] text-subtle">{t("preview_truncated")}</div>}
    </div>
  );
}

const Approval = memo(function Approval({ sid, a }) {
  const t = useT();
  const op = a.op || {};
  const label = t(`appr_${a.category}`);
  const category = label.startsWith("appr_") ? a.category : label;
  return (
    <div className="fade-in my-2 rounded-2xl border border-warn/40 bg-warn/10 p-3 text-[13px]">
      <div className="mb-1.5 flex items-center gap-1.5 font-semibold text-warn"><ShieldAlert size={15} /> {t("approval_needed")} · {category}</div>
      {a.preview ? <ChangePreview p={a.preview} /> : (
        <pre className="max-h-48 overflow-auto whitespace-pre-wrap rounded-xl bg-elev p-2.5 font-mono text-xs">
          {op.command || op.path || op.url || op.query || JSON.stringify(op, null, 2)}
        </pre>
      )}
      {op.cwd && <div className="mt-1 truncate font-mono text-[11px] text-subtle">{op.cwd}</div>}
      <div className="mt-2.5 flex gap-2">
        <button onClick={() => useStore.getState().answerApproval(sid, a, true)} className="rounded-xl bg-accent px-3.5 py-1.5 font-medium text-accent-fg">{t("approve")}</button>
        <button onClick={() => useStore.getState().answerApproval(sid, a, false)} className="rounded-xl border border-line bg-elev px-3.5 py-1.5 hover:bg-hover">{t("deny")}</button>
      </div>
    </div>
  );
});

// Documents the run generated (make_doc), shown as clickable cards under the answer.
const docsOf = (steps) => [...new Set((steps || []).filter((s) => s.status === "done" && s.data?.tool === "make_doc" && s.data.path)
  .map((s) => s.data.path))];

// Read an answer aloud (browser speech synthesis); a second click stops it.
function SpeakButton({ m }) {
  const t = useT();
  const [on, setOn] = useState(speakingId() === m.id);
  useEffect(() => onSpeech((id) => setOn(id === m.id)), [m.id]);
  if (!speechSupported() || !m.content) return null;
  const prefs = useStore.getState().prefs;
  return (
    <button onClick={() => (on ? stopSpeech() : speak(m.id, m.content, speechOpts(prefs)))}
      title={t(on ? "voice_stop" : "voice_read")}
      className={`mt-1 flex items-center gap-1 rounded-lg px-1.5 py-1 text-xs hover:bg-hover ${on ? "text-accent" : "text-subtle"}`}>
      {on ? <Square size={12} fill="currentColor" /> : <Volume2 size={14} />}
    </button>
  );
}

const Message = memo(function Message({ m }) {
  const t = useT();
  if (m.role === "user") {
    const atts = m.meta?.attachments || [];
    return (
      <div className="flex flex-col items-end gap-1.5">
        {atts.length > 0 && <div className="flex max-w-[90%] flex-wrap justify-end gap-1.5">{atts.map((a, i) => <FileChip key={i} file={a} compact />)}</div>}
        <div className="max-w-[90%] rounded-3xl rounded-br-lg bg-hover px-4 py-2.5 sm:max-w-[80%]">
          <Markdown text={m.content} mentions />
        </div>
      </div>
    );
  }
  return (
    <div>
      <ActivityTrace steps={m.meta?.steps} timing={m.meta?.timing} />
      <TaskBoard steps={m.meta?.steps} />
      {m.content && <Markdown text={m.content} />}
      <SpeakButton m={m} />
      <TodoList todos={m.meta?.todos} />
      {docsOf(m.meta?.steps).length > 0 && <div className="mt-3 flex flex-wrap gap-2">{docsOf(m.meta.steps).map((p) => <DocCard key={p} path={p} />)}</div>}
      <OutputGallery paths={withoutShots(m.meta?.outputs, m.meta?.steps)} />
      {m.meta?.changes?.files?.length > 0 && <ChangesCard changes={m.meta.changes} />}
      {m.meta?.error && <ErrorNote code={m.meta.errorCode} message={m.meta.error} />}
      {m.meta?.status === "cancelled" && <div className="text-[13px] text-subtle">{t("cancelled")}</div>}
    </div>
  );
});

// What the model writes before a tool call ("I'll check the sources") is a step note: it is shown as a live note
// line in the trace from the start, so it does not appear as the answer and then vanish into the trace. Text that
// grows long or gets structure (paragraphs, lists, code) is the answer and streams as Markdown.
const isAnswer = (t) => t.length > 320 || /\n\s*\n|```|^\s*([-*|#>]|\d+\.)\s/m.test(t);

// Text the model writes while it works with tools is a work note, not the reply: it streams small and muted
// (the latest lines only) and then moves into the step list; the real reply is shown when the task ends.
function LiveNote({ text }) {
  const long = text.length > 420 || text.split("\n").length > 7;
  return (
    <div className="fade-in -mt-0.5 mb-1 ml-[7px] flex gap-2 border-l border-line py-1 pl-[17px]">
      <MessageSquareText size={13} className="mt-[5px] shrink-0 text-subtle" />
      <div className={`note-md min-w-0 flex-1 ${long ? "note-tail" : ""}`}><Markdown text={text.trim()} /></div>
    </div>
  );
}

// Only this component re-renders while a run streams.
function LiveRun({ sid }) {
  const run = useStore((s) => s.runs[sid]);
  if (!run) return null;
  const running = run.steps.some((x) => x.status === "running");
  // Tools are in use: streamed text is a work note (thinking, retries and compression are not tool work).
  const working = run.steps.some((x) => !["thinking", "retry", "fallback", "compress"].includes(x.kind));
  return (
    <div>
      <ActivityTrace steps={run.steps} live />
      <TaskBoard steps={run.steps} />
      {run.approvals.map((a) => <Approval key={a.approval_id} sid={sid} a={a} />)}
      {run.text && (!working && isAnswer(run.text) ? <Markdown text={run.text} /> : <LiveNote text={run.text} />)}
      <TodoList todos={run.todos} live />
      {/* Always show what is happening while the run is active (no silent "waiting" phase). */}
      {!run.error && !running && run.approvals.length === 0 && <Thinking role={run.role} compact={!!run.text} />}
      {run.error && <ErrorNote code={run.errorCode} message={run.error} />}
    </div>
  );
}

function ScopeTabs() {
  const t = useT();
  const project = useStore((s) => s.projects.find((p) => p.id === s.projectId));
  const scope = useStore((s) => s.scope);
  const tab = (active) => `flex items-center gap-1.5 rounded-full border px-3.5 py-1.5 text-[13px] transition ${active ? "border-line bg-elev font-medium shadow-sm" : "border-transparent text-muted hover:bg-hover"}`;
  return (
    <div className="flex flex-wrap justify-center gap-1.5 rounded-full bg-panel p-1">
      {project && (
        <button onClick={() => { useStore.setState({ scope: "project" }); useStore.getState().loadContext(); }} className={tab(scope === "project")}>
          <Folder size={14} /> {project.name}
        </button>
      )}
      <button onClick={() => useStore.setState({ scope: "computer" })} className={tab(scope === "computer" || !project)}>
        <Laptop size={14} /> {t("this_computer")}
      </button>
    </div>
  );
}

// Scrolled up in a long chat: a round button above the message box brings the latest message back.
// While a task runs it shows the working dots, and the arrow on hover (always on touch screens).
function JumpButton({ live, onClick }) {
  const t = useT();
  return (
    <button onClick={onClick} title={t("jump_latest")} aria-label={t("jump_latest")}
      className="jump-in group absolute -top-12 left-1/2 z-30 grid h-9 w-9 -translate-x-1/2 place-items-center rounded-full border border-line bg-elev text-muted shadow-[0_4px_16px_rgb(0_0_0/0.12)] transition hover:border-accent/50 hover:text-fg">
      {live ? (
        <>
          <span className="flex gap-[3px] group-hover:hidden [@media(hover:none)]:hidden">
            {[0, 1, 2].map((i) => <span key={i} className="pulse-dot h-[5px] w-[5px] rounded-full bg-accent" style={{ animationDelay: `${i * 0.18}s` }} />)}
          </span>
          <ArrowDown size={16} className="hidden group-hover:block [@media(hover:none)]:block" />
        </>
      ) : <ArrowDown size={16} />}
    </button>
  );
}

// Reads a dropped folder entry recursively; each file keeps its path inside the folder as relPath.
const readTree = async (entry) => {
  if (entry.isFile) {
    const f = await new Promise((res, rej) => entry.file(res, rej));
    f.relPath = entry.fullPath.replace(/^\//, "");
    return [f];
  }
  const reader = entry.createReader();
  const out = [];
  for (;;) {
    const batch = await new Promise((res, rej) => reader.readEntries(res, rej));
    if (!batch.length) return out;
    for (const e of batch) out.push(...await readTree(e));
  }
};

// Drop zone over the whole chat: a full overlay while files are dragged in, then files and folders go to the composer.
function useDropZone() {
  const [over, setOver] = useState(false);
  const depth = useRef(0);
  const hasFiles = (e) => [...(e.dataTransfer?.types || [])].includes("Files") && !e.target.closest?.("[role=dialog]");
  const handlers = {
    onDragEnter: (e) => { if (!hasFiles(e)) return; e.preventDefault(); depth.current += 1; setOver(true); },
    onDragOver: (e) => { if (!hasFiles(e)) return; e.preventDefault(); e.dataTransfer.dropEffect = "copy"; },
    onDragLeave: (e) => { if (!hasFiles(e)) return; depth.current = Math.max(0, depth.current - 1); if (!depth.current) setOver(false); },
    onDrop: async (e) => {
      if (!hasFiles(e)) return;
      e.preventDefault();
      depth.current = 0;
      setOver(false);
      const entries = [...e.dataTransfer.items].map((i) => i.webkitGetAsEntry?.()).filter(Boolean);
      const plain = [...e.dataTransfer.files];
      const files = [], folders = [];
      if (entries.length === plain.length) {
        for (const [i, en] of entries.entries()) {
          if (en.isDirectory) folders.push(await readTree(en));
          else files.push(plain[i]);
        }
      } else files.push(...plain);
      dispatchEvent(new CustomEvent("aiiq:drop", { detail: { files, folders: folders.filter((f) => f.length) } }));
    },
  };
  return [over, handlers];
}

function DropOverlay() {
  const t = useT();
  return (
    <div className="drop-in pointer-events-none absolute inset-0 z-40 grid place-items-center p-3 backdrop-blur-md sm:p-5"
      style={{ background: "color-mix(in srgb, var(--bg) 90%, transparent)" }}>
      <div className="flex h-full w-full flex-col items-center justify-center gap-4 rounded-[28px] border-2 border-dashed border-accent px-6 text-center shadow-[inset_0_0_80px_color-mix(in_srgb,var(--accent)_10%,transparent)]"
        style={{ background: "color-mix(in srgb, var(--accent) 7%, var(--elev))" }}>
        <div className="grid h-16 w-16 place-items-center rounded-2xl bg-accent text-accent-fg shadow-lg shadow-accent/25">
          <FileUp size={30} strokeWidth={1.8} />
        </div>
        <div className="space-y-1.5">
          <div className="text-[19px] font-semibold tracking-tight">{t("drop_title")}</div>
          <div className="max-w-sm text-[13px] leading-relaxed text-muted">{t("drop_sub")}</div>
        </div>
      </div>
    </div>
  );
}

export default function ChatView() {
  const t = useT();
  const sessionId = useStore((s) => s.sessionId);
  const messages = useStore((s) => s.messages);
  const hasRun = useStore((s) => !!s.runs[s.sessionId]);
  const project = useStore((s) => s.projects.find((p) => p.id === s.projectId));
  const scope = useStore((s) => s.scope);
  const scroller = useRef(null);
  const stick = useRef(true);
  const empty = messages.length === 0 && !hasRun;

  // Follow the stream only while the user is at the bottom.
  const [away, setAway] = useState(false); // scrolled up from the bottom: show the jump button
  const onScroll = () => {
    const el = scroller.current;
    stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
    setAway(!stick.current && el.scrollHeight - el.scrollTop - el.clientHeight > 120);
  };
  const toBottom = () => {
    const el = scroller.current;
    stick.current = true;
    el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  };
  useLayoutEffect(() => { stick.current = true; setAway(false); }, [sessionId]);
  useEffect(() => {
    const el = scroller.current;
    if (!el) return;
    const ro = new ResizeObserver(() => { if (stick.current) el.scrollTop = el.scrollHeight; });
    ro.observe(el.firstElementChild);
    return () => ro.disconnect();
  }, [empty]);

  const [dropping, drop] = useDropZone();

  return (
    <div className="relative flex min-h-0 flex-1 flex-col" {...drop}>
      {dropping && <DropOverlay />}
      <div ref={scroller} onScroll={onScroll} className="min-h-0 flex-1 overflow-y-auto">
        {empty ? (
          <div className="flex h-full flex-col items-center justify-center gap-5 px-4 pb-8 text-center">
            <Logo size={52} />
            <div className="-mb-2 text-[13px] font-medium text-muted">{t("welcome_hi")}</div>
            <h1 className="max-w-xl text-[22px] font-semibold tracking-tight sm:text-[28px]">
              {project && scope === "project" ? t("what_work", { project: project.name }) : t("what_work_pc")}
            </h1>
            <ScopeTabs />
            <p className="max-w-md text-[13px] leading-relaxed text-subtle">{t("welcome_sub")}</p>
          </div>
        ) : (
          <div className="mx-auto w-full max-w-3xl space-y-7 px-4 py-6 sm:px-6">
            {messages.map((m) => <Message key={m.id} m={m} />)}
            {hasRun && <LiveRun sid={sessionId} />}
          </div>
        )}
      </div>
      <div className="relative">
        {away && !empty && <JumpButton live={hasRun} onClick={toBottom} />}
        <Composer />
      </div>
    </div>
  );
}
