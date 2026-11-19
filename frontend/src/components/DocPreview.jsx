import { useEffect, useRef, useState } from "react";
import { AlertTriangle, Download, Loader2, X } from "lucide-react";
import { useStore, useT } from "../lib/store";
import { api } from "../lib/api";
import { docKind, fileType, formatSize } from "../lib/fileTypes";

// Office/PDF documents produced by the agent (make_doc) or found in the file manager, previewed in place:
// Excel via SheetJS, Word via docx-preview, PDF via the browser's own viewer, PowerPoint as slide cards.

const rawUrl = (path) => useStore.getState().fileApi(`/fs/raw?path=${encodeURIComponent(path)}`);
const fetchBytes = async (path) => {
  const r = await fetch(rawUrl(path));
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.arrayBuffer();
};

// Excel as Excel shows it: formatted values, formulas in the bar above the grid, merged cells, the file's column
// widths and fills, a frozen header row and column, sheet tabs at the bottom.
const colLetter = (i) => (i >= 26 ? colLetter(Math.floor(i / 26) - 1) : "") + String.fromCharCode(65 + (i % 26));

function SheetView({ path }) {
  const t = useT();
  const [book, setBook] = useState(null);
  const [tab, setTab] = useState(0);
  const [sel, setSel] = useState({ r: 0, c: 0 });
  useEffect(() => {
    let alive = true;
    Promise.all([import("xlsx"), fetchBytes(path)]).then(([XLSX, buf]) => {
      const wb = XLSX.read(buf, { type: "array", cellDates: true, cellStyles: true, cellFormula: true });
      const sheets = wb.SheetNames.map((name) => {
        const ws = wb.Sheets[name];
        const ref = ws["!ref"] ? XLSX.utils.decode_range(ws["!ref"]) : { s: { r: 0, c: 0 }, e: { r: -1, c: -1 } };
        const R = Math.min(ref.e.r, ref.s.r + 999), C = Math.min(ref.e.c, ref.s.c + 59);
        const cells = [];
        for (let r = ref.s.r; r <= R; r++) {
          const row = [];
          for (let c = ref.s.c; c <= C; c++) {
            const cell = ws[XLSX.utils.encode_cell({ r, c })];
            const fill = cell?.s?.fgColor?.rgb || cell?.s?.bgColor?.rgb;
            row.push(cell ? { v: cell.w ?? (cell.v instanceof Date ? cell.v.toLocaleDateString() : String(cell.v ?? "")),
              f: cell.f, n: cell.t === "n", bold: !!cell.s?.font?.bold || !!cell.s?.bold,
              fill: fill && fill.length >= 6 && !/^(FFFFFF|FFFFFFFF|000000)$/i.test(fill) ? `#${fill.slice(-6)}` : null } : null);
          }
          cells.push(row);
        }
        const merges = {}, hidden = new Set();
        for (const m of ws["!merges"] || []) {
          const r0 = m.s.r - ref.s.r, c0 = m.s.c - ref.s.c;
          merges[`${r0}:${c0}`] = { rs: m.e.r - m.s.r + 1, cs: m.e.c - m.s.c + 1 };
          for (let r = m.s.r; r <= m.e.r; r++) for (let c = m.s.c; c <= m.e.c; c++) if (r !== m.s.r || c !== m.s.c) hidden.add(`${r - ref.s.r}:${c - ref.s.c}`);
        }
        const widths = (ws["!cols"] || []).map((w) => (w?.wpx ? w.wpx : w?.wch ? Math.round(w.wch * 7.5 + 12) : null));
        return { name, cells, merges, hidden, widths, r0: ref.s.r, c0: ref.s.c, cols: Math.max(0, C - ref.s.c + 1) };
      });
      if (alive) setBook(sheets);
    }).catch((e) => alive && setBook({ error: e.message }));
    return () => { alive = false; };
  }, [path]);
  if (!book) return <Loading />;
  if (book.error) return <Failed msg={book.error} />;
  const sheet = book[tab] || { cells: [], cols: 0, merges: {}, hidden: new Set(), widths: [] };
  const cur = sheet.cells[sel.r]?.[sel.c];
  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="mb-1.5 flex items-center gap-2 rounded-lg border border-line bg-bg px-2 py-1 text-[12.5px]">
        <span className="w-14 shrink-0 border-r border-line pr-2 text-center font-mono text-subtle">{colLetter(sel.c + sheet.c0)}{sel.r + sheet.r0 + 1}</span>
        <span className="shrink-0 font-serif italic text-subtle">fx</span>
        <span className="min-w-0 flex-1 truncate font-mono">{cur ? (cur.f ? `=${cur.f}` : cur.v) : ""}</span>
      </div>
      <div className="min-h-0 flex-1 overflow-auto rounded-xl border border-line bg-bg">
        <table className="border-collapse text-[12.5px]">
          <thead className="sticky top-0 z-10">
            <tr>
              <th className="sticky left-0 z-20 w-10 border-b border-r border-line bg-hover" />
              {Array.from({ length: sheet.cols }, (_, i) => (
                <th key={i} style={{ minWidth: sheet.widths[i + sheet.c0] || 90 }}
                  className={`border-b border-r border-line px-2 py-1 text-center font-medium ${i === sel.c ? "bg-[#217346]/15 text-[#217346]" : "bg-hover text-subtle"}`}>{colLetter(i + sheet.c0)}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sheet.cells.map((r, i) => (
              <tr key={i} className={i === 0 ? "sticky top-[27px] z-[5] bg-bg font-semibold" : ""}>
                <td className={`sticky left-0 z-[4] border-b border-r border-line px-2 py-1 text-center text-[11px] ${i === sel.r ? "bg-[#217346]/15 text-[#217346]" : "bg-hover text-subtle"}`}>{i + sheet.r0 + 1}</td>
                {r.map((c, j) => {
                  if (sheet.hidden.has(`${i}:${j}`)) return null;
                  const m = sheet.merges[`${i}:${j}`];
                  const on = sel.r === i && sel.c === j;
                  return (
                    <td key={j} rowSpan={m?.rs} colSpan={m?.cs} onClick={() => setSel({ r: i, c: j })} title={c?.f ? `=${c.f}` : c?.v || ""}
                      style={{ background: c?.fill || undefined, maxWidth: (sheet.widths[j + sheet.c0] || 90) * 3 }}
                      className={`cursor-cell truncate border-b border-r border-line px-2 py-1 ${c?.n ? "text-right tabular-nums" : ""} ${c?.bold || i === 0 ? "font-semibold" : ""} ${m ? "text-center" : ""} ${on ? "outline outline-2 -outline-offset-2 outline-[#217346]" : ""}`}>
                      {c?.v ?? ""}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
        {!sheet.cells.length && <div className="p-6 text-center text-xs text-subtle">{t("empty_file")}</div>}
      </div>
      <div className="mt-1.5 flex gap-1 overflow-x-auto">
        {book.map((s, i) => (
          <button key={s.name} onClick={() => { setTab(i); setSel({ r: 0, c: 0 }); }}
            className={`shrink-0 rounded-b-lg border-t-2 px-3 py-1 text-xs font-medium ${i === tab ? "border-[#217346] bg-bg text-[#217346] shadow-sm" : "border-transparent text-muted hover:bg-hover"}`}>{s.name}</button>
        ))}
      </div>
    </div>
  );
}

function WordView({ path }) {
  const host = useRef(null);
  const [state, setState] = useState("loading");
  useEffect(() => {
    let alive = true;
    setState("loading");
    Promise.all([import("docx-preview"), fetchBytes(path)]).then(async ([docx, buf]) => {
      if (!alive || !host.current) return;
      host.current.innerHTML = "";
      await docx.renderAsync(buf, host.current, null, { className: "docx", inWrapper: true, breakPages: true, ignoreLastRenderedPageBreak: true });
      if (alive) setState("ok");
    }).catch((e) => alive && setState(e.message));
    return () => { alive = false; };
  }, [path]);
  return (
    <div className="relative h-full min-h-0 overflow-auto rounded-xl border border-line bg-[#e9e9ec] dark:bg-[#2a2a2e]">
      {state === "loading" && <Loading />}
      {state !== "loading" && state !== "ok" && <Failed msg={state} />}
      <div ref={host} className="docx-host" />
    </div>
  );
}

// One slide drawn from its real shapes (positions in % of the slide, font sizes scaled to the box width with
// container units), so pictures, colour bands, tables and charts look like PowerPoint shows them.
function Slide({ s, ratio, widthPt }) {
  const fs = (pt) => `calc(${pt || 18} / ${widthPt || 720} * 100cqw)`;
  const plain = !s.shapes?.length;
  return (
    <div className="relative w-full overflow-hidden rounded-md bg-white text-zinc-900 shadow-sm ring-1 ring-black/10"
      style={{ aspectRatio: ratio || 16 / 9, containerType: "inline-size", background: s.bg || "#fff" }}>
      {plain && (
        <div className="absolute inset-0 p-[5%]">
          <div className="mb-[2cqw] border-b-2 border-[#d24726] pb-[1cqw] font-bold leading-tight" style={{ fontSize: "4cqw" }}>{s.title}</div>
          {s.lines.map((l, j) => <div key={j} style={{ fontSize: "2.4cqw" }}>• {l}</div>)}
        </div>
      )}
      {(s.shapes || []).map((x, k) => {
        const pos = { left: `${x.x}%`, top: `${x.y}%`, width: `${x.w}%`, height: `${x.h}%` };
        if (x.kind === "image") return <img key={k} src={x.src} alt="" draggable={false} className="absolute object-contain" style={pos} />;
        if (x.kind === "rect") return <div key={k} className="absolute" style={{ ...pos, background: x.fill || "transparent", borderRadius: x.radius || undefined }} />;
        if (x.kind === "table") {
          return (
            <div key={k} className="absolute overflow-hidden" style={pos}>
              <table className="h-full w-full border-collapse" style={{ fontSize: fs(12) }}>
                <tbody>{x.rows.map((r, i) => (
                  <tr key={i} className={i === 0 ? "bg-[#1F4E79] font-semibold text-white" : i % 2 ? "bg-[#EEF3F8]" : "bg-white"}>
                    {r.map((c, j) => <td key={j} className="border border-black/10 px-[0.6cqw] py-[0.3cqw]">{c}</td>)}
                  </tr>))}
                </tbody>
              </table>
            </div>
          );
        }
        if (x.kind === "chart") {
          const vals = (x.series[0]?.values || []).map((v) => +v || 0);
          const max = Math.max(1, ...vals);
          return (
            <div key={k} className="absolute flex items-end gap-[1%] rounded border border-black/10 bg-white p-[1.5%]" style={pos}>
              {vals.map((v, i) => (
                <div key={i} className="flex flex-1 flex-col items-center justify-end" style={{ height: "100%" }}>
                  <div className="w-full rounded-t bg-[#2563EB]" style={{ height: `${(v / max) * 82}%` }} />
                  <span className="mt-[0.3cqw] truncate text-zinc-600" style={{ fontSize: fs(9) }}>{x.categories[i]}</span>
                </div>
              ))}
            </div>
          );
        }
        return (
          <div key={k} className={`absolute flex flex-col overflow-hidden leading-[1.2] ${x.valign === "middle" ? "justify-center" : x.valign === "bottom" ? "justify-end" : ""}`}
            style={{ ...pos, background: x.fill || "transparent", borderRadius: x.radius || undefined, padding: "0.5cqw 0.8cqw", fontWeight: x.title ? 600 : undefined }}>
            {x.paras.map((p, i) => (p.empty ? <div key={i} style={{ height: fs(10) }} /> : (
              <div key={i} style={{ fontSize: fs(p.pt), textAlign: p.align || undefined, paddingLeft: p.level ? `${p.level * 2.2}cqw` : undefined,
                marginTop: p.before ? fs(p.before) : p.bullet && i ? "0.6cqw" : undefined, marginBottom: p.after ? fs(p.after) : undefined, lineHeight: 1.25 }}>
                {p.bullet && <span className="mr-[0.8cqw]" style={{ color: p.runs[0]?.c || "#d24726" }}>{p.bullet === "#" ? `${(x.paras.slice(0, i).filter((q) => q.bullet === "#").length) + 1}.` : p.bullet}</span>}
                {p.runs.map((r, j) => <span key={j} style={{ fontWeight: r.b ? 700 : undefined, fontStyle: r.i ? "italic" : undefined, color: r.c || undefined, fontSize: r.pt ? fs(r.pt) : undefined }}>{p.bullet && j === 0 ? r.t.replace(/^•\s*/, "") : r.t}</span>)}
              </div>
            )))}
          </div>
        );
      })}
    </div>
  );
}

function SlidesView({ path }) {
  const t = useT();
  const [data, setData] = useState(null);
  const [cur, setCur] = useState(0);
  const thumbs = useRef(null);
  useEffect(() => {
    let alive = true;
    setCur(0);
    api.get(useStore.getState().fileApi(`/fs/slides?path=${encodeURIComponent(path)}`))
      .then((d) => alive && setData(d)).catch((e) => alive && setData({ error: e.message }));
    return () => { alive = false; };
  }, [path]);
  const n = data?.slides?.length || 0;
  useEffect(() => {
    const k = (e) => {
      if (/input|textarea/i.test(e.target.tagName)) return;
      if (["ArrowRight", "ArrowDown", "PageDown"].includes(e.key)) setCur((c) => Math.min(n - 1, c + 1));
      if (["ArrowLeft", "ArrowUp", "PageUp"].includes(e.key)) setCur((c) => Math.max(0, c - 1));
    };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [n]);
  useEffect(() => { thumbs.current?.querySelector(`[data-i="${cur}"]`)?.scrollIntoView({ block: "nearest", inline: "nearest" }); }, [cur]);
  if (!data) return <Loading />;
  if (data.error) return <Failed msg={data.error} />;
  if (!n) return <div className="p-6 text-center text-xs text-subtle">{t("empty_file")}</div>;
  const s = data.slides[cur];
  return (
    <div className="flex h-full min-h-0 flex-col gap-2 md:flex-row">
      <div ref={thumbs} className="order-2 flex shrink-0 gap-2 overflow-x-auto pb-1 md:order-1 md:w-44 md:flex-col md:overflow-y-auto md:overflow-x-hidden md:pb-0 md:pr-1">
        {data.slides.map((x, i) => (
          <button key={i} data-i={i} onClick={() => setCur(i)}
            className={`w-28 shrink-0 rounded-lg p-1 text-left transition md:w-full ${i === cur ? "bg-accent/10 ring-2 ring-accent" : "hover:bg-hover"}`}>
            <div className="pointer-events-none"><Slide s={x} ratio={data.ratio} widthPt={data.width_pt} /></div>
            <div className="mt-0.5 text-center text-[10px] text-subtle">{i + 1}</div>
          </button>
        ))}
      </div>
      <div className="order-1 flex min-h-0 flex-1 flex-col md:order-2">
        <div className="flex min-h-0 flex-1 items-center justify-center overflow-auto rounded-xl bg-[#e9e9ec] p-2 sm:p-4 dark:bg-[#2a2a2e]">
          <div className="w-full max-w-4xl"><Slide s={s} ratio={data.ratio} widthPt={data.width_pt} /></div>
        </div>
        <div className="mt-2 flex items-center gap-2 text-xs text-muted">
          <button onClick={() => setCur(Math.max(0, cur - 1))} disabled={!cur} className="rounded-lg border border-line px-2.5 py-1 hover:bg-hover disabled:opacity-40">‹</button>
          <span className="tabular-nums">{t("slide_n", { n: cur + 1 })} / {n}</span>
          <button onClick={() => setCur(Math.min(n - 1, cur + 1))} disabled={cur >= n - 1} className="rounded-lg border border-line px-2.5 py-1 hover:bg-hover disabled:opacity-40">›</button>
          {s.notes && <span className="ml-2 min-w-0 flex-1 truncate rounded-lg bg-hover px-2 py-1" title={s.notes}>{s.notes}</span>}
        </div>
      </div>
    </div>
  );
}

const Loading = () => <div className="grid h-40 place-items-center"><Loader2 size={20} className="animate-spin text-accent" /></div>;
function Failed({ msg }) {
  const t = useT();
  return (
    <div className="flex flex-col items-center gap-2 p-8 text-center text-sm text-muted">
      <AlertTriangle size={20} className="text-warn" />{t("preview_failed")}<span className="font-mono text-xs text-subtle">{msg}</span>
    </div>
  );
}

export function DocBody({ path }) {
  const kind = docKind(path);
  if (kind === "sheet") return <SheetView path={path} />;
  if (kind === "word") return <WordView path={path} />;
  if (kind === "slides") return <SlidesView path={path} />;
  if (kind === "pdf") return <iframe title={path} src={rawUrl(path)} className="h-full w-full rounded-xl border border-line bg-white" />;
  return <Failed msg="?" />;
}

// Full-screen preview dialog: opened with useStore.getState().previewFile(path).
export default function DocPreviewDialog() {
  const t = useT();
  const dialog = useStore((s) => s.dialog);
  const close = () => useStore.setState({ dialog: null });
  useEffect(() => {
    const k = (e) => e.key === "Escape" && close();
    addEventListener("keydown", k);
    return () => removeEventListener("keydown", k);
  }, []);
  if (dialog?.type !== "preview") return null;
  const { path, size } = dialog;
  const ft = fileType(path);
  const Icon = ft.icon;
  return (
    <div role="dialog" aria-modal="true" className="fixed inset-0 z-50 flex items-center justify-center bg-black/45 p-0 backdrop-blur-[2px] sm:p-6"
      onMouseDown={(e) => e.target === e.currentTarget && close()}>
      <div className="fade-in flex h-full w-full max-w-5xl flex-col overflow-hidden border border-line bg-elev shadow-2xl sm:h-[88vh] sm:rounded-3xl">
        <div className="flex items-center gap-3 border-b border-line px-4 py-3">
          <span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl text-white" style={{ background: ft.color }}><Icon size={18} /></span>
          <div className="min-w-0 flex-1">
            <div className="truncate text-[14px] font-semibold">{path.split(/[\\/]/).pop()}</div>
            <div className="truncate text-xs text-subtle">{t(`doc_${docKind(path) || "file"}`)}{size ? ` · ${formatSize(size)}` : ""} · <span className="font-mono">{path}</span></div>
          </div>
          <a href={rawUrl(path) + "&download=true"} title={t("download")} className="flex items-center gap-1.5 rounded-xl border border-line px-3 py-1.5 text-[13px] font-medium hover:bg-hover">
            <Download size={14} /><span className="hidden sm:inline">{t("download")}</span>
          </a>
          <button onClick={close} className="rounded-lg p-1.5 text-muted hover:bg-hover"><X size={18} /></button>
        </div>
        <div className="min-h-0 flex-1 p-3 sm:p-4"><DocBody path={path} /></div>
      </div>
    </div>
  );
}

// Clickable card for a generated document: big type icon, name and kind; a click opens the preview.
export function DocCard({ path }) {
  const t = useT();
  const ft = fileType(path);
  const Icon = ft.icon;
  const kind = docKind(path);
  const open = () => (kind ? useStore.getState().previewFile(path) : useStore.getState().openFile(path));
  return (
    <button onClick={open} title={path}
      className="group flex w-full max-w-sm items-center gap-3 rounded-2xl border border-line bg-elev p-2.5 pr-4 text-left shadow-[0_1px_4px_rgb(0_0_0/0.04)] transition hover:border-subtle hover:shadow-md">
      <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl text-white shadow-sm" style={{ background: ft.color }}>
        <Icon size={22} />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-[13.5px] font-semibold">{path.split(/[\\/]/).pop()}</span>
        <span className="block truncate text-xs text-subtle">{t(`doc_${kind || "file"}`)} · {ft.label}</span>
      </span>
      <span className="shrink-0 rounded-lg bg-hover px-2 py-1 text-[11px] font-medium text-muted group-hover:bg-accent group-hover:text-accent-fg">{t("preview")}</span>
    </button>
  );
}
