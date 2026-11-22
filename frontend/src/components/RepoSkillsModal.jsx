import { useEffect, useMemo, useState } from "react";
import { Check, Download, Loader2, Search } from "lucide-react";
import { useStore, useT } from "../lib/store";
import { api } from "../lib/api";
import { Button, Modal, inputCls } from "./ui";

// "npx skills add owner/repo", owner/repo or a GitHub repository URL, "hf skills add [name]" (Hugging Face
// marketplace), "gradio skills add [user/space]": such commands copy SKILL.md files into an agent's skills folder -
// they are skills, not MCP servers. Lists what the source offers, the user picks some.
export const SKILLS_CMD = /\bskills(@[\w.-]+)?\s+(add|install)\b/i;
export const isRepoSpec = (s) => {
  const v = (s || "").trim();
  return SKILLS_CMD.test(v) || /^[\w.-]+\/[\w.-]+$/.test(v) || /^https?:\/\/github\.com\/[\w.-]+\/[\w.-]+(\.git)?(\/tree\/[^\s]+)?\/?$/i.test(v);
};

export default function RepoSkillsModal({ spec, onClose, onDone }) {
  const t = useT();
  const [data, setData] = useState(null);
  const [err, setErr] = useState("");
  const [q, setQ] = useState("");
  const [picked, setPicked] = useState(() => new Set());
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.post("/api/skills/repo", { spec })
      .then((r) => { setData(r); setPicked(new Set(r.skills.filter((s) => s.picked || s.installed).map((s) => s.path))); })
      .catch((e) => setErr(e.message));
  }, [spec]);

  const shown = useMemo(() => {
    const words = q.toLowerCase().split(/\s+/).filter(Boolean);
    return (data?.skills || []).filter((s) => words.every((w) => `${s.name} ${s.group} ${s.description || ""}`.toLowerCase().includes(w)));
  }, [data, q]);
  const groups = useMemo(() => {
    const g = new Map();
    for (const s of shown) { if (!g.has(s.group)) g.set(s.group, []); g.get(s.group).push(s); }
    return [...g.entries()];
  }, [shown]);

  const flip = (paths, on) => setPicked((old) => {
    const n = new Set(old);
    for (const p of paths) (on ? n.add(p) : n.delete(p));
    return n;
  });
  const run = async () => {
    setBusy(true);
    try {
      const r = await api.post("/api/skills/repo/import", { spec, paths: [...picked] });
      useStore.getState().notify(t("repo_skills_done", { n: r.names.length }), "ok");
      useStore.getState().loadCatalog?.();
      onDone?.(r.names);
      onClose();
    } catch (e) {
      useStore.getState().notify(t("import_failed"), "error", e.message);
    } finally { setBusy(false); }
  };
  const tooMany = picked.size > 60;

  return (
    <Modal title={t("repo_skills_title", { repo: data?.repo || spec })} onClose={onClose} width="max-w-3xl"
      footer={<>
        <span className="mr-auto text-xs text-muted">{t("repo_skills_picked", { n: picked.size, tokens: picked.size * (data?.tokens_each || 40) })}</span>
        <Button variant="ghost" onClick={onClose}>{t("cancel")}</Button>
        <Button variant="primary" disabled={busy || !picked.size || tooMany} onClick={run}>
          {busy ? <Loader2 size={14} className="animate-spin" /> : <Download size={14} />} {t("import")}</Button>
      </>}>
      <p className="mb-3 text-xs leading-snug text-muted">{t("repo_skills_note")}</p>
      {err ? <div className="rounded-xl bg-danger/10 px-3 py-2 text-xs text-danger">{err}</div>
        : !data ? <div className="grid h-40 place-items-center"><Loader2 className="animate-spin text-subtle" /></div> : (
          <>
            <div className="mb-3 flex items-center gap-2">
              <div className="relative flex-1">
                <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-subtle" />
                <input autoFocus className={`${inputCls} pl-9`} value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("repo_skills_search")} />
              </div>
              <span className="shrink-0 text-xs text-subtle">{shown.length} / {data.skills.length}</span>
            </div>
            {tooMany && <div className="mb-2 rounded-xl bg-danger/10 px-3 py-2 text-xs text-danger">{t("repo_skills_too_many")}</div>}
            <div className="max-h-[50vh] space-y-3 overflow-y-auto pr-1">
              {groups.map(([g, list]) => {
                const all = list.every((s) => picked.has(s.path));
                return (
                  <div key={g}>
                    <div className="mb-1 flex items-center gap-2">
                      <span className="font-mono text-[11px] text-subtle">{g || data.repo}</span>
                      <button className="text-[11px] text-accent hover:underline" onClick={() => flip(list.map((s) => s.path), !all)}>
                        {t(all ? "repo_skills_none" : "repo_skills_all")} ({list.length})</button>
                    </div>
                    <div className="grid gap-1 sm:grid-cols-2">
                      {list.map((s) => {
                        const on = picked.has(s.path);
                        return (
                          <button key={s.path} onClick={() => flip([s.path], !on)} title={s.description || s.path}
                            className={`flex items-center gap-2 rounded-lg border px-2.5 py-1.5 text-left text-xs transition ${on ? "border-accent bg-accent-soft" : "border-line hover:bg-hover"}`}>
                            <span className={`grid h-4 w-4 shrink-0 place-items-center rounded border ${on ? "border-accent bg-accent text-white" : "border-line"}`}>{on && <Check size={11} />}</span>
                            <span className="min-w-0 flex-1">
                              <span className="block truncate font-mono">{s.name}</span>
                              {s.description && <span className="line-clamp-2 block text-[11px] leading-snug text-muted">{s.description}</span>}
                            </span>
                            {s.installed && <span className="shrink-0 text-[10px] text-ok">{t("repo_skills_installed")}</span>}
                          </button>
                        );
                      })}
                    </div>
                  </div>
                );
              })}
              {!shown.length && <div className="py-6 text-center text-xs text-subtle">{t("no_results")}</div>}
            </div>
          </>
        )}
    </Modal>
  );
}
