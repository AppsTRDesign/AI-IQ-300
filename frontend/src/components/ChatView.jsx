import { memo, useEffect, useLayoutEffect, useRef } from "react";
import { Folder, Laptop, ShieldAlert } from "lucide-react";
import { useStore, useT } from "../lib/store";
import Markdown from "./Markdown";
import ActivityTrace from "./ActivityTrace";
import Composer from "./Composer";
import { Thinking, Logo } from "./Brand";
import { FileChip } from "./ui";
import { ErrorNote } from "./Feedback";
import TodoList from "./TodoList";
import { DocCard } from "./DocPreview";

const Approval = memo(function Approval({ sid, a }) {
  const t = useT();
  const op = a.op || {};
  return (
    <div className="fade-in my-2 rounded-2xl border border-warn/40 bg-warn/10 p-3 text-[13px]">
      <div className="mb-1.5 flex items-center gap-1.5 font-semibold text-warn"><ShieldAlert size={15} /> {t("approval_needed")} · {a.category}</div>
      <pre className="max-h-48 overflow-auto whitespace-pre-wrap rounded-xl bg-elev p-2.5 font-mono text-xs">
        {op.command || op.path || op.url || op.query || JSON.stringify(op, null, 2)}
      </pre>
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
      <ActivityTrace steps={m.meta?.steps} />
      {m.content && <Markdown text={m.content} />}
      <TodoList todos={m.meta?.todos} />
      {docsOf(m.meta?.steps).length > 0 && <div className="mt-3 flex flex-wrap gap-2">{docsOf(m.meta.steps).map((p) => <DocCard key={p} path={p} />)}</div>}
      {m.meta?.error && <ErrorNote code={m.meta.errorCode} message={m.meta.error} />}
      {m.meta?.status === "cancelled" && <div className="text-[13px] text-subtle">{t("cancelled")}</div>}
    </div>
  );
});

// Only this component re-renders while a run streams.
function LiveRun({ sid }) {
  const run = useStore((s) => s.runs[sid]);
  if (!run) return null;
  const running = run.steps.some((x) => x.status === "running");
  return (
    <div>
      <ActivityTrace steps={run.steps} live />
      {run.approvals.map((a) => <Approval key={a.approval_id} sid={sid} a={a} />)}
      {run.text && <Markdown text={run.text} />}
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
  const onScroll = () => {
    const el = scroller.current;
    stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
  };
  useLayoutEffect(() => { stick.current = true; }, [sessionId]);
  useEffect(() => {
    const el = scroller.current;
    if (!el) return;
    const ro = new ResizeObserver(() => { if (stick.current) el.scrollTop = el.scrollHeight; });
    ro.observe(el.firstElementChild);
    return () => ro.disconnect();
  }, [empty]);

  return (
    <div className="flex min-h-0 flex-1 flex-col">
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
      <Composer />
    </div>
  );
}
