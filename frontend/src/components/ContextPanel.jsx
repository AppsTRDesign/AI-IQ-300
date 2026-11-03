import { memo, useEffect, useMemo, useState } from "react";
import { Archive, ChevronRight, Code2, Loader2, Square, SquareTerminal } from "lucide-react";
import { useStore, useT } from "../lib/store";
import { api } from "../lib/api";
import { formatTokens } from "../lib/fileTypes";
import { Popover } from "./ui";

// Category -> color; keys come from backend orchestrator.context_breakdown.
const CATS = [
  ["messages", "#3b82f6"], ["tool_io", "#f97316"], ["tools", "#14b8a6"], ["system", "#71717a"], ["skills", "#8b5cf6"],
  ["summary", "#ec4899"], ["attachments", "#84cc16"], ["project", "#06b6d4"], ["state", "#eab308"], ["plan", "#6366f1"],
];

const fmtPct = (n) => `%${n.toFixed(1)}`;
const elapsed = (t, start) => {
  const s = Math.max(0, Math.floor(Date.now() / 1000 - start));
  const [h, m, sec] = [t("unit_h"), t("unit_m"), t("unit_s")];
  return s >= 3600 ? `${Math.floor(s / 3600)}${h} ${Math.floor((s % 3600) / 60)}${m}` : s >= 60 ? `${Math.floor(s / 60)}${m} ${s % 60}${sec}` : `${s}${sec}`;
};

function Section({ title, count, open, onToggle, children }) {
  return (
    <div className="border-t border-line pt-2.5">
      <button onClick={onToggle} className="flex w-full items-center gap-1.5 rounded-lg px-1 py-1 text-[13px] font-medium hover:bg-hover">
        <ChevronRight size={14} className={`text-subtle transition ${open ? "rotate-90" : ""}`} />
        <span className="flex-1 text-left">{title}</span>
        {count != null && <span className="text-xs text-subtle">{count}</span>}
      </button>
      {open && <div className="fade-in mt-1">{children}</div>}
    </div>
  );
}

function ContextPanel() {
  const t = useT();
  const ctx = useStore((s) => s.context);
  const sid = useStore((s) => s.sessionId);
  const processes = useStore((s) => s.processes);
  const compressing = useStore((s) => s.compressing);
  const [open, setOpen] = useState(false);
  const [val, setVal] = useState(null);
  const [sec, setSec] = useState({ outputs: true, tasks: true, size: false, done: false });
  const [more, setMore] = useState(false);
  const [, tick] = useState(0);
  const tasks = useMemo(() => Object.values(processes).filter((p) => sid && String(p.owner || "").startsWith(`${sid}:`)), [processes, sid]);
  const running = tasks.filter((p) => p.state === "running");
  const finished = tasks.filter((p) => p.state !== "running");
  useEffect(() => {
    if (!open || !running.length) return;
    const i = setInterval(() => tick((n) => n + 1), 1000);
    return () => clearInterval(i);
  }, [open, running.length]);
  useEffect(() => { if (open) useStore.getState().loadContext(); }, [open]);
  if (!ctx) return null;

  const used = ctx.used || 0;
  const cap = ctx.current || 1;
  const pct = Math.min(100, (used / cap) * 100);
  const color = pct >= ctx.threshold ? "var(--danger)" : pct >= ctx.threshold * 0.75 ? "var(--warn)" : "var(--accent)";
  const R = 7, C = 2 * Math.PI * R;
  const stats = ctx.stats || {};
  const rows = CATS.filter(([k]) => stats[k] > 0).map(([k, c]) => ({ k, c, v: stats[k] }));
  const buffer = Math.round(cap * (100 - ctx.threshold) / 100);
  const free = Math.max(0, cap - used - buffer);
  const toggle = (k) => setSec((x) => ({ ...x, [k]: !x[k] }));
  const commit = async () => {
    if (val == null) return;
    await useStore.getState().setModelContext(ctx.model, val);
    setVal(null);
  };
  const outputs = ctx.outputs || [];

  return (
    <div className="relative">
      <button onClick={() => setOpen(!open)} title={t("context")} className="grid h-8 w-8 place-items-center rounded-full hover:bg-hover">
        <svg width="18" height="18" viewBox="0 0 18 18" className="-rotate-90">
          <circle cx="9" cy="9" r={R} fill="none" stroke="var(--line)" strokeWidth="2.4" />
          {pct > 0 && <circle cx="9" cy="9" r={R} fill="none" stroke={color} strokeWidth="2.4" strokeLinecap="round"
            strokeDasharray={C} strokeDashoffset={C * (1 - Math.max(pct, 3) / 100)} style={{ transition: "stroke-dashoffset .4s" }} />}
        </svg>
      </button>
      {open && (
        <Popover onClose={() => setOpen(false)} className="bottom-full right-0 mb-2 max-h-[min(640px,75vh)] w-[min(360px,calc(100vw-20px))] overflow-y-auto p-3.5">
          <div className="text-[13px] font-semibold">{t("context")}</div>
          <div className="mt-2 flex items-baseline justify-between text-[13px]">
            <span className="font-medium">{t("pct_used", { n: pct.toFixed(0) })}</span>
            <span className="font-mono text-xs text-muted">{formatTokens(used)} / {formatTokens(cap)}</span>
          </div>
          <div className="mt-1.5 flex h-2 overflow-hidden rounded-full bg-hover">
            {rows.length ? rows.map((r) => <div key={r.k} style={{ width: `${(r.v / cap) * 100}%`, background: r.c }} />)
              : <div style={{ width: `${pct}%`, background: color }} />}
            <div className="ml-auto h-full" style={{ width: `${(buffer / cap) * 100}%`, background: "var(--active)" }} />
          </div>

          <div className="mt-3 space-y-1">
            {rows.map((r) => (
              <div key={r.k} className="flex items-center gap-2 text-[12.5px]">
                <span className="h-2.5 w-2.5 shrink-0 rounded-[3px]" style={{ background: r.c }} />
                <span className="flex-1 text-muted">{t(`ctx_${r.k}`)}</span>
                <span className="w-14 text-right font-mono text-xs">{formatTokens(r.v)}</span>
                <span className="w-12 text-right font-mono text-xs text-subtle">{fmtPct((r.v / cap) * 100)}</span>
              </div>
            ))}
            {!rows.length && <div className="text-xs text-subtle">{t("ctx_no_stats")}</div>}
            <div className="flex items-center gap-2 text-[12.5px]">
              <span className="h-2.5 w-2.5 shrink-0 rounded-[3px] bg-active" />
              <span className="flex-1 text-muted">{t("ctx_buffer", { n: ctx.threshold })}</span>
              <span className="w-14 text-right font-mono text-xs">{formatTokens(buffer)}</span>
              <span className="w-12 text-right font-mono text-xs text-subtle">{fmtPct((buffer / cap) * 100)}</span>
            </div>
            <div className="flex items-center gap-2 text-[12.5px]">
              <span className="h-2.5 w-2.5 shrink-0 rounded-[3px] border border-line bg-bg" />
              <span className="flex-1 text-muted">{t("ctx_free")}</span>
              <span className="w-14 text-right font-mono text-xs">{formatTokens(free)}</span>
              <span className="w-12 text-right font-mono text-xs text-subtle">{fmtPct((free / cap) * 100)}</span>
            </div>
          </div>
          <div className="mt-2 text-[11px] text-subtle">
            {t("model_max")}: {formatTokens(ctx.max)}{ctx.summarized && <span className="ml-2 text-accent">· {t("summarized")}</span>}
          </div>
          <button disabled={compressing} onClick={() => useStore.getState().compressNow()}
            className="mt-3 flex w-full items-center justify-center gap-1.5 rounded-xl border border-line py-1.5 text-[13px] font-medium hover:bg-hover disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:bg-transparent">
            {compressing ? <Loader2 size={14} className="animate-spin" /> : <Archive size={14} />} {t(compressing ? "compressing" : "compress_now")}
          </button>

          {ctx.adjustable && (
            <div className="mt-3">
              <Section title={t("context_size")} count={formatTokens(val ?? ctx.current)} open={sec.size} onToggle={() => toggle("size")}>
                <input type="range" className="slider w-full" min={2048} max={ctx.max} step={1024} value={val ?? ctx.current}
                  onChange={(e) => setVal(+e.target.value)} onMouseUp={commit} onTouchEnd={commit} onKeyUp={commit} />
                <div className="mt-1 flex justify-between text-[10px] text-subtle"><span>2K</span><span>{formatTokens(ctx.max)}</span></div>
                <p className="mt-1.5 text-[11px] leading-snug text-subtle">{t("context_size_hint")}</p>
              </Section>
            </div>
          )}

          <div className="mt-3">
            <Section title={t("outputs")} count={outputs.length} open={sec.outputs} onToggle={() => toggle("outputs")}>
              {outputs.length === 0 && <div className="px-2 py-1 text-xs text-subtle">{t("no_outputs")}</div>}
              {outputs.slice(0, more ? 100 : 5).map((o) => (
                <button key={o.path} onClick={() => { setOpen(false); useStore.getState().openFile(o.path); }}
                  className="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-[13px] hover:bg-hover" title={o.path}>
                  <Code2 size={14} className="shrink-0 text-subtle" /><span className="truncate">{o.path.split(/[\\/]/).pop()}</span>
                </button>
              ))}
              {outputs.length > 5 && (
                <button onClick={() => setMore(!more)} className="px-2 py-1 text-xs text-muted hover:text-fg">{more ? t("show_less") : t("show_more")}</button>
              )}
            </Section>
          </div>
          <div className="mt-2">
            <Section title={t("bg_tasks")} count={running.length || null} open={sec.tasks} onToggle={() => toggle("tasks")}>
              {running.length === 0 && <div className="px-2 py-1 text-xs text-subtle">{t("no_running_tasks")}</div>}
              {running.map((p) => (
                <div key={p.id} className="flex items-center gap-2 rounded-lg px-2 py-1.5 text-[13px]">
                  <Loader2 size={13} className="shrink-0 animate-spin text-accent" />
                  <span className="min-w-0 flex-1 truncate font-mono text-xs">{(p.argv || []).slice(-1)[0]?.split(/[\\/]/).pop() || p.id}</span>
                  {p.started && <span className="text-[11px] text-subtle">{elapsed(t, p.started)}</span>}
                  <button title={t("stop")} onClick={() => api.post(`/api/processes/${p.id}/stop`)} className="rounded p-0.5 text-danger hover:bg-hover"><Square size={11} fill="currentColor" /></button>
                </div>
              ))}
              {finished.length > 0 && (
                <>
                  <button onClick={() => toggle("done")} className="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-[13px] text-muted hover:bg-hover">
                    <SquareTerminal size={14} /> {t("finished_n", { n: finished.length })}
                    <ChevronRight size={13} className={`ml-auto transition ${sec.done ? "rotate-90" : ""}`} />
                  </button>
                  {sec.done && finished.slice(-20).reverse().map((p) => (
                    <div key={p.id} className="flex items-center gap-2 px-2 py-1 pl-8 text-xs text-muted">
                      <span className={`h-1.5 w-1.5 rounded-full ${p.exit_code === 0 ? "bg-ok" : "bg-danger"}`} />
                      <span className="min-w-0 flex-1 truncate font-mono">{(p.argv || []).slice(-1)[0]?.split(/[\\/]/).pop() || p.id}</span>
                      <span>{p.state} {p.exit_code != null ? `(${p.exit_code})` : ""}</span>
                    </div>
                  ))}
                </>
              )}
            </Section>
          </div>
        </Popover>
      )}
    </div>
  );
}

export default memo(ContextPanel);
