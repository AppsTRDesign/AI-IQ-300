import { useEffect, useState } from "react";
import { BookMarked, Loader2 } from "lucide-react";
import { useStore, useT } from "../lib/store";
import { api } from "../lib/api";
import { Button, Modal } from "./ui";

const MAX = 6000;

// Project memory: the rules in <project>/AIIQ.md, added to every chat of the project.
// The model also adds rules itself (remember tool) when the user states a lasting preference.
export default function RulesDialog() {
  const t = useT();
  const dialog = useStore((s) => s.dialog);
  const project = useStore((s) => s.projects.find((p) => p.id === dialog?.projectId));
  const close = () => useStore.setState({ dialog: null });
  const [text, setText] = useState(null);
  const [path, setPath] = useState("");
  const [saving, setSaving] = useState(false);
  useEffect(() => {
    api.get(`/api/projects/${dialog.projectId}/rules`).then((r) => { setText(r.text); setPath(r.path); })
      .catch((e) => { useStore.getState().notify(t("rules_load_failed"), "error", e.message); close(); });
  }, [dialog.projectId]);
  const save = async () => {
    setSaving(true);
    try {
      await api.put(`/api/projects/${dialog.projectId}/rules`, { text });
      useStore.getState().notify(t("rules_saved"), "ok");
      close();
    } catch (e) {
      useStore.getState().notify(t("rules_save_failed"), "error", e.message);
    } finally { setSaving(false); }
  };
  return (
    <Modal width="max-w-2xl" onClose={close}
      title={<span className="flex items-center gap-2"><BookMarked size={17} className="text-accent" />{t("rules_title", { project: project?.name || "" })}</span>}
      footer={<>
        <Button variant="ghost" onClick={close}>{t("cancel")}</Button>
        <Button variant="primary" disabled={text == null || saving || text.length > MAX} onClick={save}>{saving ? <Loader2 size={14} className="animate-spin" /> : t("save")}</Button>
      </>}>
      <p className="mb-3 text-[13px] leading-relaxed text-muted">{t("rules_desc")}</p>
      {text == null ? (
        <div className="grid h-40 place-items-center"><Loader2 size={18} className="animate-spin text-accent" /></div>
      ) : (
        <>
          <textarea value={text} onChange={(e) => setText(e.target.value)} autoFocus spellCheck={false} placeholder={t("rules_placeholder")}
            className="h-72 w-full resize-y rounded-2xl border border-line bg-bg p-3 font-mono text-[13px] leading-relaxed outline-none focus:border-accent" />
          <div className="mt-1.5 flex items-center justify-between gap-3 text-[11px] text-subtle">
            <span className="truncate font-mono" title={path}>{path}</span>
            <span className={`shrink-0 tabular-nums ${text.length > MAX ? "text-danger" : ""}`}>{text.length} / {MAX}</span>
          </div>
        </>
      )}
    </Modal>
  );
}
