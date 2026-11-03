import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { X } from "lucide-react";
import { fileType, formatSize } from "../lib/fileTypes";

// Small shared UI primitives.

export function useOutside(ref, onClose, active = true, anchor = null) {
  useEffect(() => {
    if (!active) return;
    // A press on the anchor (the button that opened the popover) is left to the button's own toggle,
    // so clicking it again closes the popover instead of closing and reopening it.
    const h = (e) => ref.current && !ref.current.contains(e.target) && !anchor?.()?.contains(e.target) && onClose();
    const k = (e) => e.key === "Escape" && onClose();
    document.addEventListener("mousedown", h);
    document.addEventListener("keydown", k);
    return () => { document.removeEventListener("mousedown", h); document.removeEventListener("keydown", k); };
  }, [active, onClose]);
}

export function Popover({ children, onClose, className = "" }) {
  const ref = useRef(null);
  useOutside(ref, onClose, true, () => ref.current?.parentElement);
  return (
    <div ref={ref} className={`fade-in absolute z-40 rounded-2xl border border-line bg-elev p-1.5 shadow-xl shadow-black/10 ${className}`}>
      {children}
    </div>
  );
}

export function MenuItem({ icon: Icon, label, desc, onClick, right, danger, active, shortcut }) {
  return (
    <button onClick={onClick}
      className={`flex w-full items-start gap-2.5 rounded-xl px-2.5 py-2 text-left text-[13px] hover:bg-hover ${danger ? "text-danger" : ""} ${active ? "bg-hover" : ""}`}>
      {Icon && <Icon size={15} className={`mt-0.5 shrink-0 ${danger ? "" : "text-muted"}`} />}
      <span className="min-w-0 flex-1">
        <span className="block truncate">{label}</span>
        {desc && <span className="mt-0.5 block text-xs leading-snug text-muted">{desc}</span>}
      </span>
      {right}
      {shortcut && <span className="mt-0.5 shrink-0 text-xs text-subtle">{shortcut}</span>}
    </button>
  );
}

export const MenuSep = () => <div className="mx-2 my-1 border-t border-line" />;

// Right-click / "..." menu positioned at the cursor, clamped to the viewport.
export function ContextMenu({ x, y, onClose, children }) {
  const ref = useRef(null);
  const [pos, setPos] = useState({ left: x, top: y });
  useOutside(ref, onClose);
  useLayoutEffect(() => {
    const r = ref.current.getBoundingClientRect();
    setPos({ left: Math.min(x, innerWidth - r.width - 8), top: Math.min(y, innerHeight - r.height - 8) });
  }, [x, y]);
  return (
    <div ref={ref} style={pos} onClick={onClose}
      className="fade-in fixed z-50 w-56 rounded-2xl border border-line bg-elev p-1.5 shadow-xl shadow-black/15">
      {children}
    </div>
  );
}

export function Modal({ title, onClose, children, footer, width = "max-w-lg" }) {
  // Escape closes the dialog, unless an inner control (e.g. an open Select) already handled it.
  const close = useRef(onClose);
  close.current = onClose;
  useEffect(() => {
    const k = (e) => { if (e.key === "Escape" && !e.defaultPrevented) close.current(); };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, []);
  return (
    <div role="dialog" aria-modal="true" aria-label={typeof title === "string" ? title : undefined}
      className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 p-0 backdrop-blur-[2px] sm:items-center sm:p-4"
      onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className={`fade-in flex max-h-[92vh] w-full ${width} flex-col overflow-hidden rounded-t-3xl border border-line bg-elev shadow-2xl sm:rounded-3xl`}>
        <div className="flex items-center justify-between px-5 pb-2 pt-4">
          <h2 className="text-[15px] font-semibold">{title}</h2>
          <button onClick={onClose} className="rounded-lg p-1 text-muted hover:bg-hover"><X size={18} /></button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto px-5 pb-4">{children}</div>
        {footer && <div className="flex justify-end gap-2 border-t border-line px-5 py-3">{footer}</div>}
      </div>
    </div>
  );
}

export function Button({ variant = "default", className = "", ...p }) {
  const v = {
    primary: "bg-accent text-accent-fg hover:opacity-90 disabled:opacity-40",
    default: "border border-line bg-elev hover:bg-hover disabled:opacity-50",
    ghost: "hover:bg-hover",
    danger: "border border-line text-danger hover:bg-hover",
  }[variant];
  return <button {...p} className={`inline-flex items-center justify-center gap-1.5 rounded-xl px-3 py-1.5 text-[13px] font-medium transition ${v} ${className}`} />;
}

export function Toggle({ checked, onChange, disabled }) {
  return (
    <button type="button" role="switch" aria-checked={checked} disabled={disabled} onClick={() => onChange(!checked)}
      className={`relative h-5 w-9 shrink-0 rounded-full transition ${checked ? "bg-accent" : "bg-active"} disabled:opacity-50`}>
      <span className={`absolute top-0.5 h-4 w-4 rounded-full bg-white shadow transition-all ${checked ? "left-[18px]" : "left-0.5"}`} />
    </button>
  );
}

export const inputCls = "w-full rounded-xl border border-line bg-bg px-3 py-2 text-[13px] outline-none transition placeholder:text-subtle focus:border-accent focus:ring-2 focus:ring-accent/20";

export function FileChip({ file, onRemove, compact }) {
  const ft = fileType(file.name);
  const Icon = ft.icon;
  return (
    <div className={`group relative flex shrink-0 items-center gap-2 rounded-xl border border-line bg-elev ${compact ? "px-2 py-1" : "w-44 p-2"}`}>
      {file.kind === "image" && file.b64 && !compact
        ? <img src={`data:image/png;base64,${file.b64}`} className="h-9 w-9 rounded-lg object-cover" alt="" />
        : (
          <div className={`grid shrink-0 place-items-center rounded-lg text-white ${compact ? "h-6 w-6" : "h-9 w-9"}`} style={{ background: ft.color }}>
            <Icon size={compact ? 13 : 17} />
          </div>
        )}
      <div className="min-w-0">
        <div className="truncate text-xs font-medium">{file.name}</div>
        {!compact && <div className="text-[11px] text-subtle">{ft.label} · {formatSize(file.size)}</div>}
      </div>
      {onRemove && (
        <button onClick={onRemove} className="absolute -right-1.5 -top-1.5 hidden rounded-full bg-fg p-0.5 text-bg group-hover:block"><X size={11} /></button>
      )}
    </div>
  );
}
