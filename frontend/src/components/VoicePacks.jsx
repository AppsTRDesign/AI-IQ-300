import { useState } from "react";
import { AlertTriangle, Cpu, Download, Loader2, Play, Sparkles, Trash2, Zap } from "lucide-react";
import { useStore, useT } from "../lib/store";
import { SAMPLES, installVoice, previewVoice } from "../lib/voices";
import { Button } from "./ui";
import Select from "./Select";
import { GenderIcon } from "./VoiceLibrary";

// Settings > Voices > Turkish voice packs: local text-to-speech engines, each in its own environment. Every pack shows
// what it needs (any CPU / a GPU makes it fast / an NVIDIA GPU), its download size and its licence before it is
// installed; packs this computer cannot run say why instead of offering a button.

const TIER_ICON = { light: Zap, medium: Cpu, gpu: Sparkles };

export default function VoicePacks({ voices, hardware, moods, onSaveMoods, onChanged, onRemove }) {
  const t = useT();
  const st = useStore.getState();
  const [prog, setProg] = useState({}); // pack -> 0..1 while installing
  const packs = {};
  for (const v of voices) if (v.pack) (packs[v.pack] ||= []).push(v);
  const install = async (pack, first) => {
    if (first.terms && !(await st.confirm({ title: t("vpk_terms_title"), message: t("vpk_terms_msg", { name: first.name.split(" · ")[0], license: first.license }),
      confirmLabel: t("vpk_terms_ok") }))) return;
    setProg((p) => ({ ...p, [pack]: 0 }));
    try {
      await installVoice(first.id, (f) => setProg((p) => ({ ...p, [pack]: f })));
      st.notify(t("vpk_ready", { name: first.name.split(" · ")[0] }), "ok");
      onChanged();
    } catch (e) { st.notify(t("vl_install_failed"), "error", e.message); }
    setProg((p) => { const n = { ...p }; delete n[pack]; return n; });
  };
  const hw = hardware?.cuda ? t("vpk_hw_cuda", { gb: hardware.vram_gb }) : hardware?.mps ? t("vpk_hw_mps") : t("vpk_hw_cpu");
  return (
    <section className="rounded-2xl border border-line bg-elev">
      <div className="border-b border-line px-4 py-3.5 @md:px-5">
        <h3 className="text-[14px] font-semibold">{t("vpk_title")}</h3>
        <p className="mt-0.5 text-xs leading-snug text-muted">{t("vpk_desc")} <span className="text-subtle">· {hw}</span></p>
      </div>
      {["light", "medium", "gpu"].map((tier) => {
        const Icon = TIER_ICON[tier];
        const list = Object.entries(packs).filter(([, vs]) => vs[0].tier === tier);
        if (!list.length) return null;
        return (
          <div key={tier} className="border-b border-line last:border-b-0">
            <div className="flex items-center gap-2 bg-hover/40 px-4 py-2 text-[12px] font-semibold text-muted @md:px-5">
              <Icon size={13} />{t(`vpk_tier_${tier}`)}<span className="font-normal text-subtle">· {t(`vpk_tier_${tier}_hint`)}</span>
            </div>
            <div className="divide-y divide-line">
              {list.map(([pack, vs]) => {
                const v = vs[0];
                const ready = v.installed !== false;
                const p = prog[pack];
                const name = v.name.split(" · ")[0];
                return (
                  <div key={pack} className="flex flex-col gap-2 px-4 py-3 @md:px-5 @2xl:flex-row @2xl:items-center">
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-1.5 text-[13px] font-medium">
                        {name}
                        <span className="rounded-md bg-hover px-1.5 py-px text-[10px] font-normal text-muted">{v.license}</span>
                        {!v.commercial && <span className="rounded-md bg-amber-500/15 px-1.5 py-px text-[10px] font-medium text-amber-700 dark:text-amber-400">{t("vpk_noncommercial")}</span>}
                        {v.clone && <span className="rounded-md bg-violet-500/12 px-1.5 py-px text-[10px] text-violet-600 dark:text-violet-400">{t("vpk_clone")}</span>}
                        {v.emotion && <span className="rounded-md bg-pink-500/12 px-1.5 py-px text-[10px] text-pink-600 dark:text-pink-400">{t("vpk_emotion")}</span>}
                      </div>
                      <div className="mt-0.5 text-[11.5px] leading-snug text-muted">{t(`vpk_note_${pack}`)}
                        {!ready && <span className="text-subtle"> · {v.mb >= 1000 ? `${(v.mb / 1000).toFixed(1)} GB` : `${v.mb} MB`}</span>}
                        {ready && <span className="text-subtle"> · {vs.map((x) => x.name.split(" · ")[1] || t("vpk_one_voice")).slice(0, 6).join(", ")}{vs.length > 6 ? ` +${vs.length - 6}` : ""}</span>}
                      </div>
                      {v.warn && <div className="mt-1 flex items-start gap-1 text-[11px] leading-snug text-amber-700 dark:text-amber-400"><AlertTriangle size={12} className="mt-px shrink-0" />{t(`vpk_warn_${v.warn}`)}</div>}
                      {v.fit?.state === "slow" && !ready && <div className="mt-1 text-[11px] text-subtle">{t("vpk_fit_slow")}</div>}
                      {v.fit?.state === "no" && <div className="mt-1 text-[11px] text-danger">{t(v.fit.reason === "low_vram" ? "vpk_fit_low_vram" : "vpk_fit_cuda", { gb: v.fit.vram, have: v.fit.have })}</div>}
                    </div>
                    <div className="flex shrink-0 items-center gap-1.5">
                      {ready && v.moods?.length > 0 && (
                        <div className="w-36"><Select value={moods?.[pack] || ""} onChange={(m) => onSaveMoods({ ...(moods || {}), [pack]: m })} ariaLabel={t("vpk_mood")}
                          options={[{ value: "", label: t("vpk_mood_auto") }, ...v.moods.map((m) => ({ value: m, label: m }))]} /></div>
                      )}
                      {ready && (
                        <>
                          <button onClick={() => previewVoice({ text: SAMPLES.tr, voice: v.id }).catch((e) => st.notify(t("vl_listen_failed"), "error", e.message))}
                            className="rounded-lg p-1.5 text-subtle hover:bg-hover" title={t("voice_test")}><Play size={14} /></button>
                          <GenderIcon g={vs.length === 1 ? v.gender : ""} />
                          <button onClick={() => onRemove(v.id, name)} className="rounded-lg p-1.5 text-subtle hover:bg-hover hover:text-danger" title={t("delete")}><Trash2 size={14} /></button>
                        </>
                      )}
                      {!ready && p !== undefined && <span className="flex items-center gap-1.5 text-[12px] text-accent"><Loader2 size={13} className="animate-spin" />{Math.round(p * 100)}%</span>}
                      {!ready && p === undefined && v.fit?.state !== "no" && (
                        <Button className="text-xs" onClick={() => install(pack, v)}><Download size={14} />{t("vpk_install")}</Button>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        );
      })}
    </section>
  );
}
