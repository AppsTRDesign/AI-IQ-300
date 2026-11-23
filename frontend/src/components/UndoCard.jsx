import { useState } from "react";
import { Loader2, Undo2 } from "lucide-react";

import { api } from "../lib/api";
import { useStore, useT } from "../lib/store";

// Under a stopped or failed task: put back the files it changed. Only files still exactly as the task left them are
// restored; a file changed since (by the user or a later task) is skipped and listed. Shell-command changes are not
// tracked (projects have the git time machine for those).
export default function UndoCard({ undo }) {
  const t = useT();
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(undo.done || null);
  const files = undo.files || [];
  if (!files.length) return null;

  const run = async () => {
    const st = useStore.getState();
    const ok = await st.confirm({
      title: t("undo_task_title"),
      message: t("undo_task_confirm", { n: files.length }) + "\n\n" + files.slice(0, 12).join("\n") + (files.length > 12 ? "\n…" : ""),
      confirmLabel: t("undo_task_button", { n: files.length }),
    });
    if (!ok) return;
    setBusy(true);
    try {
      const res = await api.post(`/api/sessions/${st.sessionId}/undo/${undo.run}`);
      setDone(res);
      st.notify(t("undo_task_done", { n: (res.restored?.length || 0) + (res.removed?.length || 0) }), "ok");
    } catch (e) {
      st.notify(t("undo_task_failed"), "error", e.message);
    } finally {
      setBusy(false);
    }
  };

  if (done) {
    const back = [...(done.restored || []), ...(done.removed || [])];
    const skipped = (done.skipped || []).filter((s) => s.path);
    return (
      <div className="mt-2 rounded-xl border border-line bg-elev px-3 py-2 text-[13px]">
        <div className="flex items-center gap-1.5 font-medium"><Undo2 size={13} /> {t("undo_task_done", { n: back.length })}</div>
        {skipped.length > 0 && (
          <ul className="mt-1 list-disc pl-5 text-subtle">
            {skipped.map((s) => <li key={s.path}><code>{s.path}</code>: {t("undo_task_skipped")}</li>)}
          </ul>
        )}
      </div>
    );
  }
  return (
    <button onClick={run} disabled={busy} title={t("undo_task_hint")}
      className="mt-2 mr-2 inline-flex items-center gap-1.5 rounded-xl border border-line bg-elev px-3 py-1.5 text-[13px] font-medium hover:border-accent hover:text-accent disabled:opacity-60">
      {busy ? <Loader2 size={13} className="animate-spin" /> : <Undo2 size={13} />} {t("undo_task_button", { n: files.length })}
    </button>
  );
}
