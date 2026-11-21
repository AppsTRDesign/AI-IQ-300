import { useEffect, useMemo, useRef, useState } from "react";
import { ArrowDown, ArrowUp, Download, Loader2, Mic, Pause, Play, Sparkles, Trash2, Upload } from "lucide-react";
import { useStore, useT } from "../lib/store";
import { api } from "../lib/api";
import { ENGINE_LABEL, LANG_NAMES, SAMPLES, installVoice, loadVoices, previewVoice, stopPreview } from "../lib/voices";
import { Button, Toggle, inputCls } from "./ui";
import Select from "./Select";
import { EngineBadge, GenderIcon, ToneSliders, VoicePicker } from "./VoiceLibrary";

// Settings > Voices: the default voice per language, tone and studio finish for everything the app says, the
// engine order (one at a time; the next only when one fails), Chatterbox's own environment and the user's own voice.

const Card = ({ title, desc, children, action }) => (
  <section className="rounded-2xl border border-line bg-elev">
    <div className="flex flex-wrap items-start justify-between gap-3 border-b border-line px-4 py-3.5 @md:px-5">
      <div className="min-w-0"><h3 className="text-[14px] font-semibold">{title}</h3>{desc && <p className="mt-0.5 text-xs leading-snug text-muted">{desc}</p>}</div>
      {action}
    </div>
    <div className="divide-y divide-line">{children}</div>
  </section>
);
const Row = ({ label, desc, children }) => (
  <div className="flex flex-col gap-2 px-4 py-3.5 @md:px-5 @2xl:flex-row @2xl:items-center @2xl:justify-between">
    <div className="min-w-0 @2xl:max-w-[48%]"><div className="text-[13px] font-medium">{label}</div>{desc && <div className="mt-0.5 text-xs leading-snug text-muted">{desc}</div>}</div>
    <div className="min-w-0 @2xl:w-[340px] @2xl:shrink-0">{children}</div>
  </div>
);

export default function VoicesPane() {
  const t = useT();
  const st = useStore.getState();
  const cfg = useStore((s) => s.settings?.voice) || {};
  const ui = useStore((s) => s.prefs?.lang) || "tr";
  const [data, setData] = useState(null);
  const [lang, setLang] = useState(ui);
  const [tone, setTone] = useState(null);
  const [busy, setBusy] = useState("");
  const [cbx, setCbx] = useState(null); // progress 0..1 while Chatterbox installs
  const reload = () => loadVoices(true).then(setData).catch(() => setData({ voices: [], engines: {} }));
  useEffect(() => { reload(); }, []);
  useEffect(() => { setTone({ rate: cfg.rate ?? 1, pitch: cfg.pitch ?? 0, emotion: cfg.emotion ?? 0.5, studio: cfg.studio || "natural" }); }, [cfg.rate, cfg.pitch, cfg.emotion, cfg.studio]);
  const save = (patch) => st.updateSettings({ voice: patch }).then(() => loadVoices(true).then(setData));
  const voices = data?.voices || [];
  const engines = data?.engines || {};
  const order = cfg.order || ["piper", "kokoro", "chatterbox", "edge"];
  const off = new Set(cfg.disabled || []);
  const langs = useMemo(() => [...new Set(voices.map((v) => v.lang || v.locale.slice(0, 2)))]
    .sort((a, b) => (a === ui ? -1 : b === ui ? 1 : (LANG_NAMES[a] || a).localeCompare(LANG_NAMES[b] || b))), [voices, ui]);
  const installedLocal = voices.filter((v) => v.engine !== "edge" && v.installed !== false && !v.own);
  const refs = voices.filter((v) => v.own && v.id.endsWith(`@${ui}`));
  const move = (i, d) => { const o = [...order]; [o[i], o[i + d]] = [o[i + d], o[i]]; save({ order: o }); };
  const saveTone = (v) => { setTone(v); };
  const commitTone = () => tone && save({ rate: tone.rate, pitch: tone.pitch, emotion: tone.emotion, studio: tone.studio || "natural" });
  const test = async () => {
    if (busy === "playing") { stopPreview(); setBusy(""); return; } // the same button pauses
    setBusy("test");
    try {
      const a = await previewVoice({ text: SAMPLES[lang] || SAMPLES.en, voice: cfg.defaults?.[lang] || installedLocal.find((v) => v.lang === lang)?.id || voices.find((v) => v.lang === lang)?.id,
        rate: tone.rate, pitch: tone.pitch, emotion: tone.emotion, preset: tone.studio, room: cfg.room });
      setBusy("playing");
      const end = () => setBusy((b) => (b === "playing" ? "" : b));
      a.addEventListener("ended", end); a.addEventListener("pause", end);
    } catch (e) { st.notify(t("vl_listen_failed"), "error", e.message); setBusy(""); }
  };
  const installCbx = async () => {
    setCbx(0);
    try { await installVoice(`chatterbox:default@${ui}`, (f) => setCbx(f)); st.notify(t("vp_cbx_ready"), "ok"); reload(); }
    catch (e) { st.notify(t("vl_install_failed"), "error", e.message); }
    setCbx(null);
  };
  const remove = async (id, name) => {
    if (!(await st.confirm({ title: t("delete"), message: t("vp_remove_q", { name }), confirmLabel: t("delete"), danger: true }))) return;
    await api.del(`/api/voices/${encodeURIComponent(id)}`);
    reload();
  };
  if (!data || !tone) return <div className="grid h-40 place-items-center text-muted"><Loader2 className="animate-spin" /></div>;
  return (
    <div className="space-y-4">
      <Card title={t("vp_default_title")} desc={t("vp_default_desc")}
        action={<Button className="text-xs" onClick={test} disabled={busy === "test"}>{busy === "test" ? <Loader2 size={14} className="animate-spin" /> : busy === "playing" ? <Pause size={14} /> : <Play size={14} />}{busy === "playing" ? t("vl_pause") : t("voice_test")}</Button>}>
        <Row label={t("vl_lang")} desc={t("vp_lang_desc")}>
          <Select value={lang} onChange={setLang} searchable ariaLabel={t("vl_lang")}
            options={langs.map((l) => ({ value: l, label: LANG_NAMES[l] || l, badge: l.toUpperCase(),
              hint: cfg.defaults?.[l] ? voices.find((v) => v.id === cfg.defaults[l])?.name : t("vl_auto") }))} />
        </Row>
        <div className="px-4 py-3.5 @md:px-5">
          <VoicePicker key={lang} value={{ voice: cfg.defaults?.[lang], rate: tone.rate }} height="max-h-80"
            onChange={(v) => save({ defaults: { ...(cfg.defaults || {}), [lang]: v.voice || "" } })} />
        </div>
      </Card>

      <Card title={t("vp_tone_title")} desc={t("vp_tone_desc")}>
        <div className="px-4 py-3.5 @md:px-5" onPointerUp={commitTone} onKeyUp={commitTone}>
          <ToneSliders value={tone} onChange={(v) => { saveTone(v); if (v.studio !== tone.studio) save({ studio: v.studio || "natural" }); }} presets={data.presets} />
        </div>
        <Row label={t("vp_pause")} desc={t("vp_pause_desc")}>
          <div className="flex items-center gap-2 text-[11.5px] text-muted">
            <input type="range" min={0.1} max={1.2} step={0.05} defaultValue={cfg.pause ?? 0.3} onPointerUp={(e) => save({ pause: +e.target.value })} onKeyUp={(e) => save({ pause: +e.target.value })} className="min-w-0 flex-1" />
            <span className="w-12 text-right font-mono">{(cfg.pause ?? 0.3).toFixed(2)} s</span>
          </div>
        </Row>
        <Row label={t("vp_room")} desc={t("vp_room_desc")}><Toggle checked={!!cfg.room} onChange={(v) => save({ room: v })} /></Row>
        <Row label={t("vp_quality")} desc={t("vp_quality_desc")}>
          <Select value={cfg.quality || "fast"} onChange={(v) => save({ quality: v })} ariaLabel={t("vp_quality")}
            options={[{ value: "fast", label: t("vp_quality_fast"), hint: t("vp_quality_fast_hint") },
              { value: "best", label: t("vp_quality_best"), hint: t("vp_quality_best_hint"), disabled: !engines.chatterbox }]} />
        </Row>
      </Card>

      <Card title={t("vp_engines_title")} desc={t("vp_engines_desc")}>
        {order.map((e, i) => (
          <div key={e} className="flex items-center gap-3 px-4 py-3 @md:px-5">
            <span className="grid h-6 w-6 shrink-0 place-items-center rounded-lg bg-hover text-[11px] font-semibold text-muted">{i + 1}</span>
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2 text-[13px] font-medium">{ENGINE_LABEL[e]}<EngineBadge engine={e} /></div>
              <div className="text-[11.5px] leading-snug text-muted">{t(`vp_engine_${e}`)}
                <span className="text-subtle"> · {e === "piper" ? t("vp_n_installed", { n: engines.piper || 0 }) : e === "edge" ? (engines.edge ? t("vp_online_ok") : t("vp_online_off"))
                  : engines[e] ? t("vp_ready") : t("vp_not_installed")}</span></div>
            </div>
            <div className="flex shrink-0 items-center gap-0.5">
              <button disabled={i === 0} onClick={() => move(i, -1)} className="rounded-lg p-1.5 text-subtle hover:bg-hover disabled:opacity-30" title={t("vp_up")}><ArrowUp size={14} /></button>
              <button disabled={i === order.length - 1} onClick={() => move(i, 1)} className="rounded-lg p-1.5 text-subtle hover:bg-hover disabled:opacity-30" title={t("vp_down")}><ArrowDown size={14} /></button>
            </div>
            <Toggle checked={!off.has(e)} onChange={(v) => save({ disabled: v ? [...off].filter((x) => x !== e) : [...off, e] })} />
          </div>
        ))}
      </Card>

      <Card title={<span className="flex items-center gap-2"><Sparkles size={15} className="text-amber-500" />Chatterbox</span>} desc={t("vp_cbx_desc")}
        action={engines.chatterbox ? <span className="rounded-md bg-ok/12 px-2 py-1 text-[11px] font-medium text-ok">{t("vp_ready")}</span>
          : cbx !== null ? <span className="flex items-center gap-1.5 text-[12px] text-accent"><Loader2 size={13} className="animate-spin" />{Math.round(cbx * 100)}%</span>
            : <Button variant="primary" className="text-xs" onClick={installCbx}><Download size={14} />{t("vp_cbx_install")}</Button>}>
        {engines.chatterbox && <OwnVoice t={t} refs={refs} onDone={reload} onRemove={remove} />}
        {engines.chatterbox && (
          <Row label={t("vp_cbx_remove")} desc={t("vp_cbx_remove_desc")}>
            <Button variant="danger" onClick={() => remove(`chatterbox:default@${ui}`, "Chatterbox")}><Trash2 size={14} />{t("delete")}</Button>
          </Row>
        )}
      </Card>

      <Card title={t("vp_installed_title")} desc={t("vp_installed_desc")}>
        {installedLocal.filter((v, i, a) => v.engine !== "chatterbox" && (v.engine !== "kokoro" || a.findIndex((x) => x.engine === "kokoro") === i)).map((v) => (
          <div key={v.id} className="flex items-center gap-2.5 px-4 py-2.5 text-[12.5px] @md:px-5">
            <GenderIcon g={v.engine === "kokoro" ? "" : v.gender} />
            <span className="min-w-0 flex-1 truncate font-medium">{v.engine === "kokoro" ? t("vp_kokoro_pack") : `${v.name} · ${v.locale}`}</span>
            <EngineBadge engine={v.engine} />
            <span className="w-14 shrink-0 text-right text-[11px] text-subtle">{v.mb} MB</span>
            <button onClick={() => remove(v.id, v.engine === "kokoro" ? "Kokoro" : v.name)} className="rounded-lg p-1.5 text-subtle hover:bg-hover hover:text-danger" title={t("delete")}><Trash2 size={14} /></button>
          </div>
        ))}
        {!installedLocal.length && <div className="px-5 py-4 text-[12.5px] text-muted">{t("vp_none_installed")}</div>}
      </Card>
    </div>
  );
}

// The user's own voice for Chatterbox: 5-30 s of clear speech, only with consent (own voice or permission).
function OwnVoice({ t, refs, onDone, onRemove }) {
  const st = useStore.getState();
  const [name, setName] = useState("");
  const [file, setFile] = useState(null);
  const [ok, setOk] = useState(false);
  const [busy, setBusy] = useState(false);
  const [rec, setRec] = useState(null);
  const chunks = useRef([]);
  const upload = async (f = file) => {
    if (!f || !name.trim() || !ok) return;
    setBusy(true);
    const fd = new FormData();
    fd.append("file", f); fd.append("name", name.trim()); fd.append("consent", "true");
    try {
      const r = await fetch("/api/voices/reference", { method: "POST", body: fd });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail?.message || `HTTP ${r.status}`);
      st.notify(t("vp_own_saved", { name: d.name, s: d.seconds }), "ok");
      setName(""); setFile(null); onDone();
    } catch (e) { st.notify(t("vp_own_failed"), "error", e.message); }
    setBusy(false);
  };
  const record = async () => {
    if (rec) { rec.stop(); return; }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mr = new MediaRecorder(stream);
      chunks.current = [];
      mr.ondataavailable = (e) => chunks.current.push(e.data);
      mr.onstop = () => { stream.getTracks().forEach((x) => x.stop()); setFile(new File([new Blob(chunks.current, { type: mr.mimeType })], "voice.webm", { type: mr.mimeType })); setRec(null); };
      mr.start(); setRec(mr);
    } catch (e) { st.notify(t("vl_mic_failed"), "error", e.message); }
  };
  return (
    <div className="space-y-2.5 px-4 py-3.5 @md:px-5">
      <div className="text-[13px] font-medium">{t("vp_own_title")}</div>
      <p className="text-xs leading-snug text-muted">{t("vp_own_desc")}</p>
      <div className="flex flex-wrap gap-2">
        <input className={`${inputCls} !w-48`} value={name} onChange={(e) => setName(e.target.value)} placeholder={t("vp_own_name")} maxLength={40} />
        <label className="flex cursor-pointer items-center gap-1.5 rounded-xl border border-dashed border-line px-3 py-2 text-[12.5px] hover:bg-hover">
          <Upload size={14} /><span className="max-w-[160px] truncate">{file ? file.name : t("vl_pick_file")}</span>
          <input type="file" accept="audio/*,video/*" className="hidden" onChange={(e) => setFile(e.target.files?.[0] || null)} />
        </label>
        <button onClick={record} className={`flex items-center gap-1.5 rounded-xl px-3 py-2 text-[12.5px] ${rec ? "bg-danger text-white" : "bg-hover hover:bg-active"}`}>
          <Mic size={14} />{rec ? t("vl_stop_rec") : t("vl_record")}</button>
      </div>
      <label className="flex items-start gap-2 text-[12px] leading-snug text-muted">
        <input type="checkbox" checked={ok} onChange={(e) => setOk(e.target.checked)} className="mt-0.5" />{t("vp_own_consent")}
      </label>
      <Button variant="primary" disabled={!file || !name.trim() || !ok || busy} onClick={() => upload()}>
        {busy ? <Loader2 size={14} className="animate-spin" /> : <Upload size={14} />}{t("vp_own_add")}</Button>
      {refs.length > 0 && (
        <div className="divide-y divide-line rounded-xl border border-line">
          {refs.map((v) => (
            <div key={v.id} className="flex items-center gap-2 px-3 py-2 text-[12.5px]">
              <GenderIcon g={v.gender} /><span className="min-w-0 flex-1 truncate font-medium">{v.name.replace(/ \(\w+\)$/, "")}</span>
              <button onClick={() => previewVoice({ text: SAMPLES.tr, voice: v.id })} className="rounded-lg p-1.5 text-subtle hover:bg-hover"><Play size={13} /></button>
              <button onClick={() => onRemove(`ref:${v.id.split(":")[1].split("@")[0].slice(4)}`, v.name)} className="rounded-lg p-1.5 text-subtle hover:bg-hover hover:text-danger"><Trash2 size={13} /></button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
