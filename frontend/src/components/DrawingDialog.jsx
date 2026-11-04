import { useEffect, useRef, useState } from "react";
import { ArrowUpRight, Circle, Eraser, Minus, Pencil, Redo2, RectangleHorizontal, Send, Trash2, Type, Undo2, X } from "lucide-react";
import { useT } from "../lib/store";

// Sketch pad and image editor: freehand pen, shapes, arrows, text, eraser, colors, undo/redo.
// Without `image` it is a blank sheet; with an attached image the marks are drawn over it and the result is
// exported at the image's own resolution, replacing the attachment.
const COLORS = ["#111827", "#ef4444", "#f97316", "#eab308", "#22c55e", "#3b82f6", "#8b5cf6", "#ec4899", "#ffffff"];
const SIZES = [2, 4, 8, 14];
const TEXT_PX = { 2: 18, 4: 26, 8: 38, 14: 56 }; // on-screen font size per size choice
const TOOLS = [["pen", Pencil], ["line", Minus], ["arrow", ArrowUpRight], ["rect", RectangleHorizontal], ["ellipse", Circle], ["text", Type], ["eraser", Eraser]];
const MAX_SIDE = 4096;
const FONT = "600 {px}px Inter, 'Segoe UI', system-ui, sans-serif";
const light = (hex) => {
  const n = parseInt(hex.slice(1), 16);
  return (0.299 * (n >> 16) + 0.587 * ((n >> 8) & 255) + 0.114 * (n & 255)) / 255 > 0.6;
};

function paint(ctx, s) {
  ctx.save();
  ctx.lineCap = ctx.lineJoin = "round";
  ctx.lineWidth = s.size;
  ctx.strokeStyle = s.color;
  if (s.tool === "eraser") ctx.globalCompositeOperation = "destination-out";
  const [a, b] = [s.points[0], s.points[s.points.length - 1]];
  if (s.tool === "text") {
    ctx.font = FONT.replace("{px}", s.size);
    ctx.textBaseline = "top";
    ctx.lineWidth = Math.max(2, s.size * 0.16);
    ctx.strokeStyle = light(s.color) ? "rgba(0,0,0,.55)" : "rgba(255,255,255,.75)";
    ctx.fillStyle = s.color;
    s.text.split("\n").forEach((line, i) => {
      ctx.strokeText(line, a.x, a.y + i * s.size * 1.2);
      ctx.fillText(line, a.x, a.y + i * s.size * 1.2);
    });
    ctx.restore();
    return;
  }
  ctx.beginPath();
  if (s.tool === "pen" || s.tool === "eraser") {
    s.points.forEach((p, i) => (i ? ctx.lineTo(p.x, p.y) : ctx.moveTo(p.x, p.y)));
    if (s.points.length === 1) ctx.lineTo(a.x + 0.1, a.y);
  } else if (s.tool === "line" || s.tool === "arrow") {
    ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y);
    if (s.tool === "arrow" && (a.x !== b.x || a.y !== b.y)) {
      const ang = Math.atan2(b.y - a.y, b.x - a.x), head = Math.max(10, s.size * 3.2);
      for (const d of [-0.45, 0.45]) {
        ctx.moveTo(b.x, b.y);
        ctx.lineTo(b.x - head * Math.cos(ang + d), b.y - head * Math.sin(ang + d));
      }
    }
  } else if (s.tool === "rect") {
    ctx.rect(a.x, a.y, b.x - a.x, b.y - a.y);
  } else if (s.tool === "ellipse") {
    ctx.ellipse((a.x + b.x) / 2, (a.y + b.y) / 2, Math.abs(b.x - a.x) / 2, Math.abs(b.y - a.y) / 2, 0, 0, Math.PI * 2);
  }
  ctx.stroke();
  ctx.restore();
}

export default function DrawingDialog({ onClose, onSend, image }) {
  const t = useT();
  const canvas = useRef(null);
  const wrap = useRef(null);
  const [tool, setTool] = useState("pen");
  const [color, setColor] = useState(image ? COLORS[1] : COLORS[0]);
  const [size, setSize] = useState(4);
  const [shapes, setShapes] = useState([]); // committed marks in document coordinates (vector, so undo is exact)
  const [redo, setRedo] = useState([]);
  const [typing, setTyping] = useState(null); // { x, y } in document coordinates while a text box is open
  const [bg, setBg] = useState(null); // the loaded image
  const draft = useRef(null);
  const view = useRef({ w: 1, h: 1, scale: 1, ox: 0, oy: 0 }); // document size and how it sits on screen
  const [, force] = useState(0);

  useEffect(() => {
    if (!image) return;
    const img = new Image();
    img.onload = () => setBg(img);
    img.src = `data:${image.mime || "image/png"};base64,${image.b64}`;
  }, [image]);

  // Marks are drawn on their own layer, so the eraser removes marks and never the photo under them.
  // The committed layer is cached; while drawing only the draft is painted on top (an eraser draft on a copy).
  const layerOf = (list, into) => {
    const { w, h } = view.current;
    const c = into || document.createElement("canvas");
    if (c.width !== w || c.height !== h) { c.width = w; c.height = h; } else c.getContext("2d").clearRect(0, 0, w, h);
    const ctx = c.getContext("2d");
    for (const s of list) paint(ctx, s);
    return c;
  };
  const cache = useRef({ layer: null, key: null, scratch: null });
  const committed = () => {
    const { w, h } = view.current, key = `${w}x${h}`;
    if (cache.current.list !== shapes || cache.current.key !== key) {
      cache.current.layer = layerOf(shapes, cache.current.layer);
      cache.current.list = shapes; cache.current.key = key;
    }
    return cache.current.layer;
  };

  const render = () => {
    const c = canvas.current;
    if (!c) return;
    const ctx = c.getContext("2d");
    const dpr = devicePixelRatio || 1;
    const { w, h, scale, ox, oy } = view.current;
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, c.width, c.height);
    ctx.setTransform(dpr * scale, 0, 0, dpr * scale, dpr * ox, dpr * oy);
    if (image) {
      ctx.shadowColor = "rgba(0,0,0,.25)"; ctx.shadowBlur = 24 / scale;
      if (bg) ctx.drawImage(bg, 0, 0, w, h);
      ctx.shadowColor = "transparent";
    } else {
      ctx.fillStyle = "#ffffff";
      ctx.fillRect(0, 0, w, h);
    }
    const d = draft.current;
    if (d?.tool === "eraser") {
      const sc = cache.current.scratch ||= document.createElement("canvas");
      layerOf([], sc).getContext("2d").drawImage(committed(), 0, 0);
      paint(sc.getContext("2d"), d);
      ctx.drawImage(sc, 0, 0);
    } else {
      ctx.drawImage(committed(), 0, 0);
      if (d) paint(ctx, d);
    }
  };
  const renderRef = useRef(render);
  renderRef.current = render;

  useEffect(() => {
    const fit = () => {
      const c = canvas.current, r = wrap.current.getBoundingClientRect(), dpr = devicePixelRatio || 1;
      c.width = r.width * dpr; c.height = r.height * dpr;
      c.style.width = `${r.width}px`; c.style.height = `${r.height}px`;
      if (image && bg) {
        const pad = r.width < 640 ? 12 : 32;
        const scale = Math.min((r.width - pad * 2) / bg.naturalWidth, (r.height - pad * 2) / bg.naturalHeight, 2);
        view.current = { w: bg.naturalWidth, h: bg.naturalHeight, scale,
          ox: (r.width - bg.naturalWidth * scale) / 2, oy: (r.height - bg.naturalHeight * scale) / 2 };
      } else if (!image) view.current = { w: Math.round(r.width), h: Math.round(r.height), scale: 1, ox: 0, oy: 0 };
      renderRef.current();
      force((n) => n + 1);
    };
    fit();
    const ro = new ResizeObserver(fit);
    ro.observe(wrap.current);
    return () => ro.disconnect();
  }, [bg, image]);
  useEffect(() => renderRef.current(), [shapes]);

  const undo = () => { if (shapes.length) { setRedo([...redo, shapes.at(-1)]); setShapes(shapes.slice(0, -1)); } };
  const redoOne = () => { if (redo.length) { setShapes([...shapes, redo.at(-1)]); setRedo(redo.slice(0, -1)); } };
  const commit = (s) => { setShapes((x) => [...x, s]); setRedo([]); };
  useEffect(() => {
    const k = (e) => {
      if (e.target.tagName === "TEXTAREA") return;
      if (e.key === "Escape") onClose();
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z") { e.preventDefault(); e.shiftKey ? redoOne() : undo(); }
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "y") { e.preventDefault(); redoOne(); }
    };
    addEventListener("keydown", k);
    return () => removeEventListener("keydown", k);
  });

  const pos = (e) => {
    const r = canvas.current.getBoundingClientRect(), { scale, ox, oy } = view.current;
    return { x: (e.clientX - r.left - ox) / scale, y: (e.clientY - r.top - oy) / scale };
  };
  const down = (e) => {
    if (image && !bg) return;
    if (tool === "text") { e.preventDefault(); return setTyping(pos(e)); }
    canvas.current.setPointerCapture(e.pointerId);
    const w = (tool === "eraser" ? size * 3 : size) / view.current.scale; // same on-screen thickness at any zoom
    draft.current = { tool, color, size: w, points: [pos(e)] };
    render();
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
    commit(draft.current);
    draft.current = null;
  };
  const textPx = TEXT_PX[size];
  const finishText = (value) => {
    if (typing && value.trim()) commit({ tool: "text", color, size: textPx / view.current.scale, text: value.replace(/\s+$/, ""), points: [typing] });
    setTyping(null);
  };

  const send = () => {
    const { w, h } = view.current;
    const k = Math.min(1, MAX_SIDE / Math.max(w, h));
    const out = document.createElement("canvas");
    out.width = Math.round(w * k); out.height = Math.round(h * k);
    const ctx = out.getContext("2d");
    ctx.scale(k, k);
    if (image) ctx.drawImage(bg, 0, 0, w, h);
    else { ctx.fillStyle = "#ffffff"; ctx.fillRect(0, 0, w, h); }
    ctx.drawImage(layerOf(shapes), 0, 0);
    const type = image && /jpe?g|webp/.test(image.mime || image.name) ? (/webp/.test(image.mime || image.name) ? "image/webp" : "image/jpeg") : "image/png";
    const ext = { "image/png": "png", "image/jpeg": "jpg", "image/webp": "webp" }[type];
    const base = image ? image.name.replace(/\.[^.]+$/, "") + "-" + t("draw_edited_suffix") : t("drawing").toLowerCase().replace(/\s+/g, "-") + "-" + Date.now();
    out.toBlob((blob) => { onSend(new File([blob], `${base}.${ext}`, { type })); onClose(); }, type, 0.92);
  };

  const { scale, ox, oy } = view.current;
  const btn = (active) => `grid h-8 w-8 shrink-0 place-items-center rounded-lg transition ${active ? "bg-accent text-accent-fg" : "text-muted hover:bg-hover hover:text-fg"}`;
  const sep = <span className="mx-1 hidden h-5 w-px shrink-0 bg-line sm:block" />;
  return (
    <div role="dialog" aria-modal="true" className="fixed inset-0 z-50 flex items-center justify-center bg-black/55 backdrop-blur-[3px] sm:p-6"
      onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="fade-in flex h-full w-full max-w-6xl flex-col overflow-hidden border border-line bg-elev shadow-2xl sm:h-[90vh] sm:rounded-3xl">
        <div className="flex items-center gap-3 border-b border-line px-4 py-2.5">
          <div className="min-w-0 flex-1">
            <div className="truncate text-[14px] font-semibold">{image ? t("draw_edit_title") : t("drawing")}</div>
            {image && <div className="truncate text-[11.5px] text-subtle">{image.name}{bg ? ` · ${bg.naturalWidth}×${bg.naturalHeight}` : ""}</div>}
          </div>
          <button onClick={send} disabled={!shapes.length || (image && !bg)}
            className="flex h-9 shrink-0 items-center gap-1.5 rounded-xl bg-accent px-3.5 text-[13px] font-medium text-accent-fg shadow-sm transition hover:opacity-90 disabled:opacity-40">
            <Send size={14} /> {t(image ? "draw_apply" : "draw_send")}</button>
          <button onClick={onClose} title={t("close")} className="grid h-9 w-9 shrink-0 place-items-center rounded-xl text-muted hover:bg-hover"><X size={18} /></button>
        </div>
        <div ref={wrap} className={`relative min-h-0 flex-1 overflow-hidden ${image ? "bg-[repeating-conic-gradient(var(--panel)_0_25%,var(--elev)_0_50%)] bg-[length:22px_22px]" : "bg-white"}`}
          style={{ cursor: tool === "text" ? "text" : tool === "eraser" ? "cell" : "crosshair" }}>
          <canvas ref={canvas} className="absolute inset-0 touch-none" onPointerDown={down} onPointerMove={move} onPointerUp={up} onPointerCancel={up} />
          {!image && !shapes.length && !draft.current && !typing && (
            <div className="pointer-events-none absolute inset-0 grid place-items-center text-sm text-zinc-400">{t("draw_hint")}</div>
          )}
          {typing && (
            <textarea autoFocus rows={1} placeholder={t("draw_text_ph")}
              onBlur={(e) => finishText(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Escape") { e.preventDefault(); setTyping(null); }
                if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); finishText(e.target.value); }
              }}
              onInput={(e) => { e.target.style.height = "auto"; e.target.style.height = e.target.scrollHeight + "px"; e.target.style.width = "auto"; e.target.style.width = Math.max(120, e.target.scrollWidth + 8) + "px"; }}
              className="absolute z-10 resize-none overflow-hidden whitespace-pre rounded-md border-2 border-dashed border-accent bg-black/10 px-1 font-semibold leading-[1.2] outline-none placeholder:text-current placeholder:opacity-50"
              style={{ left: ox + typing.x * scale - 6, top: oy + typing.y * scale - 4, color, fontSize: textPx, minWidth: 120,
                fontFamily: "Inter, 'Segoe UI', system-ui, sans-serif", textShadow: light(color) ? "0 0 3px rgba(0,0,0,.6)" : "0 0 3px rgba(255,255,255,.8)" }} />
          )}
        </div>
        <div className="flex flex-wrap items-center justify-center gap-x-1 gap-y-1.5 border-t border-line px-2 py-2 sm:justify-start sm:px-3">
          <div className="flex items-center gap-0.5">
            {TOOLS.map(([id, Icon]) => <button key={id} title={t(`draw_${id}`)} onClick={() => setTool(id)} className={btn(tool === id)}><Icon size={16} /></button>)}
          </div>
          {sep}
          <div className="flex items-center gap-1 px-0.5">
            {COLORS.map((c) => (
              <button key={c} title={c} onClick={() => { setColor(c); if (tool === "eraser") setTool("pen"); }}
                className={`h-6 w-6 shrink-0 rounded-full border transition ${color === c && tool !== "eraser" ? "scale-110 ring-2 ring-accent ring-offset-2 ring-offset-[var(--elev)]" : "border-line"}`} style={{ background: c }} />
            ))}
          </div>
          {sep}
          <div className="flex items-center gap-0.5">
            {SIZES.map((s) => (
              <button key={s} title={tool === "text" ? `${TEXT_PX[s]}px` : `${s}px`} onClick={() => setSize(s)} className={btn(size === s)}>
                {tool === "text" ? <span className="font-semibold" style={{ fontSize: 9 + SIZES.indexOf(s) * 2.5 }}>A</span>
                  : <span className="rounded-full bg-current" style={{ width: Math.min(16, s + 2), height: Math.min(16, s + 2) }} />}
              </button>
            ))}
          </div>
          {sep}
          <div className="flex items-center gap-0.5">
            <button title={t("undo")} onClick={undo} disabled={!shapes.length} className={`${btn(false)} disabled:opacity-30`}><Undo2 size={16} /></button>
            <button title={t("redo")} onClick={redoOne} disabled={!redo.length} className={`${btn(false)} disabled:opacity-30`}><Redo2 size={16} /></button>
            <button title={t("clear")} onClick={() => { setRedo([...redo, ...shapes.slice().reverse()]); setShapes([]); }} disabled={!shapes.length} className={`${btn(false)} disabled:opacity-30`}><Trash2 size={16} /></button>
          </div>
        </div>
      </div>
    </div>
  );
}
