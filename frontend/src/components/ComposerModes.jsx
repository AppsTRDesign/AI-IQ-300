import { useEffect, useRef, useState } from "react";
import {
  Camera, ChevronLeft, ChevronRight, Film, FileSpreadsheet, FileText, FileType2, FolderOpen, Image as ImageIcon,
  LayoutGrid, LayoutTemplate, Loader2, Presentation, Sparkles, Trash2, Upload, Wand2, X, Plug, Wrench, Search, Braces, ChevronDown,
} from "lucide-react";
import { useStore, useT } from "../lib/store";
import { api } from "../lib/api";
import { isImage } from "../lib/fileTypes";
import { Modal } from "./ui";

// The (+) menu's "make something" entries as coloured mode chips in the composer (not text typed into it): the chip
// says what will be made, the text says what it should be; the instruction for the model is added when it is sent.
// Document modes open a template gallery (each format has its own templates; Template Creator makes new ones).

export const MODES = {
  make_image: { icon: Wand2, tone: "text-orange-600 dark:text-orange-400", bg: "bg-orange-500/12", label: "make_image", say: "make_image_prefix" },
  make_video: { icon: Film, tone: "text-pink-600 dark:text-pink-400", bg: "bg-pink-500/12", label: "make_video", say: "make_video_prefix" },
  make_aiclip: { icon: Sparkles, tone: "text-rose-600 dark:text-rose-400", bg: "bg-rose-500/12", label: "make_aiclip", say: "make_aiclip_prefix" },
  img2video: { icon: ImageIcon, tone: "text-fuchsia-600 dark:text-fuchsia-400", bg: "bg-fuchsia-500/12", label: "img2video", say: "img2video_say" },
  web_shot: { icon: Camera, tone: "text-cyan-600 dark:text-cyan-400", bg: "bg-cyan-500/12", label: "web_shot", say: "web_shot_prefix" },
  docx: { icon: FileText, tone: "text-blue-600 dark:text-blue-400", bg: "bg-blue-500/12", label: "documents", say: "doc_say_docx", doc: "docx" },
  pdf: { icon: FileType2, tone: "text-red-600 dark:text-red-400", bg: "bg-red-500/12", label: "pdf", say: "doc_say_pdf", doc: "pdf" },
  xlsx: { icon: FileSpreadsheet, tone: "text-green-700 dark:text-green-400", bg: "bg-green-500/12", label: "spreadsheets", say: "doc_say_xlsx", doc: "xlsx" },
  pptx: { icon: Presentation, tone: "text-orange-700 dark:text-orange-400", bg: "bg-orange-600/12", label: "presentations", say: "doc_say_pptx", doc: "pptx" },
  // an MCP tool the user picked (+ menu > MCP tool, or Settings > MCP > Try > Use in chat): the model calls it
  mcp: { icon: Plug, tone: "text-violet-600 dark:text-violet-400", bg: "bg-violet-500/12", label: "mcp_tool", say: "mcp_say" },
};

// The text the model gets in front of the user's words
export function modeInstruction(t, mode, tpl, image) {
  if (!mode) return "";
  const m = MODES[mode.id];
  let s = t(m.say, { name: image || mode.tool || "", path: image || "" });
  if (mode.args && Object.keys(mode.args).length) s = `${s.trim()} ${JSON.stringify(mode.args)}`;
  if (tpl?.creator) s += " " + t("tpl_creator_say", { kind: m.doc?.toUpperCase() || "" });
  else if (tpl) s += ` [${t("tpl_word")}: ${tpl.name} — ${tpl.instruction}] `;
  return s.trim() + " ";
}

// The chips of a sent message (stored in its meta): the mode, the template; `strip` is the instruction text at the
// start of the message, hidden in the bubble because the chips say it.
export function modeChips(t, mode, tpl, image, prefix) {
  if (!mode) return [];
  const out = [{ kind: "mode", id: mode.id, label: t(MODES[mode.id].label), strip: prefix.trim() }];
  if (tpl) out.push({ kind: "tpl", creator: !!tpl.creator, id: tpl.id || "", label: tpl.creator ? t("tpl_creator") : tpl.name });
  if (image) out.push({ kind: "image", label: image });
  if (mode.tool) out.push({ kind: "tool", label: mode.tool });
  if (mode.args && Object.keys(mode.args).length) out.push({ kind: "args", label: argsLabel(mode.args), args: mode.args });
  return out;
}

// A message whose text starts with a mode's instruction (copied from an earlier message and sent again, or typed):
// the same chips as when it was sent from the (+) menu. Returns [] when the text has no such start.
export function chipsFromText(t, content) {
  const text = content || "";
  // The MCP tool instruction has the tool's name inside it ("{name} MCP aracını ... yap:" / "Do this by calling the
  // MCP tool {name} with the mcp tool:"): head + server/tool + tail, in either language order.
  {
    const [head = "", tail = ""] = t(MODES.mcp.say, { name: "\u0001" }).split("\u0001");
    const esc = (s) => s.trim().replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const m = (head.trim() || tail.trim()) && text.match(new RegExp(`^${esc(head)}${head.trim() ? "\\s*" : ""}([a-z0-9_-]{1,32}/[\\w.-]{1,64})\\s*${esc(tail)}`));
    if (m) {
      const chips = [{ kind: "mode", id: "mcp", label: t(MODES.mcp.label), strip: m[0].trim() }, { kind: "tool", label: m[1] }];
      const json = leadingJson(text.slice(m[0].length));
      if (json) {
        chips.push({ kind: "args", label: argsLabel(json.value), args: json.value });
        chips[0].strip = text.slice(0, m[0].length + json.end).trim();
      }
      return chips;
    }
  }
  for (const [id, m] of Object.entries(MODES)) {
    if (id === "mcp") continue;
    const say = (t(m.say, { name: "\u0001", path: "\u0001" }) || "").split("\u0001")[0].trim();
    if (!say || say.length < 4 || !text.startsWith(say)) continue;
    let end = say.length;
    const chips = [{ kind: "mode", id, label: t(m.label) }];
    const rest = text.slice(end);
    const br = rest.match(/^\s*\[([^\]]{3,800})\]/);
    if (br) {
      const inner = br[1];
      const creator = /Template Creator|doc_template action=create/i.test(inner) || inner.startsWith(t("tpl_creator"));
      const name = creator ? t("tpl_creator") : inner.replace(new RegExp(`^${t("tpl_word")}:\\s*`), "").split(/\s+[—-]\s+/)[0].trim();
      chips.push({ kind: "tpl", creator, label: name.slice(0, 60) });
      end += br[0].length;
    }
    chips[0].strip = text.slice(0, end).trim();
    return chips;
  }
  return [];
}

// "{...}" at the start of a text: the JSON object and where it ends (the MCP arguments after the tool instruction)
function leadingJson(rest) {
  const lead = rest.match(/^\s*/)[0].length;
  if (rest[lead] !== "{") return null;
  let depth = 0, str = false;
  for (let i = lead; i < rest.length; i++) {
    const c = rest[i];
    if (str) { if (c === "\\") i++; else if (c === '"') str = false; continue; }
    if (c === '"') str = true;
    else if (c === "{") depth++;
    else if (c === "}" && --depth === 0) {
      try { return { value: JSON.parse(rest.slice(lead, i + 1)), end: i + 1 }; } catch { return null; }
    }
  }
  return null;
}

// query="C# read file" · language="C#": the filled-in MCP arguments as one short chip
export const argsLabel = (args) => Object.entries(args || {}).map(([k, v]) => `${k}=${typeof v === "string" ? v : JSON.stringify(v)}`)
  .join(" · ").slice(0, 120);

// Read-only chips over a sent message
export function SentChips({ chips }) {
  if (!chips?.length) return null;
  return (
    <div className="flex max-w-[90%] flex-wrap justify-end gap-1.5">
      {chips.map((c, i) => {
        const m = c.kind === "mode" ? MODES[c.id] : null;
        const Icon = m ? m.icon : c.kind === "tpl" ? (c.creator ? Sparkles : LayoutTemplate) : c.kind === "tool" ? Wrench : c.kind === "args" ? Braces : ImageIcon;
        const cls = m ? `${m.tone} ${m.bg}` : c.kind === "tpl" ? "bg-accent-soft text-accent"
          : c.kind === "tool" || c.kind === "args" ? "bg-violet-500/10 font-mono text-violet-600 dark:text-violet-400" : "bg-fuchsia-500/12 text-fuchsia-600 dark:text-fuchsia-400";
        return (
          <span key={i} className={`inline-flex max-w-[260px] items-center gap-1.5 rounded-lg px-2 py-0.5 text-[12.5px] font-semibold ${cls}`}>
            <Icon size={13} className="shrink-0" /><span className="truncate">{c.label}</span>
          </span>
        );
      })}
    </div>
  );
}

export function ModeChips({ mode, tpl, image, onClear, onClearTpl, onPickImage, onToggleArgs, argsOpen }) {
  const t = useT();
  if (!mode) return null;
  const m = MODES[mode.id];
  const Icon = m.icon;
  return (
    <div className="flex flex-wrap items-center gap-1.5 px-3 pt-2.5">
      <span className={`inline-flex items-center gap-1.5 rounded-lg px-2 py-0.5 text-[13px] font-semibold ${m.tone} ${m.bg}`}>
        <Icon size={14} />{t(m.label)}
        <button onClick={onClear} title={t("remove")} className="-mr-0.5 rounded p-0.5 opacity-60 hover:opacity-100"><X size={12} /></button>
      </span>
      {tpl && (
        <span className="inline-flex items-center gap-1.5 rounded-lg bg-accent-soft px-2 py-0.5 text-[13px] font-semibold text-accent">
          {tpl.creator ? <Sparkles size={13} /> : <LayoutTemplate size={13} />}{tpl.creator ? t("tpl_creator") : tpl.name}
          <button onClick={onClearTpl} title={t("remove")} className="-mr-0.5 rounded p-0.5 opacity-60 hover:opacity-100"><X size={12} /></button>
        </span>
      )}
      {mode.id === "img2video" && (
        <button onClick={onPickImage} className="inline-flex max-w-[260px] items-center gap-1.5 rounded-lg border border-dashed border-line px-2 py-0.5 text-[12.5px] text-muted hover:border-accent hover:text-accent">
          <ImageIcon size={13} /><span className="truncate">{image || t("img2video_pick")}</span>
        </button>
      )}
      {mode.id === "mcp" && (
        <button onClick={mode.tool ? onToggleArgs : onPickImage} title={mode.tool ? t("mcp_args_toggle") : ""}
          className={`inline-flex max-w-[320px] items-center gap-1.5 rounded-lg px-2 py-0.5 font-mono text-[12.5px] ${mode.tool
          ? "bg-violet-500/10 text-violet-600 hover:opacity-90 dark:text-violet-400" : "border border-dashed border-line text-muted hover:border-accent hover:text-accent"}`}>
          <Wrench size={13} className="shrink-0" /><span className="truncate">{mode.tool || t("mcp_pick_tool")}</span>
          {mode.tool && <ChevronDown size={12} className={`shrink-0 transition-transform ${argsOpen ? "rotate-180" : ""}`} />}
        </button>
      )}
      {mode.id === "mcp" && mode.args && Object.keys(mode.args).length > 0 && !argsOpen && (
        <button onClick={onToggleArgs} className="inline-flex max-w-[320px] items-center gap-1.5 rounded-lg bg-violet-500/10 px-2 py-0.5 font-mono text-[12px] text-violet-600 hover:opacity-90 dark:text-violet-400">
          <Braces size={12} className="shrink-0" /><span className="truncate">{argsLabel(mode.args)}</span>
        </button>
      )}
    </div>
  );
}

// Pick an MCP tool for the composer chip: the tools of the running servers (Settings > MCP adds servers).
export function McpToolPicker({ onPick, onClose }) {
  const t = useT();
  const [servers, setServers] = useState(null);
  const [q, setQ] = useState("");
  useEffect(() => { api.get("/api/mcp").then(setServers).catch(() => setServers({})); }, []);
  const ql = q.trim().toLowerCase();
  const rows = Object.entries(servers || {}).filter(([, s]) => s.running)
    .flatMap(([sid, s]) => (s.tools || []).map((tl) => ({ sid, server: s.name || sid, ...tl })))
    .filter((r) => !ql || `${r.sid} ${r.name} ${r.description}`.toLowerCase().includes(ql));
  const openSettings = () => { onClose(); useStore.getState().setView("settings"); useStore.setState({ settingsTab: "mcp" }); };
  return (
    <Modal title={t("mcp_pick_tool")} onClose={onClose} width="max-w-xl">
      <div className="space-y-2 text-[13px]">
        <div className="relative">
          <Search size={14} className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-subtle" />
          <input autoFocus value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("mcp_cat_search")}
            className="w-full rounded-lg border border-line bg-surface py-1.5 pl-8 pr-2 text-[13px] outline-none focus:border-accent" />
        </div>
        {servers == null && <div className="grid h-20 place-items-center"><Loader2 size={16} className="animate-spin text-accent" /></div>}
        {servers && rows.length === 0 && (
          <div className="space-y-2 py-4 text-center text-muted">
            <p>{t("mcp_pick_none")}</p>
            <button onClick={openSettings} className="rounded-lg bg-accent-soft px-2.5 py-1 text-xs font-medium text-accent">{t("mcp_open_settings")}</button>
          </div>
        )}
        <div className="max-h-[55vh] space-y-1 overflow-y-auto">
          {rows.map((r) => (
            <button key={`${r.sid}/${r.name}`} onClick={() => onPick(`${r.sid}/${r.name}`)}
              className="flex w-full items-start gap-2 rounded-lg px-2 py-1.5 text-left hover:bg-hover">
              <Wrench size={14} className="mt-0.5 shrink-0 text-violet-500" />
              <span className="min-w-0">
                <span className="block font-mono text-[12.5px]"><span className="text-subtle">{r.sid}/</span>{r.name}</span>
                {r.description && <span className="line-clamp-2 block text-xs leading-snug text-muted">{r.description}</span>}
              </span>
            </button>
          ))}
        </div>
      </div>
    </Modal>
  );
}

// Templates of one format, as real thumbnails (the template's own page, drawn by the document engine): a strip with
// the first ones and a "View all" card that opens every template in a dialog (more load while scrolling down).
// The arrows go grey at the ends of the strip.
const STRIP = 8;
const PAGE_ALL = 12;

function TemplateCard({ tp, kind, lang, selected, onPick, onRemove, big = false }) {
  const t = useT();
  return (
    <div className={`group relative ${big ? "" : "w-44 shrink-0 snap-start sm:w-52"}`}>
      <button onClick={() => onPick(tp)} title={tp.desc}
        className={`block w-full overflow-hidden rounded-2xl border bg-hover/60 transition hover:border-accent ${selected === tp.id ? "border-accent ring-2 ring-accent/25" : "border-line"}`}>
        <div className={`relative overflow-hidden ${big ? "h-44 sm:h-48" : "h-28 sm:h-32"}`}>
          <iframe title={tp.name} src={`/api/doc-templates/${tp.id}/preview?kind=${kind}&lang=${lang}`} loading="lazy" tabIndex={-1}
            className="pointer-events-none absolute left-0 top-0 h-[200%] w-[200%] origin-top-left scale-50 border-0" />
        </div>
      </button>
      <div className={`mt-1.5 truncate text-center ${big ? "text-[13.5px] font-medium" : "text-[12.5px]"}`}>{tp.name}</div>
      {big && <div className="truncate text-center text-[11.5px] text-subtle">{tp.desc}</div>}
      {tp.user && (
        <button onClick={() => onRemove(tp)} title={t("delete")} className="absolute right-1.5 top-1.5 hidden rounded-md bg-elev/90 p-1 text-subtle shadow hover:text-danger group-hover:block"><Trash2 size={12} /></button>
      )}
    </div>
  );
}

export function TemplateGallery({ kind, selected, onPick, onCreate, onClose }) {
  const t = useT();
  const lang = useStore((s) => s.prefs?.lang) || "tr";
  const [list, setList] = useState(null);
  const [ends, setEnds] = useState({ left: true, right: false });
  const [all, setAll] = useState(false);
  const strip = useRef(null);
  const load = () => api.get(`/api/doc-templates?kind=${kind}&lang=${lang}`).then((r) => setList(r.templates || [])).catch(() => setList([]));
  useEffect(() => { setList(null); load(); }, [kind, lang]);
  const measure = () => {
    const el = strip.current;
    if (!el) return;
    setEnds({ left: el.scrollLeft <= 2, right: el.scrollLeft + el.clientWidth >= el.scrollWidth - 2 });
  };
  useEffect(() => { measure(); }, [list]);
  useEffect(() => { addEventListener("resize", measure); return () => removeEventListener("resize", measure); }, []);
  const scroll = (d) => strip.current?.scrollBy({ left: d * strip.current.clientWidth * 0.8, behavior: "smooth" });
  const remove = async (tp) => {
    if (!(await useStore.getState().confirm({ title: t("delete"), message: t("tpl_delete_q", { name: tp.name }), confirmLabel: t("delete"), danger: true }))) return;
    await api.del(`/api/doc-templates/${tp.id}`);
    load();
  };
  const arrow = (off) => `grid h-7 w-7 place-items-center rounded-full ${off ? "cursor-default text-subtle/40" : "text-muted hover:bg-hover"}`;
  const more = list && list.length > STRIP;
  return (
    <div className="fade-in mb-2 rounded-2xl border border-line bg-elev p-3 shadow-[0_2px_12px_rgb(0_0_0/0.06)]">
      <div className="mb-2 flex items-center gap-2">
        <span className="text-[13px] font-medium">{t("tpl_title")}</span>
        <div className="flex-1" />
        <button onClick={onCreate} className="rounded-full border border-line px-3 py-1 text-[12px] font-medium hover:bg-hover">{t("tpl_create")}</button>
        <button onClick={() => !ends.left && scroll(-1)} disabled={ends.left} aria-disabled={ends.left} className={arrow(ends.left)}><ChevronLeft size={16} /></button>
        <button onClick={() => !ends.right && scroll(1)} disabled={ends.right} aria-disabled={ends.right} className={arrow(ends.right)}><ChevronRight size={16} /></button>
        <button onClick={onClose} className="grid h-7 w-7 place-items-center rounded-full text-muted hover:bg-hover"><X size={15} /></button>
      </div>
      <div ref={strip} onScroll={measure} className="flex snap-x gap-3 overflow-x-auto pb-1 [scrollbar-width:none]">
        {!list && <div className="grid h-32 w-full place-items-center text-muted"><Loader2 size={18} className="animate-spin" /></div>}
        {list?.slice(0, STRIP).map((tp) => <TemplateCard key={tp.id} tp={tp} kind={kind} lang={lang} selected={selected} onPick={onPick} onRemove={remove} />)}
        {more && (
          <div className="w-32 shrink-0 snap-start sm:w-40">
            <button onClick={() => setAll(true)} className="grid h-28 w-full place-items-center rounded-2xl border border-line bg-hover/60 text-muted transition hover:border-accent hover:text-accent sm:h-32">
              <span className="flex flex-col items-center gap-1.5"><LayoutGrid size={22} /><span className="text-[12.5px] font-medium">{t("tpl_view_all")}</span></span>
            </button>
            <div className="mt-1.5 text-center text-[12px] text-subtle">{list.length}</div>
          </div>
        )}
      </div>
      {all && <AllTemplates list={list} kind={kind} lang={lang} selected={selected} onRemove={remove}
        onPick={(tp) => { setAll(false); onPick(tp); }} onClose={() => setAll(false)} />}
    </div>
  );
}

// Every template of a format in a dialog: a grid that shows more while you scroll down
function AllTemplates({ list, kind, lang, selected, onPick, onRemove, onClose }) {
  const t = useT();
  const [n, setN] = useState(PAGE_ALL);
  const sentinel = useRef(null);
  useEffect(() => {
    const el = sentinel.current;
    if (!el) return undefined;
    const io = new IntersectionObserver((es) => { if (es.some((e) => e.isIntersecting)) setN((v) => Math.min(list.length, v + PAGE_ALL)); }, { rootMargin: "240px" });
    io.observe(el);
    return () => io.disconnect();
  }, [list.length, n]);
  return (
    <Modal title={t("tpl_title")} onClose={onClose} width="max-w-5xl">
      <div className="grid max-h-[72vh] grid-cols-2 gap-4 overflow-y-auto pr-1 sm:grid-cols-3">
        {list.slice(0, n).map((tp) => <TemplateCard key={tp.id} big tp={tp} kind={kind} lang={lang} selected={selected} onPick={onPick} onRemove={onRemove} />)}
        {n < list.length && <div ref={sentinel} className="col-span-full grid h-16 place-items-center text-muted"><Loader2 size={18} className="animate-spin" /></div>}
      </div>
    </Modal>
  );
}

// Image to video: the pictures of the chat's folder and the ones attached to the message, or a new upload
export function ImagePicker({ onPick, onClose }) {
  const t = useT();
  const st = useStore.getState();
  const attachments = useStore((s) => s.attachments);
  const [files, setFiles] = useState(null);
  const input = useRef(null);
  useEffect(() => {
    const walk = async (dir, depth, out) => {
      if (depth > 2 || out.length > 120) return;
      const r = await api.get(st.fileApi(`/fs/list?path=${encodeURIComponent(dir)}`)).catch(() => ({ items: [] }));
      for (const e of r.items || []) {
        if (e.dir && !/^(\.|node_modules|\.cache|\.session)/.test(e.name)) await walk(e.path, depth + 1, out);
        else if (!e.dir && isImage(e.name)) out.push(e);
      }
    };
    (async () => {
      if (!useStore.getState().sessionId) return setFiles([]);
      const out = [];
      await walk("", 0, out);
      setFiles(out.sort((a, b) => (b.mtime || 0) - (a.mtime || 0)));
    })();
  }, []);
  const attached = attachments.filter((a) => a.kind === "image");
  const raw = (p) => st.fileApi(`/fs/raw?path=${encodeURIComponent(p)}`);
  const upload = async (list) => {
    if (!list.length) return;
    await st.addAttachments(list);
    onPick({ name: list[0].name, attached: true });
  };
  return (
    <Modal title={<span className="flex items-center gap-2"><ImageIcon size={17} className="text-fuchsia-500" />{t("img2video_pick_title")}</span>} onClose={onClose} width="max-w-3xl">
      <div className="space-y-3">
        <p className="text-xs text-muted">{t("img2video_pick_desc")}</p>
        <button onClick={() => input.current.click()} className="flex w-full items-center justify-center gap-2 rounded-xl border border-dashed border-line py-3 text-[13px] hover:bg-hover">
          <Upload size={15} />{t("img2video_upload")}</button>
        <input ref={input} type="file" accept="image/*" hidden onChange={(e) => { const l = [...e.target.files]; e.target.value = ""; upload(l); }} />
        {attached.length > 0 && (
          <Section title={t("img2video_attached")}>
            {attached.map((a) => (
              <Thumb key={a.name} src={a.b64 ? `data:${a.mime || "image/png"};base64,${a.b64}` : ""} name={a.name} onClick={() => onPick({ name: a.name, attached: true })} />
            ))}
          </Section>
        )}
        <Section title={<span className="flex items-center gap-1.5"><FolderOpen size={13} />{t("img2video_folder")}</span>}>
          {!files && <div className="col-span-full grid h-20 place-items-center text-muted"><Loader2 size={16} className="animate-spin" /></div>}
          {files?.length === 0 && <div className="col-span-full py-4 text-center text-[12.5px] text-muted">{t("img2video_none")}</div>}
          {files?.map((f) => <Thumb key={f.path} src={raw(f.path)} name={f.path} onClick={() => onPick({ path: f.path, name: f.path })} />)}
        </Section>
      </div>
    </Modal>
  );
}

const Section = ({ title, children }) => (
  <div>
    <div className="mb-1.5 text-[11.5px] font-semibold uppercase tracking-wide text-subtle">{title}</div>
    <div className="grid grid-cols-3 gap-2 sm:grid-cols-5">{children}</div>
  </div>
);
const Thumb = ({ src, name, onClick }) => (
  <button onClick={onClick} title={name} className="group overflow-hidden rounded-xl border border-line bg-hover text-left transition hover:border-accent">
    <div className="aspect-square overflow-hidden bg-[conic-gradient(#8881_25%,transparent_0_50%,#8881_0_75%,transparent_0)] bg-[length:14px_14px]">
      {src && <img src={src} alt="" loading="lazy" className="h-full w-full object-cover transition group-hover:scale-105" />}
    </div>
    <div className="truncate px-1.5 py-1 text-[10.5px] text-muted">{name.split("/").pop()}</div>
  </button>
);
