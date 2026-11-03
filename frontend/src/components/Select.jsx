import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Check, ChevronDown, Search, X } from "lucide-react";
import { useT } from "../lib/store";

/**
 * Searchable, grouped, keyboard-navigable select rendered in a portal (never clipped by cards).
 * options: [{ value, label, group?, hint?, badge?, disabled? }]
 */
export default function Select({ value, onChange, options, placeholder, searchable, className = "", allowClear, renderValue, mono }) {
  const t = useT();
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [hi, setHi] = useState(0);
  const [pos, setPos] = useState(null);
  const btn = useRef(null);
  const pop = useRef(null);
  const list = useRef(null);
  const canSearch = searchable ?? options.length > 8;
  const current = options.find((o) => o.value === value);

  const filtered = useMemo(() => {
    const n = q.trim().toLowerCase();
    return n ? options.filter((o) => `${o.label} ${o.group || ""} ${o.hint || ""}`.toLowerCase().includes(n)) : options;
  }, [options, q]);

  useLayoutEffect(() => {
    if (!open || !btn.current) return;
    const place = () => {
      const r = btn.current.getBoundingClientRect();
      const h = Math.min(380, innerHeight * 0.6);
      const up = r.bottom + h + 8 > innerHeight && r.top > h;
      setPos({ left: r.left, width: Math.max(r.width, 240), top: up ? undefined : r.bottom + 6, bottom: up ? innerHeight - r.top + 6 : undefined, h });
    };
    place();
    addEventListener("resize", place);
    addEventListener("scroll", place, true);
    return () => { removeEventListener("resize", place); removeEventListener("scroll", place, true); };
  }, [open]);

  useEffect(() => {
    if (!open) return;
    setQ("");
    setHi(Math.max(0, options.findIndex((o) => o.value === value)));
    const close = (e) => !pop.current?.contains(e.target) && !btn.current?.contains(e.target) && setOpen(false);
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);
  useEffect(() => { list.current?.querySelector(`[data-i="${hi}"]`)?.scrollIntoView({ block: "nearest" }); }, [hi, open]);

  const pick = (o) => { if (o && !o.disabled) { onChange(o.value); setOpen(false); btn.current?.focus(); } };
  const onKey = (e) => {
    if (!open && ["ArrowDown", "Enter", " "].includes(e.key)) { e.preventDefault(); return setOpen(true); }
    if (!open) return;
    if (e.key === "ArrowDown") { e.preventDefault(); setHi((h) => Math.min(filtered.length - 1, h + 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setHi((h) => Math.max(0, h - 1)); }
    else if (e.key === "Enter") { e.preventDefault(); pick(filtered[hi]); }
    else if (e.key === "Escape") { e.preventDefault(); setOpen(false); }
  };

  let lastGroup = null;
  return (
    <>
      <button ref={btn} type="button" onClick={() => setOpen(!open)} onKeyDown={onKey}
        className={`flex w-full items-center gap-2 rounded-xl border bg-bg px-3 py-2 text-left text-[13px] outline-none transition ${open ? "border-accent ring-2 ring-accent/20" : "border-line hover:border-subtle"} ${className}`}>
        <span className={`min-w-0 flex-1 truncate ${current ? "" : "text-subtle"} ${mono ? "font-mono text-xs" : ""}`}>
          {current ? (renderValue ? renderValue(current) : current.label) : (value || placeholder || t("select"))}
        </span>
        {current?.badge && <span className="shrink-0 rounded-md bg-hover px-1.5 py-px text-[10px] text-muted">{current.badge}</span>}
        {allowClear && value && (
          <span role="button" onClick={(e) => { e.stopPropagation(); onChange(""); }} className="rounded p-0.5 text-subtle hover:text-fg"><X size={13} /></span>
        )}
        <ChevronDown size={15} className={`shrink-0 text-subtle transition ${open ? "rotate-180" : ""}`} />
      </button>
      {open && pos && createPortal(
        <div ref={pop} onKeyDown={onKey} style={{ left: pos.left, top: pos.top, bottom: pos.bottom, width: pos.width, maxHeight: pos.h }}
          className="fade-in fixed z-[90] flex flex-col overflow-hidden rounded-2xl border border-line bg-elev shadow-2xl shadow-black/15">
          {canSearch && (
            <div className="flex items-center gap-2 border-b border-line px-3 py-2">
              <Search size={14} className="shrink-0 text-subtle" />
              <input autoFocus value={q} onChange={(e) => { setQ(e.target.value); setHi(0); }} placeholder={t("search")}
                className="min-w-0 flex-1 bg-transparent text-[13px] outline-none placeholder:text-subtle" />
              <span className="shrink-0 text-[11px] text-subtle">{filtered.length}</span>
            </div>
          )}
          <div ref={list} className="min-h-0 flex-1 overflow-y-auto p-1.5" tabIndex={-1}>
            {filtered.length === 0 && <div className="px-3 py-6 text-center text-xs text-subtle">{t("no_results")}</div>}
            {filtered.map((o, i) => {
              const header = o.group && o.group !== lastGroup ? (lastGroup = o.group) : null;
              return (
                <div key={`${o.group || ""}:${o.value}`}>
                  {header && (
                    <div className={`mx-1 mb-1 flex items-center gap-2 rounded-lg bg-hover px-2.5 py-1.5 text-[12px] font-bold text-fg ${i > 0 ? "mt-2.5" : "mt-1"}`}>
                      <span className="h-3.5 w-1 shrink-0 rounded-full bg-accent" />{header}
                    </div>
                  )}
                  <button type="button" data-i={i} disabled={o.disabled} onMouseEnter={() => setHi(i)} onClick={() => pick(o)}
                    className={`flex w-full items-center gap-2 rounded-xl px-2.5 py-1.5 text-left text-[13px] disabled:opacity-40 ${i === hi ? "bg-hover" : ""}`}>
                    <span className="min-w-0 flex-1">
                      <span className={`block truncate ${mono ? "font-mono text-xs" : ""}`}>{o.label}</span>
                      {o.hint && <span className="block truncate text-[11px] text-subtle">{o.hint}</span>}
                    </span>
                    {o.badge && <span className="shrink-0 rounded-md bg-hover px-1.5 py-px text-[10px] text-muted">{o.badge}</span>}
                    {o.value === value && <Check size={14} className="shrink-0 text-accent" />}
                  </button>
                </div>
              );
            })}
          </div>
        </div>, document.body)}
    </>
  );
}
