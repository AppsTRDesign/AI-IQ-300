import { useEffect, useRef, useState } from "react";
import { Circle, Eraser, Minus, Pencil, Redo2, RectangleHorizontal, Send, Trash2, Undo2, X } from "lucide-react";
import { useT } from "../lib/store";

// Sketch pad: freehand pen, shapes, eraser, colors, undo/redo. "Send" attaches the drawing as a PNG image.
const COLORS = ["#111827", "#ef4444", "#f97316", "#eab308", "#22c55e", "#3b82f6", "#8b5cf6", "#ec4899", "#ffffff"];
const SIZES = [2, 4, 8, 14];
const TOOLS = [["pen", Pencil], ["line", Minus], ["rect", RectangleHorizontal], ["ellipse", Circle], ["eraser", Eraser]];

export default function DrawingDialog({ onClose, onSend }) {
  const t = useT();
  const canvas = useRef(null);
  const wrap = useRef(null);
  const [tool, setTool] = useState("pen");
  const [color, setColor] = useState(COLORS[0]);
  const [size, setSize] = useState(4);
  const [shapes, setShapes] = useState([]); // committed strokes/shapes (vector, so resize and undo are exact)
  const [redo, setRedo] = useState([]);
  const draft = useRef(null);
  const [, force] = useState(0);

  const paint = (ctx, s) => {
    ctx.save();
    ctx.lineCap = ctx.lineJoin = "round";
    ctx.lineWidth = s.size;
    ctx.strokeStyle = s.tool === "eraser" ? "#ffffff" : s.color;
    ctx.beginPath();
    const [a, b] = [s.points[0], s.points[s.points.length - 1]];
    if (s.tool === "pen" || s.tool === "eraser") {
      s.points.forEach((p, i) => (i ? ctx.lineTo(p.x, p.y) : ctx.moveTo(p.x, p.y)));
      if (s.points.length === 1) ctx.lineTo(a.x + 0.1, a.y);
    } else if (s.tool === "line") {
      ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y);
    } else if (s.tool === "rect") {
      ctx.rect(a.x, a.y, b.x - a.x, b.y - a.y);
    } else if (s.tool === "ellipse") {
      ctx.ellipse((a.x + b.x) / 2, (a.y + b.y) / 2, Math.abs(b.x - a.x) / 2, Math.abs(b.y - a.y) / 2, 0, 0, Math.PI * 2);
    }
    ctx.stroke();
    ctx.restore();
  };

  const render = () => {
    const c = canvas.current;
    if (!c) return;
    const ctx = c.getContext("2d");
    const dpr = devicePixelRatio || 1;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, c.width, c.height);
    for (const s of shapes) paint(ctx, s);
    if (draft.current) paint(ctx, draft.current);
  };

  const renderRef = useRef(render);
  renderRef.current = render;
  useEffect(() => {
    const fit = () => {
      const c = canvas.current, r = wrap.current.getBoundingClientRect(), dpr = devicePixelRatio || 1;
      c.width = r.width * dpr; c.height = r.height * dpr;
      c.style.width = `${r.width}px`; c.style.height = `${r.height}px`;
      renderRef.current();
    };
    fit();
    const ro = new ResizeObserver(fit);
    ro.observe(wrap.current);
    return () => ro.disconnect();
  }, []);
  useEffect(() => renderRef.current(), [shapes]);

  const undo = () => { if (shapes.length) { setRedo([...redo, shapes.at(-1)]); setShapes(shapes.slice(0, -1)); } };
  const redoOne = () => { if (redo.length) { setShapes([...shapes, redo.at(-1)]); setRedo(redo.slice(0, -1)); } };
  useEffect(() => {
    const k = (e) => {
      if (e.key === "Escape") onClose();
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z") { e.preventDefault(); e.shiftKey ? redoOne() : undo(); }
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "y") { e.preventDefault(); redoOne(); }
    };
    addEventListener("keydown", k);
    return () => removeEventListener("keydown", k);
  });

  const pos = (e) => { const r = canvas.current.getBoundingClientRect(); return { x: e.clientX - r.left, y: e.clientY - r.top }; };
  const down = (e) => {
    canvas.current.setPointerCapture(e.pointerId);
    draft.current = { tool, color, size: tool === "eraser" ? size * 3 : size, points: [pos(e)] };
    force((n) => n + 1);
  };
  const move = (e) => {
    if (!draft.current) return;
    const p = pos(e);
    if (draft.current.tool === "pen" || draft.current.tool === "eraser") draft.current.points.push(p);
    else draft.current.points = [draft.current.points[0], p];
    render();
  };
  const up = () => {
    if (!draft.current) return;
    setShapes([...shapes, draft.current]);
    setRedo([]);
    draft.current = null;
  };
  const send = () => canvas.current.toBlob((blob) => {
    onSend(new File([blob], `${t("drawing").toLowerCase().replace(/\s+/g, "-")}-${Date.now()}.png`, { type: "image/png" }));
    onClose();
  }, "image/png");

  const btn = (active) => `grid h-8 w-8 place-items-center rounded-lg transition ${active ? "bg-accent text-accent-fg" : "text-muted hover:bg-hover hover:text-fg"}`;
  return (
    <div role="dialog" aria-modal="true" className="fixed inset-0 z-50 flex items-center justify-center bg-black/45 backdrop-blur-[2px] sm:p-6"
      onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="fade-in flex h-full w-full max-w-5xl flex-col overflow-hidden border border-line bg-elev shadow-2xl sm:h-[86vh] sm:rounded-3xl">
        <div className="flex flex-wrap items-center gap-1 border-b border-line px-3 py-2">
          <span className="mr-2 text-[14px] font-semibold">{t("drawing")}</span>
          {TOOLS.map(([id, Icon]) => <button key={id} title={t(`draw_${id}`)} onClick={() => setTool(id)} className={btn(tool === id)}><Icon size={16} /></button>)}
          <span className="mx-1.5 h-5 w-px bg-line" />
          {COLORS.map((c) => (
            <button key={c} title={c} onClick={() => { setColor(c); if (tool === "eraser") setTool("pen"); }}
              className={`h-6 w-6 rounded-full border transition ${color === c && tool !== "eraser" ? "scale-110 ring-2 ring-accent ring-offset-2 ring-offset-[var(--elev)]" : "border-line"}`} style={{ background: c }} />
          ))}
          <span className="mx-1.5 h-5 w-px bg-line" />
          {SIZES.map((s) => (
            <button key={s} title={`${s}px`} onClick={() => setSize(s)} className={btn(size === s)}>
              <span className="rounded-full bg-current" style={{ width: Math.min(16, s + 2), height: Math.min(16, s + 2) }} />
            </button>
          ))}
          <span className="mx-1.5 h-5 w-px bg-line" />
          <button title={t("undo")} onClick={undo} disabled={!shapes.length} className={`${btn(false)} disabled:opacity-30`}><Undo2 size={16} /></button>
          <button title={t("redo")} onClick={redoOne} disabled={!redo.length} className={`${btn(false)} disabled:opacity-30`}><Redo2 size={16} /></button>
          <button title={t("clear")} onClick={() => { setRedo([...redo, ...shapes.slice().reverse()]); setShapes([]); }} disabled={!shapes.length} className={`${btn(false)} disabled:opacity-30`}><Trash2 size={16} /></button>
          <div className="flex-1" />
          <button onClick={send} disabled={!shapes.length}
            className="flex h-8 items-center gap-1.5 rounded-xl bg-accent px-3 text-[13px] font-medium text-accent-fg disabled:opacity-40"><Send size={14} /> {t("draw_send")}</button>
          <button onClick={onClose} className="ml-1 rounded-lg p-1.5 text-muted hover:bg-hover"><X size={18} /></button>
        </div>
        <div ref={wrap} className="relative min-h-0 flex-1 bg-white" style={{ cursor: tool === "eraser" ? "cell" : "crosshair" }}>
          <canvas ref={canvas} className="absolute inset-0 touch-none" onPointerDown={down} onPointerMove={move} onPointerUp={up} onPointerCancel={up} />
          {!shapes.length && !draft.current && (
            <div className="pointer-events-none absolute inset-0 grid place-items-center text-sm text-zinc-400">{t("draw_hint")}</div>
          )}
        </div>
      </div>
    </div>
  );
}
