import { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ChevronRight, Download, FilePlus2, Folder, FolderOpen, FolderPlus, HardDrive, History, LayoutGrid, List, Loader2,
  PanelLeft, Pencil, RefreshCw, Search, SquareArrowOutUpRight, Trash2, Upload, X,
  Maximize2,
} from "lucide-react";
import { useStore, useT } from "../lib/store";
import { api } from "../lib/api";
import { CATEGORIES, docKind, fileCategory, fileType, formatSize, isTextFile } from "../lib/fileTypes";
import { DocBody } from "./DocPreview";
import { ContextMenu, MenuItem, MenuSep, Modal } from "./ui";
import CodeBlock from "./CodeBlock";

const fmtDate = (s) => new Date(s * 1000).toLocaleString([], { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });

function Icon({ item, size = 16 }) {
  if (item.dir) return <Folder size={size} className="shrink-0 text-accent" fill="currentColor" fillOpacity={0.15} />;
  const ft = fileType(item.name);
  const I = ft.icon;
  return <I size={size} className="shrink-0" style={{ color: ft.color }} />;
}

// Left tree: folders only, children loaded lazily on expand.
const TreeNode = memo(function TreeNode({ path, name, depth, cwd, open, toggle, go, kids, onMenu }) {
  const isOpen = open.has(path);
  const children = kids[path];
  return (
    <div>
      <div onClick={() => go(path)} onContextMenu={(e) => onMenu(e, { path, name, dir: true, root: depth === 0 })} style={{ paddingLeft: 8 + depth * 14 }}
        className={`group flex h-7 cursor-pointer items-center gap-1 rounded-lg pr-2 text-[13px] ${cwd === path ? "bg-active font-medium" : "hover:bg-hover"}`}>
        <button onClick={(e) => { e.stopPropagation(); toggle(path); }} className="rounded p-0.5 text-subtle hover:text-fg">
          <ChevronRight size={13} className={`transition ${isOpen ? "rotate-90" : ""}`} />
        </button>
        {depth === 0 ? <HardDrive size={15} className="shrink-0 text-muted" /> : isOpen ? <FolderOpen size={15} className="shrink-0 text-accent" /> : <Folder size={15} className="shrink-0 text-accent" />}
        <span className="truncate">{name}</span>
      </div>
      {isOpen && (children ? children.map((c) => (
        <TreeNode key={c.path} path={c.path} name={c.name} depth={depth + 1} cwd={cwd} open={open} toggle={toggle} go={go} kids={kids} onMenu={onMenu} />
      )) : <div style={{ paddingLeft: 30 + depth * 14 }} className="py-1"><Loader2 size={12} className="animate-spin text-subtle" /></div>)}
    </div>
  );
});

function Preview({ item, onClose }) {
  const t = useT();
  const st = useStore.getState();
  const [text, setText] = useState(null);
  const cat = fileCategory(item.name);
  const raw = st.fileApi(`/fs/raw?path=${encodeURIComponent(item.path)}`);
  useEffect(() => {
    setText(null);
    if (isTextFile(item.name) && item.size < 400_000) {
      api.get(st.fileApi(`/file?path=${encodeURIComponent(item.path)}`)).then((r) => setText(r.content)).catch(() => setText(""));
    }
  }, [item.path, item.mtime]);
  return (
    <aside className="flex min-h-0 w-full max-w-md flex-col border-l border-line bg-panel lg:w-[380px]">
      <div className="flex items-center gap-2 border-b border-line px-4 py-3">
        <Icon item={item} size={18} />
        <span className="min-w-0 flex-1 truncate text-[13px] font-semibold">{item.name}</span>
        <button onClick={onClose} className="rounded-lg p-1 text-subtle hover:bg-hover"><X size={16} /></button>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto p-4">
        {cat === "image" && <img src={raw} alt={item.name} className="mx-auto max-h-72 rounded-xl border border-line bg-bg object-contain" />}
        {docKind(item.name) && <div className="h-80"><DocBody key={`${item.path}:${item.mtime}`} path={item.path} /></div>}
        {text != null && text !== "" && <CodeBlock code={text.length > 60000 ? text.slice(0, 60000) + "\n…" : text} language={item.ext} path={item.path} />}
        {text === "" && <div className="text-xs text-subtle">{t("empty_file")}</div>}
        <dl className="mt-4 grid grid-cols-[90px_1fr] gap-y-1.5 text-xs">
          <dt className="text-subtle">{t("type")}</dt><dd>{fileType(item.name).label} · {t(`cat_${cat}`)}</dd>
          <dt className="text-subtle">{t("size")}</dt><dd>{formatSize(item.size)}</dd>
          <dt className="text-subtle">{t("modified")}</dt><dd>{fmtDate(item.mtime)}</dd>
          <dt className="text-subtle">{t("path")}</dt><dd className="break-all font-mono">{item.path}</dd>
        </dl>
      </div>
      <div className="flex gap-2 border-t border-line p-3">
        {docKind(item.name) && <button onClick={() => st.previewFile(item.path, item.size)} className="flex flex-1 items-center justify-center gap-1.5 rounded-xl bg-accent py-2 text-[13px] font-medium text-accent-fg"><Maximize2 size={14} /> {t("preview")}</button>}
        {isTextFile(item.name) && <button onClick={() => st.openFile(item.path)} className="flex flex-1 items-center justify-center gap-1.5 rounded-xl bg-accent py-2 text-[13px] font-medium text-accent-fg"><SquareArrowOutUpRight size={14} /> {t("open_editor")}</button>}
        <a href={raw + "&download=true"} className="flex flex-1 items-center justify-center gap-1.5 rounded-xl border border-line py-2 text-[13px] font-medium hover:bg-hover"><Download size={14} /> {t("download")}</a>
      </div>
    </aside>
  );
}

// Full file manager over the chat's working folder (project folder, or workspace/ for chats without a project).
export default function FilesView() {
  const t = useT();
  const scopeKey = useStore((x) => `${x.sessionId}|${x.projectId}|${x.scope}`);
  const fsTick = useStore((x) => x.fsTick);
  const st = useStore.getState();
  const [cwd, setCwd] = useState("");
  const [data, setData] = useState({ root: "", items: [] });
  const [kids, setKids] = useState({});
  const [open, setOpen] = useState(new Set([""]));
  const [q, setQ] = useState("");
  const [cat, setCat] = useState("all");
  const [view, setView] = useState("list");
  const [sel, setSel] = useState(null);
  const [menu, setMenu] = useState(null);
  const [rename, setRename] = useState(null);
  const [create, setCreate] = useState(null); // "mkdir" | "newfile"
  const [name, setName] = useState("");
  const [tree, setTree] = useState(true);
  const [hist, setHist] = useState(null);
  const [drag, setDrag] = useState(false);
  const [loading, setLoading] = useState(false);
  const fileRef = useRef(null);

  const list = useCallback((path) => api.get(st.fileApi(`/fs/list?path=${encodeURIComponent(path)}`)), [scopeKey]);
  const load = useCallback(async (path, quiet = false) => {
    if (!quiet) setLoading(true);
    try {
      const r = await list(path);
      setData(r);
      setKids((k) => ({ ...k, [path]: r.items.filter((i) => i.dir) }));
      setSel((s) => (s ? r.items.find((i) => i.path === s.path) || null : null));
    } catch (e) { if (!quiet) st.notify(t("load_failed"), "error", e.message); }
    setLoading(false);
  }, [list]);

  useEffect(() => { setCwd(""); setKids({}); setOpen(new Set([""])); setSel(null); }, [scopeKey]);
  useEffect(() => { load(cwd); }, [cwd, load]);
  useEffect(() => { if (fsTick) load(cwd, true); }, [fsTick]); // an agent changed files: refresh at once
  useEffect(() => { // live view while visible
    const i = setInterval(() => !document.hidden && load(cwd, true), 4000);
    return () => clearInterval(i);
  }, [cwd, load]);

  const toggle = useCallback(async (path) => {
    setOpen((o) => { const n = new Set(o); n.has(path) ? n.delete(path) : n.add(path); return n; });
    try { const r = await list(path); setKids((k) => ({ ...k, [path]: r.items.filter((i) => i.dir) })); } catch {}
  }, [list]);
  const go = useCallback((path) => {
    setCwd(path); setSel(null);
    const parts = path.split("/").filter(Boolean);
    setOpen((o) => new Set([...o, "", ...parts.map((_, i) => parts.slice(0, i + 1).join("/"))]));
  }, []);

  const items = useMemo(() => data.items.filter((i) =>
    (!q || i.name.toLowerCase().includes(q.toLowerCase())) && (cat === "all" || (!i.dir && fileCategory(i.name) === cat))), [data.items, q, cat]);
  const counts = useMemo(() => {
    const c = {};
    for (const i of data.items) if (!i.dir) c[fileCategory(i.name)] = (c[fileCategory(i.name)] || 0) + 1;
    return c;
  }, [data.items]);

  const op = async (body, okText) => {
    try { await api.post(st.fileApi("/fs/op"), body); st.notify(okText, "ok"); load(cwd, true); return true; }
    catch (e) { st.notify(t("op_failed"), "error", e.message); return false; }
  };
  const startCreate = (kind, folder = cwd) => { if (folder !== cwd) go(folder); setCreate(kind); setName(""); };
  const doCreate = async () => {
    if (!name.trim()) return setCreate(null);
    if (await op({ op: create, path: cwd, name: name.trim() }, t(create === "mkdir" ? "folder_created" : "file_created", { name: name.trim() }))) { setCreate(null); setName(""); }
  };
  const doRename = async () => {
    const it = rename; setRename(null);
    if (it && name.trim() && name.trim() !== it.name) await op({ op: "rename", path: it.path, name: name.trim() }, t("renamed", { name: name.trim() }));
  };
  const doDelete = async (it) => {
    if (!(await st.confirm({ title: t("delete"), message: t(it.dir ? "confirm_delete_folder" : "confirm_delete_item", { name: it.name }), confirmLabel: t("delete"), danger: true }))) return;
    if (await op({ op: "delete", path: it.path }, t("deleted", { name: it.name })) && sel?.path === it.path) setSel(null);
  };
  const upload = async (files) => {
    let ok = 0;
    for (const f of files) {
      try { await api.upload(st.fileApi(`/fs/upload?path=${encodeURIComponent(cwd)}`), f); ok++; }
      catch (e) { st.notify(t("upload_failed", { name: f.name }), "error", e.message); }
    }
    if (ok) st.notify(t("uploaded", { n: ok }), "ok");
    load(cwd, true);
  };
  const openItem = (it) => (it.dir ? go(it.path) : setSel(it));
  const showHistory = async () => {
    try { setHist(await api.get(st.fileApi("/history"))); } catch { setHist([]); }
  };
  const rollback = async (sha) => {
    if (!(await st.confirm({ title: t("rollback"), message: t("confirm_rollback", { sha }), confirmLabel: t("rollback") }))) return;
    try { await api.post(st.fileApi(`/rollback/${sha}`)); st.notify(t("rolled_back", { sha }), "ok"); load(cwd); showHistory(); }
    catch (e) { st.notify(t("rollback_failed"), "error", e.message); }
  };

  const crumbs = cwd ? cwd.split("/") : [];
  const rootName = data.root.split(/[\\/]/).filter(Boolean).pop() || "workspace";
  const btn = "flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-[13px] hover:bg-hover";
  const ctx = useCallback((e, it) => { e.preventDefault(); e.stopPropagation(); setMenu({ x: e.clientX, y: e.clientY, it }); }, []);

  return (
    <div className="flex min-h-0 flex-1">
      {tree && (
        <div className="hidden w-60 shrink-0 flex-col border-r border-line bg-panel md:flex">
          <div className="px-3 pb-1 pt-3 text-[11px] font-semibold uppercase tracking-wider text-subtle">{t("folders")}</div>
          <div className="min-h-0 flex-1 overflow-y-auto px-1.5 pb-3">
            <TreeNode path="" name={rootName} depth={0} cwd={cwd} open={open} toggle={toggle} go={go} kids={kids} onMenu={ctx} />
          </div>
        </div>
      )}
      <div className="flex min-w-0 flex-1 flex-col"
        onDragOver={(e) => { e.preventDefault(); setDrag(true); }} onDragLeave={() => setDrag(false)}
        onDrop={(e) => { e.preventDefault(); setDrag(false); upload([...e.dataTransfer.files]); }}>
        <div className="flex flex-wrap items-center gap-1 border-b border-line px-3 py-2">
          <button onClick={() => setTree(!tree)} className="hidden rounded-lg p-1.5 text-muted hover:bg-hover md:block"><PanelLeft size={16} /></button>
          <nav className="flex min-w-[140px] flex-1 items-center gap-0.5 overflow-x-auto text-[13px]">
            <button onClick={() => go("")} className="shrink-0 rounded-md px-1.5 py-0.5 font-medium hover:bg-hover">{rootName}</button>
            {crumbs.map((c, i) => (
              <span key={i} className="flex shrink-0 items-center gap-0.5">
                <ChevronRight size={13} className="text-subtle" />
                <button onClick={() => go(crumbs.slice(0, i + 1).join("/"))} className="rounded-md px-1.5 py-0.5 hover:bg-hover">{c}</button>
              </span>
            ))}
          </nav>
          <button className={btn} onClick={() => startCreate("newfile")}><FilePlus2 size={15} /><span className="hidden lg:inline">{t("new_file")}</span></button>
          <button className={btn} onClick={() => startCreate("mkdir")}><FolderPlus size={15} /><span className="hidden lg:inline">{t("new_folder")}</span></button>
          <button className={btn} onClick={() => fileRef.current.click()}><Upload size={15} /><span className="hidden lg:inline">{t("upload")}</span></button>
          <button className={btn} onClick={showHistory} title={t("history")}><History size={15} /></button>
          <button className={btn} onClick={() => load(cwd)} title={t("refresh")}><RefreshCw size={15} className={loading ? "animate-spin" : ""} /></button>
          <input ref={fileRef} type="file" multiple hidden onChange={(e) => { upload([...e.target.files]); e.target.value = ""; }} />
        </div>
        <div className="flex flex-wrap items-center gap-2 border-b border-line px-3 py-2">
          <div className="relative w-full sm:w-56">
            <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-subtle" />
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("search_files")}
              className="w-full rounded-lg border border-line bg-bg py-1.5 pl-8 pr-2 text-[13px] outline-none focus:border-accent" />
          </div>
          <div className="flex flex-1 gap-1 overflow-x-auto">
            {["all", ...CATEGORIES].filter((c) => c === "all" || counts[c]).map((c) => (
              <button key={c} onClick={() => setCat(c)}
                className={`shrink-0 rounded-full px-2.5 py-1 text-xs ${cat === c ? "bg-accent text-accent-fg" : "bg-hover text-muted hover:text-fg"}`}>
                {t(c === "all" ? "all" : `cat_${c}`)}{c !== "all" && <span className="ml-1 opacity-70">{counts[c]}</span>}
              </button>
            ))}
          </div>
          <div className="flex rounded-lg bg-hover p-0.5">
            <button onClick={() => setView("list")} className={`rounded-md p-1 ${view === "list" ? "bg-elev shadow-sm" : "text-muted"}`}><List size={15} /></button>
            <button onClick={() => setView("grid")} className={`rounded-md p-1 ${view === "grid" ? "bg-elev shadow-sm" : "text-muted"}`}><LayoutGrid size={15} /></button>
          </div>
        </div>

        <div className={`relative min-h-0 flex-1 overflow-y-auto ${drag ? "bg-accent-soft" : ""}`} onClick={() => setSel(null)}
          onContextMenu={(e) => ctx(e, null)}>
          {create && (
            <div className="flex items-center gap-2 border-b border-line bg-panel px-4 py-2" onClick={(e) => e.stopPropagation()}>
              {create === "mkdir" ? <FolderPlus size={15} className="text-accent" /> : <FilePlus2 size={15} className="text-accent" />}
              <input autoFocus value={name} onChange={(e) => setName(e.target.value)} placeholder={t(create === "mkdir" ? "folder_name_ph" : "file_name_ph")}
                onKeyDown={(e) => { if (e.key === "Enter") doCreate(); if (e.key === "Escape") setCreate(null); }}
                className="min-w-0 flex-1 rounded-lg border border-line bg-bg px-2 py-1 text-[13px] outline-none focus:border-accent" />
              <button onClick={doCreate} className="rounded-lg bg-accent px-3 py-1 text-xs font-medium text-accent-fg">{t("create")}</button>
              <button onClick={() => setCreate(null)} className="rounded p-1 text-subtle hover:text-fg"><X size={14} /></button>
            </div>
          )}
          {items.length === 0 && !loading && (
            <div className="flex flex-col items-center justify-center gap-2 py-16 text-center text-[13px] text-subtle">
              <FolderOpen size={36} className="opacity-40" />{q || cat !== "all" ? t("no_results") : t("empty_folder_drop")}
            </div>
          )}
          {view === "list" ? (
            <table className="w-full table-fixed text-[13px]">
              {items.length > 0 && (
                <thead className="sticky top-0 bg-bg text-left text-[11px] uppercase tracking-wider text-subtle">
                  <tr><th className="px-4 py-2 font-medium">{t("name")}</th><th className="hidden w-20 px-2 py-2 font-medium sm:table-cell">{t("type")}</th>
                    <th className="hidden w-20 px-2 py-2 text-right font-medium sm:table-cell">{t("size")}</th><th className={`hidden w-36 px-4 py-2 font-medium ${sel ? "2xl:table-cell" : "md:table-cell"}`}>{t("modified")}</th></tr>
                </thead>
              )}
              <tbody>
                {items.map((it) => (
                  <tr key={it.path} onClick={(e) => { e.stopPropagation(); openItem(it); }} onContextMenu={(e) => ctx(e, it)}
                    className={`cursor-pointer border-b border-line/60 ${sel?.path === it.path ? "bg-accent-soft" : "hover:bg-hover"}`}>
                    <td className="px-4 py-1.5">
                      <div className="flex min-w-0 items-center gap-2.5">
                        <Icon item={it} />
                        {rename?.path === it.path ? (
                          <input autoFocus value={name} onChange={(e) => setName(e.target.value)} onClick={(e) => e.stopPropagation()} onBlur={doRename}
                            onKeyDown={(e) => { if (e.key === "Enter") doRename(); if (e.key === "Escape") setRename(null); }}
                            className="min-w-0 flex-1 rounded border border-accent bg-bg px-1.5 py-0.5 outline-none" />
                        ) : <span className="truncate">{it.name}</span>}
                      </div>
                    </td>
                    <td className="hidden px-2 py-1.5 text-xs text-muted sm:table-cell">{it.dir ? t("folder") : fileType(it.name).label}</td>
                    <td className="hidden px-2 py-1.5 text-right font-mono text-xs text-muted sm:table-cell">{it.dir ? "—" : formatSize(it.size)}</td>
                    <td className={`hidden whitespace-nowrap px-4 py-1.5 text-xs text-muted ${sel ? "2xl:table-cell" : "md:table-cell"}`}>{fmtDate(it.mtime)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <div className="grid grid-cols-[repeat(auto-fill,minmax(120px,1fr))] gap-2 p-3">
              {items.map((it) => (
                <button key={it.path} onClick={(e) => { e.stopPropagation(); openItem(it); }} onContextMenu={(e) => ctx(e, it)}
                  className={`flex flex-col items-center gap-2 rounded-2xl border p-3 text-center ${sel?.path === it.path ? "border-accent bg-accent-soft" : "border-transparent hover:bg-hover"}`}>
                  {!it.dir && fileCategory(it.name) === "image"
                    ? <img src={st.fileApi(`/fs/raw?path=${encodeURIComponent(it.path)}`)} alt="" className="h-14 w-14 rounded-lg object-cover" loading="lazy" />
                    : <Icon item={it} size={38} />}
                  <span className="w-full truncate text-xs">{it.name}</span>
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
      {sel && (
        <div className="fixed inset-0 z-40 flex justify-end lg:static lg:z-auto">
          <div className="flex-1 bg-black/30 lg:hidden" onClick={() => setSel(null)} />
          <Preview item={sel} onClose={() => setSel(null)} />
        </div>
      )}
      {menu && (
        <ContextMenu x={menu.x} y={menu.y} onClose={() => setMenu(null)}>
          {menu.it ? (
            <>
              <MenuItem icon={menu.it.dir ? FolderOpen : SquareArrowOutUpRight} label={t(menu.it.dir ? "open" : "preview")} onClick={() => openItem(menu.it)} />
              {!menu.it.dir && isTextFile(menu.it.name) && <MenuItem icon={SquareArrowOutUpRight} label={t("open_editor")} onClick={() => st.openFile(menu.it.path)} />}
              {menu.it.dir && <MenuItem icon={FilePlus2} label={t("new_file_here")} onClick={() => startCreate("newfile", menu.it.path)} />}
              {menu.it.dir && <MenuItem icon={FolderPlus} label={t("new_folder_here")} onClick={() => startCreate("mkdir", menu.it.path)} />}
              {!menu.it.root && <MenuItem icon={Pencil} label={t("rename")} shortcut="R" onClick={() => {
                if (menu.it.dir && !data.items.some((i) => i.path === menu.it.path)) go(menu.it.path.split("/").slice(0, -1).join("/"));
                setRename(menu.it); setName(menu.it.name);
              }} />}
              {!menu.it.dir && <MenuItem icon={Download} label={t("download")} onClick={() => window.open(st.fileApi(`/fs/raw?path=${encodeURIComponent(menu.it.path)}`) + "&download=true")} />}
              {!menu.it.root && <><MenuSep /><MenuItem icon={Trash2} label={t("delete")} danger shortcut="D" onClick={() => doDelete(menu.it)} /></>}
            </>
          ) : (
            <>
              <MenuItem icon={FilePlus2} label={t("new_file")} onClick={() => startCreate("newfile")} />
              <MenuItem icon={FolderPlus} label={t("new_folder")} onClick={() => startCreate("mkdir")} />
              <MenuItem icon={Upload} label={t("upload")} onClick={() => fileRef.current.click()} />
              <MenuSep />
              <MenuItem icon={RefreshCw} label={t("refresh")} onClick={() => load(cwd)} />
            </>
          )}
        </ContextMenu>
      )}
      {hist && (
        <Modal title={t("history")} onClose={() => setHist(null)}>
          {hist.length === 0 && <div className="py-6 text-center text-[13px] text-subtle">{t("no_history")}</div>}
          <div className="space-y-1.5">
            {hist.map((h) => (
              <div key={h.sha} className="flex items-center gap-3 rounded-xl border border-line px-3 py-2 text-xs">
                <span className="font-mono text-muted">{h.sha}</span>
                <span className="min-w-0 flex-1 truncate">{h.message}</span>
                <span className="hidden text-subtle sm:inline">{fmtDate(+h.ts)}</span>
                <button onClick={() => rollback(h.sha)} className="rounded-lg px-2 py-1 font-medium text-accent hover:bg-hover">{t("rollback")}</button>
              </div>
            ))}
          </div>
        </Modal>
      )}
    </div>
  );
}
