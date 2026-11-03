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

function SheetView({ path }) {
  const t = useT();
  const [book, setBook] = useState(null);
  const [tab, setTab] = useState(0);
  useEffect(() => {
    let alive = true;
    Promise.all([import("xlsx"), fetchBytes(path)]).then(([XLSX, buf]) => {
      const wb = XLSX.read(buf, { type: "array", cellDates: true });
      const sheets = wb.SheetNames.map((name) => ({
        name, rows: XLSX.utils.sheet_to_json(wb.Sheets[name], { header: 1, raw: false, defval: "" }).slice(0, 1000),
      }));
      if (alive) setBook(sheets);
    }).catch((e) => alive && setBook({ error: e.message }));
    return () => { alive = false; };
  }, [path]);
  if (!book) return <Loading />;
  if (book.error) return <Failed msg={book.error} />;
  const sheet = book[tab] || { rows: [] };
  const cols = Math.max(1, ...sheet.rows.map((r) => r.length));
  const letter = (i) => (i >= 26 ? letter(Math.floor(i / 26) - 1) : "") + String.fromCharCode(65 + (i % 26));
  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="min-h-0 flex-1 overflow-auto rounded-xl border border-line bg-bg">
        <table className="border-collapse text-[12.5px]">
          <thead className="sticky top-0 z-10">
            <tr>
              <th className="sticky left-0 z-20 w-10 border-b border-r border-line bg-hover" />
              {Array.from({ length: cols }, (_, i) => (
                <th key={i} className="min-w-[90px] border-b border-r border-line bg-hover px-2 py-1 text-center font-medium text-subtle">{letter(i)}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sheet.rows.map((r, i) => (
              <tr key={i} className={i === 0 ? "font-semibold" : "hover:bg-hover/60"}>
                <td className="sticky left-0 border-b border-r border-line bg-hover px-2 py-1 text-center text-[11px] text-subtle">{i + 1}</td>
                {Array.from({ length: cols }, (_, j) => (
                  <td key={j} className={`max-w-[280px] truncate border-b border-r border-line px-2 py-1 ${/^-?[\d.,]+\s*[₺$€%]?$/.test(r[j]) ? "text-right tabular-nums" : ""}`} title={String(r[j] ?? "")}>{String(r[j] ?? "")}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
        {!sheet.rows.length && <div className="p-6 text-center text-xs text-subtle">{t("empty_file")}</div>}
      </div>
      {book.length > 1 && (
        <div className="mt-2 flex gap-1 overflow-x-auto">
          {book.map((s, i) => (
            <button key={s.name} onClick={() => setTab(i)}
              className={`shrink-0 rounded-lg px-3 py-1 text-xs font-medium ${i === tab ? "bg-[#217346] text-white" : "text-muted hover:bg-hover"}`}>{s.name}</button>
          ))}
        </div>
      )}
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

function SlidesView({ path }) {
  const t = useT();
  const [data, setData] = useState(null);
  useEffect(() => {
    let alive = true;
    api.get(useStore.getState().fileApi(`/fs/slides?path=${encodeURIComponent(path)}`))
      .then((d) => alive && setData(d)).catch((e) => alive && setData({ error: e.message }));
    return () => { alive = false; };
  }, [path]);
  if (!data) return <Loading />;
  if (data.error) return <Failed msg={data.error} />;
  return (
    <div className="h-full min-h-0 space-y-4 overflow-y-auto pr-1">
      {data.slides.map((s, i) => (
        <div key={i} className="mx-auto max-w-2xl">
          <div className="mb-1 text-[11px] font-medium text-subtle">{t("slide_n", { n: i + 1 })}</div>
          <div className="aspect-video overflow-hidden rounded-xl border border-line bg-white p-[5%] text-zinc-900 shadow-sm">
            <div className="mb-3 border-b-2 border-[#d24726] pb-2 text-[clamp(14px,2.6vw,22px)] font-bold leading-tight">{s.title || " "}</div>
            <ul className="space-y-1 text-[clamp(11px,1.7vw,14px)]">
              {s.lines.map((l, j) => <li key={j} className="flex gap-2"><span className="text-[#d24726]">•</span><span>{l}</span></li>)}
            </ul>
          </div>
          {s.notes && <div className="mt-1 rounded-lg bg-hover px-3 py-1.5 text-xs text-muted">{s.notes}</div>}
        </div>
      ))}
      {!data.slides.length && <div className="p-6 text-center text-xs text-subtle">{t("empty_file")}</div>}
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
