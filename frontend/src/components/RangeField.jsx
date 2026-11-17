import { useEffect, useState } from "react";
import { RotateCcw } from "lucide-react";
import { useT } from "../lib/store";

// A slider with an editable number next to it. Every numeric setting uses it.
//  - value null/undefined + auto: the setting is "automatic" (the slider is dimmed at `autoAt`, the box shows the label)
//  - log: logarithmic slider for wide ranges (tokens, request limits)
//  - zeroLabel: a value of 0 means something special (∞, off) and is shown as that label
// The value is saved when the slider is released, on Enter or when the box loses focus.
const POS = 1000;

export default function RangeField({ value, onCommit, min, max, step = 1, log, auto, autoAt, zeroLabel, format, unit = "", className = "" }) {
  const t = useT();
  const isAuto = value == null || value === "";
  const [v, setV] = useState(isAuto ? null : Number(value));
  const [text, setText] = useState(null); // while typing in the box
  useEffect(() => { setV(isAuto ? null : Number(value)); setText(null); }, [value]);

  const clamp = (n) => Math.min(max, Math.max(min, n));
  const snap = (n) => {
    const s = step < 1 ? Math.round(n / step) * step : log ? niceLog(n) : Math.round(n / step) * step;
    return clamp(+s.toFixed(step < 1 ? String(step).split(".")[1]?.length || 2 : 0));
  };
  const lo = log ? Math.log(Math.max(1, min)) : min;
  const hi = log ? Math.log(max) : max;
  const toPos = (n) => (log ? ((Math.log(Math.max(1, n)) - lo) / (hi - lo)) * POS : n);
  const fromPos = (p) => snap(log ? Math.exp(lo + (p / POS) * (hi - lo)) : p);
  const shown = v ?? (autoAt ?? min);
  const pct = Math.max(0, Math.min(100, ((toPos(shown) - (log ? 0 : min)) / ((log ? POS : max) - (log ? 0 : min))) * 100));

  const commit = (n) => {
    const next = n == null ? null : snap(n);
    if ((next ?? null) === (isAuto ? null : Number(value))) return;
    onCommit(next);
  };
  const label = (n) => (n === 0 && zeroLabel ? zeroLabel : format ? format(n) : String(n));
  const commitText = () => {
    if (text == null) return;
    const raw = text.replace(",", ".").trim();
    setText(null);
    if (raw === "" && auto) { setV(null); return commit(null); }
    const n = parseFloat(raw.replace(/[kK]$/, "e3").replace(/[mM]$/, "e6"));
    if (Number.isNaN(n)) return;
    setV(snap(n)); commit(n);
  };

  return (
    <div className={`flex items-center gap-2.5 ${className}`}>
      <input type="range" className={`slider range-fill min-w-0 flex-1 ${v == null ? "opacity-40" : ""}`}
        style={{ "--pct": `${pct}%` }} min={log ? 0 : min} max={log ? POS : max} step={log ? 1 : step} value={toPos(shown)}
        onChange={(e) => setV(fromPos(+e.target.value))}
        onMouseUp={() => commit(v)} onTouchEnd={() => commit(v)} onKeyUp={() => commit(v)} />
      <div className="relative">
        <input value={text ?? (v == null ? "" : label(v))} placeholder={v == null ? auto : undefined}
          inputMode="decimal" onFocus={(e) => { setText(v == null ? "" : String(v)); requestAnimationFrame(() => e.target.select()); }}
          onChange={(e) => setText(e.target.value)} onBlur={commitText} onKeyDown={(e) => e.key === "Enter" && e.currentTarget.blur()}
          className={`h-8 w-[84px] rounded-lg border border-line bg-bg px-2 text-right font-mono text-[12.5px] tabular-nums outline-none transition focus:border-accent ${unit ? "pr-6" : ""} ${v == null ? "placeholder:text-muted" : ""}`} />
        {unit && v != null && text == null && <span className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 text-[11px] text-subtle">{unit}</span>}
      </div>
      {auto && (
        <button type="button" title={t("prof_auto")} disabled={v == null} onClick={() => { setV(null); commit(null); }}
          className="grid h-8 w-8 shrink-0 place-items-center rounded-lg text-subtle transition hover:bg-hover hover:text-fg disabled:opacity-30">
          <RotateCcw size={13} />
        </button>
      )}
    </div>
  );
}

// 1, 2, 2.5, 5 steps: a log slider lands on round numbers (4k, 8k, 32k, 128k...)
function niceLog(n) {
  if (n <= 10) return Math.round(n);
  const p = 10 ** Math.floor(Math.log10(n));
  const m = n / p;
  const nice = [1, 1.25, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10].reduce((a, b) => (Math.abs(b - m) < Math.abs(a - m) ? b : a));
  return Math.round(nice * p);
}
