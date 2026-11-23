import { memo, useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import Editor from "@monaco-editor/react";
import { Check, Code2, Download, Ellipsis, Eye, Maximize2, Minus, Plus, ScanSearch, X } from "lucide-react";
import { useStore, useT } from "../lib/store";
import { diagramConfig } from "../lib/diagramTheme";

// Mermaid diagrams (flowchart, sequence, gantt, mind map…) drawn in the chat in the app's own look: soft accent
// nodes, pill edge labels, thin grey lines, light and dark. Mermaid (~1 MB) is loaded only when a diagram shows.
// Renders run one at a time: mermaid.initialize is global, and two chats' diagrams must not mix their settings.

let mermaidP = null;
const loadMermaid = () => (mermaidP ||= import("mermaid").then((m) => m.default));
let queue = Promise.resolve();
let seq = 0;

const FONT = getComputedStyle(document.documentElement).fontFamily || "ui-sans-serif, system-ui, sans-serif";

// One render: the SVG text, or an error. export=true draws labels as SVG text (no HTML), so the picture can be
// painted on a canvas for PNG (an SVG with HTML labels taints the canvas).
export function renderMermaid(code, dark, forExport = false) {
  const job = queue.then(async () => {
    const mermaid = await loadMermaid();
    mermaid.initialize(diagramConfig(dark, FONT, forExport));
    const id = `aiiq-mmd-${++seq}`;
    try {
      const { svg } = await mermaid.render(id, code.trim());
      return { svg };
    } catch (e) {
      return { error: String(e?.message || e).split("\n").slice(0, 4).join("\n") };
    } finally {
      document.getElementById(id)?.remove();
      document.getElementById(`d${id}`)?.remove();
    }
  });
  queue = job.catch(() => {});
  return job;
}

function svgSize(svg) {
  const m = svg.match(/viewBox="[-\d.]+ [-\d.]+ ([\d.]+) ([\d.]+)"/);
  return m ? { w: parseFloat(m[1]), h: parseFloat(m[2]) } : { w: 800, h: 600 };
}

function saveBlob(blob, name) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = name;
  document.body.appendChild(a);
  a.click();
  setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
}

async function downloadPng(code, dark) {
  const { svg } = await renderMermaid(code, dark, true);
  if (!svg) return false;
  const { w, h } = svgSize(svg);
  const scale = Math.min(3, Math.max(2, 2400 / Math.max(w, 1)));
  const sized = svg.replace(/<svg([^>]*?)\swidth="[^"]*"/, "<svg$1").replace(/<svg([^>]*?)\sheight="[^"]*"/, "<svg$1")
    .replace("<svg", `<svg width="${w}" height="${h}"`).replace(/max-width:\s*[\d.]+px;?/, "");
  const img = new Image();
  img.src = "data:image/svg+xml;charset=utf-8," + encodeURIComponent(sized);
  await img.decode();
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(w * scale);
  canvas.height = Math.round(h * scale);
  const ctx = canvas.getContext("2d");
  ctx.fillStyle = dark ? "#17171a" : "#ffffff";
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.scale(scale, scale);
  ctx.drawImage(img, 0, 0, w, h);
  const blob = await new Promise((r) => canvas.toBlob(r, "image/png"));
  if (blob) saveBlob(blob, "diagram.png");
  return !!blob;
}

function useMermaid(code, dark) {
  const [state, setState] = useState({ svg: "", error: "" });
  useEffect(() => {
    let alive = true;
    const timer = setTimeout(() => {
      renderMermaid(code, dark).then((r) => {
        if (!alive) return;
        // Keep the last good picture while the code (being edited) does not parse.
        setState((s) => (r.svg ? { svg: r.svg, error: "" } : { svg: s.svg, error: r.error || "?" }));
      });
    }, 250);
    return () => { alive = false; clearTimeout(timer); };
  }, [code, dark]);
  return state;
}

function ToolButton({ title, onClick, children, label }) {
  return (
    <button type="button" title={title} onClick={onClick}
      className={`flex h-8 items-center justify-center gap-1.5 rounded-full text-muted transition hover:bg-hover hover:text-fg ${label ? "px-3 text-[13px] font-medium" : "w-8"}`}>
      {children}{label && <span>{label}</span>}
    </button>
  );
}

// Full-screen view: zoom (buttons, wheel, keys), drag to pan, fit; "Edit code" switches to a live Monaco editor
// whose changes redraw the diagram (kept for this message on screen; the saved chat is not changed).
function DiagramViewer({ code, setCode, original, dark, onClose }) {
  const t = useT();
  const [edit, setEdit] = useState(false);
  const [editorReady, setEditorReady] = useState(false);
  const { svg, error } = useMermaid(code, dark);
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const box = useRef(null);
  const drag = useRef(null);

  const fit = useCallback(() => {
    if (!svg || !box.current) return;
    const { w, h } = svgSize(svg);
    const r = box.current.getBoundingClientRect();
    setZoom(Math.max(0.1, Math.min(2, Math.min((r.width - 64) / w, (r.height - 96) / h))));
    setPan({ x: 0, y: 0 });
  }, [svg]);
  useEffect(() => { if (!edit) fit(); }, [edit, fit]);

  useEffect(() => {
    const onKey = (e) => {
      if (e.key === "Escape") onClose();
      if (edit) return;
      if (e.key === "+" || e.key === "=") setZoom((z) => Math.min(4, z * 1.2));
      if (e.key === "-") setZoom((z) => Math.max(0.1, z / 1.2));
      if (e.key === "0") fit();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [edit, fit, onClose]);

  useEffect(() => {
    if (!edit) return;
    import("../lib/monaco").then(() => setEditorReady(true)).catch(() => setEditorReady(true));
  }, [edit]);

  const onWheel = (e) => setZoom((z) => Math.max(0.1, Math.min(4, z * (e.deltaY < 0 ? 1.1 : 1 / 1.1))));
  const onDown = (e) => { drag.current = { x: e.clientX - pan.x, y: e.clientY - pan.y }; e.currentTarget.setPointerCapture(e.pointerId); };
  const onMove = (e) => { if (drag.current) setPan({ x: e.clientX - drag.current.x, y: e.clientY - drag.current.y }); };
  const onUp = () => { drag.current = null; };

  return createPortal(
    <div className="fixed inset-0 z-[200] flex flex-col bg-black/55 p-3 backdrop-blur-[2px] sm:p-5" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="relative flex min-h-0 flex-1 flex-col overflow-hidden rounded-2xl border border-line bg-elev shadow-2xl">
        <div className="absolute right-3 top-3 z-10 flex items-center gap-1 rounded-full border border-line bg-elev/95 p-1 shadow-sm backdrop-blur">
          {edit && code !== original && (
            <ToolButton title={t("diagram_reset")} label={t("diagram_reset")} onClick={() => setCode(original)} />
          )}
          <ToolButton title={edit ? t("diagram_view") : t("diagram_edit")} label={edit ? t("diagram_view") : t("diagram_edit")} onClick={() => setEdit((v) => !v)}>
            {edit ? <Eye size={15} /> : <Code2 size={15} />}
          </ToolButton>
          <ToolButton title={t("diagram_download_png")} onClick={() => downloadPng(code, dark)}><Download size={15} /></ToolButton>
          <ToolButton title={t("close")} onClick={onClose}><X size={16} /></ToolButton>
        </div>
        {edit ? (
          <div className="flex min-h-0 flex-1 flex-col pt-14 lg:flex-row lg:pt-0">
            <div className="min-h-[220px] flex-1 border-line lg:border-r lg:pt-14">
              {editorReady && (
                <Editor language="markdown" value={code} onChange={(v) => setCode(v ?? "")} theme={dark ? "vs-dark" : "vs"}
                  options={{ fontSize: 13, minimap: { enabled: false }, wordWrap: "on", automaticLayout: true, scrollBeyondLastLine: false, padding: { top: 10 }, lineNumbersMinChars: 3 }} />
              )}
            </div>
            <div className="flex min-h-0 flex-1 flex-col lg:pt-14">
              <div className="min-h-0 flex-1 overflow-auto p-4">
                {svg && <div className="diagram-svg mx-auto w-fit" dangerouslySetInnerHTML={{ __html: svg }} />}
              </div>
              {error && <div className="border-t border-line bg-danger/10 px-4 py-2 font-mono text-xs text-danger whitespace-pre-wrap">{error}</div>}
            </div>
          </div>
        ) : (
          <div ref={box} className="relative min-h-0 flex-1 cursor-grab touch-none overflow-hidden active:cursor-grabbing"
            onWheel={onWheel} onPointerDown={onDown} onPointerMove={onMove} onPointerUp={onUp} onDoubleClick={fit}>
            {svg && (
              <div className="absolute left-1/2 top-1/2" style={{ transform: `translate(-50%, -50%) translate(${pan.x}px, ${pan.y}px) scale(${zoom})`, transformOrigin: "center" }}>
                <div className="diagram-svg" dangerouslySetInnerHTML={{ __html: svg }} />
              </div>
            )}
            {!svg && error && <div className="p-6 font-mono text-xs text-danger whitespace-pre-wrap">{error}</div>}
          </div>
        )}
      </div>
      {!edit && (
        <div className="mx-auto mt-3 flex items-center gap-1 rounded-full border border-line bg-elev p-1 shadow-lg">
          <ToolButton title={t("zoom_out")} onClick={() => setZoom((z) => Math.max(0.1, z / 1.2))}><Minus size={15} /></ToolButton>
          <span className="w-14 text-center text-[13px] font-medium tabular-nums">%{Math.round(zoom * 100)}</span>
          <ToolButton title={t("zoom_in")} onClick={() => setZoom((z) => Math.min(4, z * 1.2))}><Plus size={15} /></ToolButton>
          <ToolButton title={t("diagram_fit")} onClick={fit}><ScanSearch size={15} /></ToolButton>
        </div>
      )}
    </div>,
    document.body,
  );
}

function Diagram({ code: source }) {
  const t = useT();
  const dark = useStore((s) => s.dark);
  const [code, setCode] = useState(source);
  useEffect(() => setCode(source), [source]);
  const { svg, error } = useMermaid(code, dark);
  const [menu, setMenu] = useState(false);
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const [showCode, setShowCode] = useState(false);

  useEffect(() => {
    if (!menu) return undefined;
    const close = () => setMenu(false);
    const id = setTimeout(() => window.addEventListener("click", close), 0);
    return () => { clearTimeout(id); window.removeEventListener("click", close); };
  }, [menu]);

  const copy = async () => {
    try { await navigator.clipboard.writeText(code); setCopied(true); setTimeout(() => setCopied(false), 1500); } catch {}
  };
  const saveSvg = () => svg && saveBlob(new Blob([svg], { type: "image/svg+xml" }), "diagram.svg");

  if (error && !svg) {
    // Not drawable (a typo in the model's code): the code stays readable, with Mermaid's reason under it.
    return (
      <div className="my-3 overflow-hidden rounded-2xl border border-line bg-code">
        <div className="flex items-center justify-between border-b border-line px-3 py-1.5 text-xs text-muted">
          <span className="font-mono">mermaid</span>
          <button onClick={copy} className="flex items-center gap-1 rounded-lg px-2 py-1 hover:bg-hover">
            {copied ? <Check size={13} className="text-ok" /> : <Code2 size={13} />}<span>{copied ? t("copied") : t("diagram_copy_code")}</span>
          </button>
        </div>
        <pre className="max-h-[360px] overflow-auto px-4 py-2.5 font-mono text-[12.5px] leading-relaxed">{code}</pre>
        <div className="border-t border-line bg-danger/10 px-4 py-2 font-mono text-xs text-danger whitespace-pre-wrap">{t("diagram_error")}: {error}</div>
      </div>
    );
  }

  return (
    <div className="group/diagram relative my-3 rounded-2xl border border-transparent transition hover:border-line">
      <div className="absolute right-2 top-2 z-[1] flex items-center gap-0.5 rounded-full border border-line bg-elev/95 p-0.5 opacity-0 shadow-sm backdrop-blur transition group-hover/diagram:opacity-100 focus-within:opacity-100">
        <div className="relative">
          <ToolButton title={t("more")} onClick={() => setMenu((v) => !v)}><Ellipsis size={16} /></ToolButton>
          {menu && (
            <div className="absolute right-0 top-10 z-20 w-56 overflow-hidden rounded-xl border border-line bg-elev py-1 text-[13px] shadow-xl">
              <MenuItem icon={copied ? Check : Code2} onClick={copy}>{copied ? t("copied") : t("diagram_copy_code")}</MenuItem>
              <MenuItem icon={Eye} onClick={() => setShowCode((v) => !v)}>{showCode ? t("diagram_hide_code") : t("diagram_show_code")}</MenuItem>
              <MenuItem icon={Download} onClick={() => downloadPng(code, dark)}>{t("diagram_download_png")}</MenuItem>
              <MenuItem icon={Download} onClick={saveSvg}>{t("diagram_download_svg")}</MenuItem>
            </div>
          )}
        </div>
        <ToolButton title={t("diagram_expand")} onClick={() => setOpen(true)}><Maximize2 size={15} /></ToolButton>
      </div>
      <div className="cursor-zoom-in overflow-x-auto px-2 py-3" onClick={() => setOpen(true)} title={t("diagram_expand")}>
        {svg
          ? <div className="diagram-svg diagram-inline mx-auto w-fit max-w-full" dangerouslySetInnerHTML={{ __html: svg }} />
          : <div className="flex h-24 items-center justify-center text-xs text-subtle">{t("diagram_drawing")}</div>}
      </div>
      {showCode && <pre className="mx-2 mb-2 max-h-[320px] overflow-auto rounded-xl border border-line bg-code px-4 py-2.5 font-mono text-[12.5px] leading-relaxed">{code}</pre>}
      {open && <DiagramViewer code={code} setCode={setCode} original={source} dark={dark} onClose={() => setOpen(false)} />}
    </div>
  );
}

function MenuItem({ icon: Icon, onClick, children }) {
  return (
    <button type="button" onClick={onClick} className="flex w-full items-center gap-2.5 px-3 py-2 text-left hover:bg-hover">
      <Icon size={15} className="text-muted" />{children}
    </button>
  );
}

export default memo(Diagram);
