import { useEffect, useRef, useState } from "react";
import { Square, X } from "lucide-react";
import { useStore, useT } from "../lib/store";
import { api } from "../lib/api";

const STATE_COLOR = { running: "bg-ok", cancelling: "bg-warn", exited: "bg-subtle", failed: "bg-danger",
  timed_out: "bg-danger", cancelled: "bg-subtle" };

// Live process list + streamed logs (text only) + a command line for user-run commands.
export default function ProcessPanel() {
  const processes = useStore((s) => s.processes);
  const logs = useStore((s) => s.logs);
  const { toggle, ensureSession } = useStore.getState();
  const t = useT();
  const list = Object.values(processes).reverse();
  const [sel, setSel] = useState(null);
  const [cmd, setCmd] = useState("");
  const [err, setErr] = useState("");
  const active = sel || list[0]?.id;
  const bottom = useRef(null);
  useEffect(() => { bottom.current?.scrollIntoView({ block: "end" }); }, [logs[active]?.length]);

  const run = async (e) => {
    e.preventDefault();
    if (!cmd.trim()) return;
    try {
      const p = await api.post("/api/processes", { command: cmd, session_id: await ensureSession() });
      setSel(p.id); setCmd(""); setErr("");
    } catch (x) { setErr(x.message); }
  };

  return (
    <div className="flex h-64 shrink-0 flex-col border-t border-line bg-panel md:h-72">
      <div className="flex items-center gap-2 border-b border-line px-3 py-1.5 text-xs font-medium text-muted">
        {t("processes")}
        <div className="flex-1" />
        <button onClick={() => toggle("panel")}><X size={14} /></button>
      </div>
      <div className="flex min-h-0 flex-1">
        <div className="scroll-thin w-44 shrink-0 overflow-y-auto border-r border-line md:w-60">
          {list.length === 0 && <div className="p-3 text-xs text-subtle">{t("no_processes")}</div>}
          {list.map((p) => (
            <div key={p.id} onClick={() => setSel(p.id)}
              className={`flex cursor-pointer items-center gap-2 px-2 py-1.5 text-xs ${p.id === active ? "bg-bg" : "hover:bg-hover"}`}>
              <span className={`h-2 w-2 shrink-0 rounded-full ${STATE_COLOR[p.state] || "bg-active"}`} />
              <span className="flex-1 truncate font-mono">{(p.argv || []).slice(-1)[0]?.split(/[\\/]/).pop() || p.id}</span>
              {p.state === "running" && (
                <button title={t("stop")} onClick={(e) => { e.stopPropagation(); api.post(`/api/processes/${p.id}/stop`); }}
                  className="rounded p-0.5 text-danger hover:bg-hover"><Square size={11} fill="currentColor" /></button>
              )}
            </div>
          ))}
        </div>
        <div className="flex min-w-0 flex-1 flex-col">
          <pre className="scroll-thin min-h-0 flex-1 overflow-auto bg-[#1e1e1e] p-2 font-mono text-xs leading-5 text-zinc-200">
            {(logs[active] || []).map((l, i) => (
              <div key={i} className={l.stream === "stderr" ? "text-red-300" : ""}>{l.line}</div>
            ))}
            {processes[active]?.exit_code != null && <div className="text-subtle">— exit {processes[active].exit_code} ({processes[active].state})</div>}
            <div ref={bottom} />
          </pre>
          <form onSubmit={run} className="flex border-t border-line bg-bg">
            <span className="px-2 py-1.5 font-mono text-xs text-subtle">PS&gt;</span>
            <input value={cmd} onChange={(e) => setCmd(e.target.value)} placeholder={t("terminal_ph")}
              className="flex-1 bg-transparent py-1.5 font-mono text-xs outline-none" />
            {err && <span className="px-2 py-1.5 text-xs text-danger">{err}</span>}
          </form>
        </div>
      </div>
    </div>
  );
}
