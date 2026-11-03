import { useEffect, useState } from "react";
import { ArrowUp, Check, Folder, FolderPlus, HardDrive, Home, Loader2, Plus, X } from "lucide-react";
import { useStore, useT } from "../lib/store";
import { api } from "../lib/api";
import { Button, Modal, inputCls } from "./ui";

// Local folder browser backed by /api/fs/dirs (the browser cannot expose real paths itself).
function FolderBrowser({ onPick, onCancel }) {
  const t = useT();
  const [data, setData] = useState(null);
  const [err, setErr] = useState("");
  const [newName, setNewName] = useState(null);
  const mkdir = async () => {
    const name = (newName || "").trim();
    if (!name) return setNewName(null);
    try {
      const r = await api.post("/api/fs/mkdir", { parent: data.path, name });
      setNewName(null);
      useStore.getState().notify(t("folder_created", { name }), "ok");
      go(r.path);
    } catch (e) { setErr(e.message); }
  };
  const go = (path) => api.get(`/api/fs/dirs?path=${encodeURIComponent(path ?? "")}`).then((d) => { setData(d); setErr(""); }).catch((e) => setErr(e.message));
  useEffect(() => { go(null); }, []);
  if (!data) return <div className="flex justify-center py-6"><Loader2 className="animate-spin text-subtle" /></div>;
  return (
    <div className="overflow-hidden rounded-2xl border border-line">
      <div className="flex items-center gap-1 border-b border-line bg-panel px-2 py-1.5">
        <button disabled={data.parent == null} onClick={() => go(data.parent)} className="rounded-lg p-1.5 hover:bg-hover disabled:opacity-30"><ArrowUp size={15} /></button>
        <button onClick={() => go(data.home)} className="rounded-lg p-1.5 hover:bg-hover"><Home size={15} /></button>
        <div className="min-w-0 flex-1 truncate px-1 font-mono text-xs text-muted" title={data.path}>{data.path || t("this_computer")}</div>
        {data.path && newName == null && (
          <button onClick={() => setNewName("")} className="flex items-center gap-1 rounded-lg px-2 py-1 text-xs font-medium hover:bg-hover">
            <FolderPlus size={14} /> {t("new_folder")}
          </button>
        )}
      </div>
      {newName != null && (
        <div className="flex items-center gap-2 border-b border-line px-2 py-1.5">
          <FolderPlus size={15} className="shrink-0 text-accent" />
          <input autoFocus value={newName} onChange={(e) => setNewName(e.target.value)} placeholder={t("folder_name_ph")}
            onKeyDown={(e) => { if (e.key === "Enter") mkdir(); if (e.key === "Escape") setNewName(null); }}
            className="min-w-0 flex-1 rounded-lg border border-line bg-bg px-2 py-1 text-[13px] outline-none focus:border-accent" />
          <Button variant="primary" className="!px-2.5 !py-1" onClick={mkdir}>{t("create")}</Button>
          <button onClick={() => setNewName(null)} className="rounded p-1 text-subtle hover:text-fg"><X size={14} /></button>
        </div>
      )}
      <div className="max-h-56 overflow-y-auto p-1">
        {data.dirs.length === 0 && <div className="px-3 py-4 text-center text-xs text-subtle">{t("empty_folder")}</div>}
        {data.dirs.map((d) => (
          <button key={d.path} onDoubleClick={() => go(d.path)} onClick={() => go(d.path)}
            className="flex w-full items-center gap-2 rounded-lg px-2.5 py-1.5 text-left text-[13px] hover:bg-hover">
            {data.path ? <Folder size={15} className="text-accent" /> : <HardDrive size={15} className="text-muted" />}
            <span className="truncate">{d.name}</span>
          </button>
        ))}
      </div>
      {err && <div className="px-3 pb-2 text-xs text-danger">{err}</div>}
      <div className="flex items-center justify-end gap-2 border-t border-line bg-panel px-2 py-1.5">
        <Button variant="ghost" onClick={onCancel}>{t("cancel")}</Button>
        <Button variant="primary" disabled={!data.path} onClick={() => onPick(data.path)}><Check size={14} /> {t("select_this_folder")}</Button>
      </div>
    </div>
  );
}

export default function ProjectDialog() {
  const t = useT();
  const [name, setName] = useState("");
  const [path, setPath] = useState("");
  const [browsing, setBrowsing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const close = () => useStore.setState({ dialog: null });
  const create = async () => {
    setBusy(true);
    try { await useStore.getState().createProject(name.trim(), path || null); close(); }
    catch (e) { setErr(e.message); }
    finally { setBusy(false); }
  };
  const pick = (p) => { setPath(p); setBrowsing(false); if (!name) setName(p.split(/[\\/]/).filter(Boolean).pop() || ""); };

  return (
    <Modal title={t("new_project")} onClose={close}
      footer={<>
        <Button variant="ghost" onClick={close}>{t("cancel")}</Button>
        <Button variant="primary" disabled={!name.trim() || busy} onClick={create}>{busy && <Loader2 size={14} className="animate-spin" />}{t("create_project")}</Button>
      </>}>
      <div className="mb-4 inline-flex rounded-xl bg-hover p-1 text-[13px]">
        <span className="rounded-lg bg-elev px-3 py-1 font-medium shadow-sm">{t("local")}</span>
      </div>
      <label className="mb-1.5 block text-[13px] font-semibold">{t("name")}</label>
      <input autoFocus className={inputCls} value={name} placeholder={t("project_name_ph")}
        onChange={(e) => setName(e.target.value)} onKeyDown={(e) => e.key === "Enter" && name.trim() && create()} />

      <div className="mb-1.5 mt-5 flex items-center justify-between">
        <label className="text-[13px] font-semibold">{t("folders")} <span className="font-normal text-subtle">({t("optional")})</span></label>
        {!browsing && <Button onClick={() => setBrowsing(true)}><Plus size={14} /> {t("add")}</Button>}
      </div>
      {browsing ? <FolderBrowser onPick={pick} onCancel={() => setBrowsing(false)} />
        : path ? (
          <div className="flex items-center gap-2 rounded-2xl border border-line px-3 py-2.5">
            <Folder size={16} className="shrink-0 text-accent" />
            <span className="min-w-0 flex-1 truncate font-mono text-xs">{path}</span>
            <button onClick={() => setPath("")} className="rounded p-0.5 text-subtle hover:text-fg"><X size={14} /></button>
          </div>
        ) : (
          <button onClick={() => setBrowsing(true)} className="w-full rounded-2xl border border-dashed border-line px-4 py-4 text-left text-[13px] text-subtle hover:bg-hover">
            {t("pick_folder_hint")}
          </button>
        )}
      {err && <div className="mt-3 rounded-xl bg-danger/10 px-3 py-2 text-xs text-danger">{err}</div>}
    </Modal>
  );
}
