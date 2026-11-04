import { useEffect, useRef, useState } from "react";
import Editor from "@monaco-editor/react";
import { Bot, Download, FileUp, Link2, Loader2, Lock, Pencil, Plus, Sparkles, Terminal, Trash2 } from "lucide-react";
import { loc, useStore, useT } from "../lib/store";
import { api } from "../lib/api";
import { Button, Modal, inputCls } from "./ui";

function EditorModal({ kind, name, isNew, onClose, onSaved }) {
  const t = useT();
  const dark = useStore((s) => s.dark);
  const [content, setContent] = useState(null);
  const [newName, setNewName] = useState(isNew ? "" : name);
  const [err, setErr] = useState("");
  useEffect(() => {
    api.get(`/api/catalog/${kind}/${isNew ? "new-item" : name}`).then((r) => setContent(isNew ? r.content.replace(/new-item/g, "my-item") : r.content));
  }, []);
  const save = async () => {
    try {
      const n = newName.trim().toLowerCase();
      await api.put(`/api/catalog/${kind}/${n}`, { content });
      onSaved(); onClose();
      useStore.getState().notify(t("saved"), "ok");
    } catch (e) { setErr(e.message); }
  };
  return (
    <Modal title={isNew ? t(kind === "skills" ? "new_skill" : "new_agent") : `${kind === "skills" ? "/" : "@"}${name}`} onClose={onClose} width="max-w-4xl"
      footer={<><Button variant="ghost" onClick={onClose}>{t("cancel")}</Button><Button variant="primary" disabled={!newName.trim() || content == null} onClick={save}>{t("save")}</Button></>}>
      {isNew && (
        <input autoFocus className={`${inputCls} mb-3 font-mono`} placeholder={t("item_name_ph")} value={newName}
          onChange={(e) => setNewName(e.target.value.toLowerCase().replace(/[^a-z0-9_-]/g, ""))} />
      )}
      <div className="h-[55vh] overflow-hidden rounded-2xl border border-line">
        {content == null ? <div className="grid h-full place-items-center"><Loader2 className="animate-spin text-subtle" /></div> : (
          <Editor language="markdown" value={content} onChange={(v) => setContent(v ?? "")} theme={dark ? "vs-dark" : "vs"}
            options={{ fontSize: 13, minimap: { enabled: false }, wordWrap: "on", automaticLayout: true, scrollBeyondLastLine: false, padding: { top: 10 } }} />
        )}
      </div>
      {err && <div className="mt-3 rounded-xl bg-danger/10 px-3 py-2 text-xs text-danger">{err}</div>}
    </Modal>
  );
}

// Skills (/name) and agents (@name): list, create, edit with Monaco, delete, import from file or GitHub URL.
export default function CatalogView() {
  const t = useT();
  const view = useStore((s) => s.view);
  const kind = view === "agents" ? "agents" : "skills";
  const [items, setItems] = useState([]);
  const [edit, setEdit] = useState(null);
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const setMsg = (m) => m && useStore.getState().notify(m.ok || t("import_failed"), m.ok ? "ok" : "error", m.error);
  const fileRef = useRef(null);
  const load = () => api.get(`/api/${kind}`).then(setItems).catch(() => setItems([]));
  const refresh = () => { load(); useStore.getState().loadCatalog(); };
  useEffect(() => { load(); }, [kind]);
  const Icon = kind === "skills" ? Sparkles : Bot;
  const prefix = kind === "skills" ? "/" : "@";

  const importUrl = async (e) => {
    e.preventDefault();
    setBusy(true); setMsg(null);
    try { const r = await api.post(`/api/catalog/${kind}/import`, { url }); setUrl(""); setMsg({ ok: t("imported", { name: prefix + r.name }) }); refresh(); }
    catch (x) { setMsg({ error: x.message }); }
    setBusy(false);
  };
  const upload = async (files) => {
    for (const f of files) {
      try { const r = await api.upload(`/api/catalog/${kind}/upload`, f); setMsg({ ok: t("imported", { name: prefix + r.name }) }); }
      catch (x) { setMsg({ error: x.message }); }
    }
    refresh();
  };
  const remove = async (name) => {
    const st = useStore.getState();
    if (!(await st.confirm({ title: t("delete"), message: t("confirm_delete_item", { name: prefix + name }), confirmLabel: t("delete"), danger: true }))) return;
    try { await api.del(`/api/catalog/${kind}/${name}`); refresh(); st.notify(t("deleted", { name: prefix + name }), "ok"); }
    catch (x) { st.notify(t("delete_failed"), "error", x.message); }
  };

  return (
    <div className="min-h-0 flex-1 overflow-y-auto">
      <div className="mx-auto max-w-6xl px-4 py-6 sm:px-6 sm:py-8">
        <div className="mb-5 flex flex-wrap items-center gap-3">
          <div className="flex-1">
            <h1 className="text-xl font-semibold tracking-tight">{t(kind)}</h1>
            <p className="mt-0.5 text-[13px] text-muted">{t(kind === "skills" ? "skills_desc" : "agents_desc")}</p>
          </div>
          <Button onClick={() => fileRef.current.click()}><FileUp size={15} /> {t("from_file")}</Button>
          <Button variant="primary" onClick={() => setEdit({ isNew: true })}><Plus size={15} /> {t("new")}</Button>
          <input ref={fileRef} type="file" accept=".md,.markdown,.txt" multiple hidden onChange={(e) => { upload([...e.target.files]); e.target.value = ""; }} />
        </div>

        <form onSubmit={importUrl} className="mb-5 flex gap-2">
          <div className="relative flex-1">
            <Link2 size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-subtle" />
            <input className={`${inputCls} pl-9`} value={url} onChange={(e) => setUrl(e.target.value)} placeholder={t("import_url_ph")} />
          </div>
          <Button disabled={!url || busy}>{busy ? <Loader2 size={14} className="animate-spin" /> : <Download size={14} />} {t("import")}</Button>
        </form>

        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {items.map((x) => {
            const ItemIcon = x.builtin ? Terminal : Icon;
            return (
              <div key={x.name} className="group flex flex-col rounded-2xl border border-line bg-elev p-4 transition hover:shadow-md">
                <div className="flex items-start gap-3">
                  <div className={`grid h-9 w-9 shrink-0 place-items-center rounded-xl ${kind === "agents" ? "bg-violet-500/12 text-violet-500" : "bg-accent-soft text-accent"}`}><ItemIcon size={17} /></div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-1.5 font-semibold">{loc(x, "title")}{(x.core || x.builtin) && <Lock size={12} className="text-subtle" />}</div>
                    <div className="font-mono text-xs text-muted">{prefix}{x.name}</div>
                  </div>
                  {!x.builtin && (
                    <div className="flex gap-0.5 opacity-100 sm:opacity-0 sm:group-hover:opacity-100">
                      <button onClick={() => setEdit({ name: x.name })} className="rounded-lg p-1.5 text-muted hover:bg-hover"><Pencil size={14} /></button>
                      {!x.core && <button onClick={() => remove(x.name)} className="rounded-lg p-1.5 text-muted hover:bg-hover hover:text-danger"><Trash2 size={14} /></button>}
                    </div>
                  )}
                </div>
                <p className="mt-3 line-clamp-3 text-[13px] leading-relaxed text-muted">{loc(x, "description")}</p>
              </div>
            );
          })}
        </div>
      </div>
      {edit && <EditorModal kind={kind} {...edit} onClose={() => setEdit(null)} onSaved={refresh} />}
    </div>
  );
}
