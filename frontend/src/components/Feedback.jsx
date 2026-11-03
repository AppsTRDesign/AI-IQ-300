import { useEffect, useRef } from "react";
import { AlertCircle, AlertTriangle, CheckCircle2, Info, Loader2, X } from "lucide-react";
import { useStore, useT } from "../lib/store";
import { errorText } from "../lib/errors";

// System notifications: stacked toasts (bottom-right on desktop, top on mobile), never blocking.
export function Toaster() {
  const toasts = useStore((s) => s.toasts);
  const ms = useStore((s) => s.modelStatus);
  const t = useT();
  const busyId = useRef(null);
  useEffect(() => {
    const st = useStore.getState();
    if (busyId.current) { st.dismiss(busyId.current); busyId.current = null; }
    if (!ms) return;
    if (ms.state === "switching") busyId.current = st.notify(t("model_switching", { model: ms.model }), "busy");
    else if (ms.state === "ready") st.notify(ms.message ? t(`model_msg_${ms.message}`) : t("model_ready", { model: ms.model }), ms.message ? "info" : "ok");
    else if (ms.state === "error") st.notify(t("model_load_failed"), "error", ms.message);
    if (ms.state !== "switching") useStore.setState({ modelStatus: null });
  }, [ms?.state, ms?.model]);
  const ICON = { ok: CheckCircle2, error: AlertCircle, busy: Loader2, warn: AlertTriangle, info: Info };
  const COLOR = { ok: "text-ok", error: "text-danger", busy: "text-accent animate-spin", warn: "text-warn", info: "text-accent" };
  return (
    <div className="pointer-events-none fixed inset-x-0 top-3 z-[70] flex flex-col items-center gap-2 px-3 sm:inset-x-auto sm:bottom-5 sm:right-5 sm:top-auto sm:items-end">
      {toasts.map((x) => {
        const Icon = ICON[x.kind] || Info;
        return (
          <div key={x.id} className="fade-in pointer-events-auto flex w-full max-w-sm items-start gap-2.5 rounded-2xl border border-line bg-elev px-3.5 py-3 text-[13px] shadow-xl shadow-black/10">
            <Icon size={17} className={`mt-px shrink-0 ${COLOR[x.kind] || ""}`} />
            <div className="min-w-0 flex-1">
              <div className="font-medium leading-snug">{x.text}</div>
              {x.detail && <div className="mt-0.5 line-clamp-3 break-words text-xs text-muted">{x.detail}</div>}
            </div>
            <button onClick={() => useStore.getState().dismiss(x.id)} className="rounded-md p-0.5 text-subtle hover:bg-hover hover:text-fg"><X size={14} /></button>
          </div>
        );
      })}
    </div>
  );
}

// Styled confirm dialog (replaces window.confirm). Enter confirms, Escape cancels.
export function ConfirmDialog() {
  const c = useStore((s) => s.confirmState);
  const t = useT();
  const btn = useRef(null);
  useEffect(() => {
    if (!c) return;
    btn.current?.focus();
    const k = (e) => { if (e.key === "Escape") useStore.getState().closeConfirm(false); };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [c]);
  if (!c) return null;
  const close = (v) => useStore.getState().closeConfirm(v);
  return (
    <div className="fixed inset-0 z-[80] flex items-end justify-center bg-black/40 backdrop-blur-[2px] sm:items-center sm:p-4"
      onMouseDown={(e) => e.target === e.currentTarget && close(false)}>
      <div className="fade-in w-full max-w-sm rounded-t-3xl border border-line bg-elev p-5 shadow-2xl sm:rounded-3xl">
        <div className="flex items-start gap-3">
          <div className={`grid h-10 w-10 shrink-0 place-items-center rounded-2xl ${c.danger ? "bg-danger/10 text-danger" : "bg-accent-soft text-accent"}`}>
            {c.danger ? <AlertTriangle size={19} /> : <Info size={19} />}
          </div>
          <div className="min-w-0">
            <h3 className="text-[15px] font-semibold">{c.title}</h3>
            {c.message && <p className="mt-1 text-[13px] leading-relaxed text-muted">{c.message}</p>}
          </div>
        </div>
        <div className="mt-5 flex justify-end gap-2">
          <button onClick={() => close(false)} className="rounded-xl px-3.5 py-2 text-[13px] font-medium hover:bg-hover">{c.cancelLabel || t("cancel")}</button>
          <button ref={btn} onClick={() => close(true)}
            className={`rounded-xl px-3.5 py-2 text-[13px] font-medium text-white ${c.danger ? "bg-danger hover:opacity-90" : "bg-accent hover:opacity-90"}`}>
            {c.confirmLabel || t("ok")}
          </button>
        </div>
      </div>
    </div>
  );
}

// Inline error card for failed runs: translated title + provider detail.
export function ErrorNote({ code, message }) {
  const t = useT();
  const e = errorText(t, code, message);
  return (
    <div className="fade-in mt-2 flex items-start gap-2.5 rounded-2xl border border-danger/25 bg-danger/5 px-3.5 py-2.5 text-[13px]">
      <AlertCircle size={16} className="mt-px shrink-0 text-danger" />
      <div className="min-w-0">
        <div className="font-medium text-danger">{e.title}</div>
        {e.detail && <div className="mt-0.5 break-words font-mono text-[11.5px] text-muted">{e.detail}</div>}
      </div>
    </div>
  );
}
