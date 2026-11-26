import { useEffect, useMemo, useRef, useState } from "react";
import { Check, Cloud, Copy, Cpu, Download, FileAudio, Globe2, Loader2, Mic, Pause, Play, Save, Search, Sparkles, Volume2 } from "lucide-react";
import { useStore, useT } from "../lib/store";
import { CLOUD_ENGINES, ENGINE_LABEL, LANG_NAMES, QUALITY_ORDER, SAMPLES, clampRate, defaultVoiceOf, installVoice, loadVoices, previewVoice, speaks, stopPreview } from "../lib/voices";
import { Button, Modal, inputCls } from "./ui";
import Select from "./Select";

// The voice library: local voices (Piper, Kokoro, Chatterbox: offline, downloaded on demand) and Microsoft's online
// voices; search, filter by language / gender / engine / quality, listen, download, pick, tone. Used by "Text to speech",
// the Video Studio and Settings. Value: {voice, rate, pitch?, emotion?, studio?}.

const ENGINE_TONE = { piper: "bg-emerald-500/12 text-emerald-600 dark:text-emerald-400", kokoro: "bg-violet-500/12 text-violet-600 dark:text-violet-400",
  chatterbox: "bg-amber-500/15 text-amber-700 dark:text-amber-400", edge: "bg-sky-500/12 text-sky-600 dark:text-sky-400" };
export const GenderIcon = ({ g, size = 13 }) => (
  <span className={`w-[14px] shrink-0 text-center font-semibold leading-none ${g === "female" ? "text-pink-500" : g === "male" ? "text-sky-500" : "text-subtle"}`}
    style={{ fontSize: size + 1 }}>{g === "female" ? "♀" : g === "male" ? "♂" : "?"}</span>);

const PACK_TONE = "bg-rose-500/12 text-rose-600 dark:text-rose-400"; // Turkish voice packs
const CLOUD_TONE = "bg-indigo-500/12 text-indigo-600 dark:text-indigo-400"; // cloud voices (own key)
export function EngineBadge({ engine }) {
  return <span className={`shrink-0 rounded-md px-1.5 py-px text-[10px] font-medium ${ENGINE_TONE[engine] || (CLOUD_ENGINES.includes(engine) ? CLOUD_TONE : PACK_TONE)}`}>{ENGINE_LABEL[engine] || engine}</span>;
}

export function ToneSliders({ value, onChange, presets }) {
  const t = useT();
  const row = (k, label, min, max, step, fmt, def) => (
    <div className="flex items-center gap-2 text-[11.5px] text-muted">
      <span className="w-20 shrink-0">{label}</span>
      <input type="range" min={min} max={max} step={step} value={value[k] ?? def} onChange={(e) => onChange({ ...value, [k]: +e.target.value })} className="min-w-0 flex-1" />
      <span className="w-12 text-right font-mono tabular-nums">{fmt(value[k] ?? def)}</span>
    </div>
  );
  return (
    <div className="space-y-1.5">
      {row("rate", t("vl_rate"), 0.5, 2, 0.05, (v) => `${(+v).toFixed(2)}×`, 1)}
      {row("pitch", t("vl_pitch"), -6, 6, 0.5, (v) => `${v > 0 ? "+" : ""}${(+v).toFixed(1)}`, 0)}
      {row("emotion", t("vl_emotion"), 0, 1, 0.05, (v) => `${Math.round(v * 100)}%`, 0.5)}
      {presets && (
        <div className="flex items-center gap-2 text-[11.5px] text-muted">
          <span className="w-20 shrink-0">{t("vl_studio")}</span>
          <div className="min-w-0 flex-1">
            <Select size="sm" value={value.studio || ""} onChange={(v) => onChange({ ...value, studio: v })} ariaLabel={t("vl_studio")}
              options={[{ value: "", label: t("vl_studio_default") }, ...presets.map((p) => ({ value: p, label: t(`vl_preset_${p}`), hint: t(`vl_preset_${p}_desc`) }))]} />
          </div>
        </div>
      )}
    </div>
  );
}

export function VoicePicker({ value, onChange, sample, height = "max-h-64", tone = false, installedOnly: onlyInst = false }) {
  const t = useT();
  const cur = value && typeof value === "object" ? value : value ? { voice: value } : {};
  const ui = useStore.getState().prefs?.lang || "tr";
  const [data, setData] = useState(null);
  const [lang, setLang] = useState(ui);
  const [gender, setGender] = useState("");
  const [engine, setEngine] = useState("");
  const [installed, setInstalled] = useState(onlyInst);
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState("");
  const [inst, setInst] = useState({}); // id -> frac while downloading
  useEffect(() => { loadVoices().then(setData).catch(() => setData({ voices: [] })); }, []);
  const all = data?.voices || [];
  useEffect(() => { // the chosen voice's language is shown first
    const v = all.find((x) => x.id === cur.voice);
    if (v && !v.langs) setLang(v.lang || v.locale.slice(0, 2)); // a multilingual cloud voice keeps the language shown
  }, [data]);
  const langs = useMemo(() => {
    const set = [...new Set(all.map((v) => (v.lang || v.locale.split("-")[0]).toLowerCase()))];
    return set.sort((a, b) => (a === ui ? -1 : b === ui ? 1 : (LANG_NAMES[a] || a).localeCompare(LANG_NAMES[b] || b)));
  }, [all, ui]);
  const online = (v) => v.engine === "edge" || !!v.cloud;
  const ofEngine = (v, e) => (e === "local" ? !online(v) : e === "packs" ? !!v.pack : e === "own" ? !!v.own : e === "cloud" ? !!v.cloud : v.engine === e);
  const inLang = useMemo(() => all.filter((v) => !lang || speaks(v, lang)), [all, lang]);
  const list = useMemo(() => {
    const qq = q.trim().toLowerCase();
    return inLang.filter((v) => (!gender || v.gender === gender) && (!engine || ofEngine(v, engine))
      && (!installed || v.installed !== false)
      && (!qq || `${v.name} ${v.locale} ${v.id} ${ENGINE_LABEL[v.engine] || ""} ${v.pack_name || ""}`.toLowerCase().includes(qq)))
      .sort((a, b) => online(a) - online(b) || (b.installed !== false) - (a.installed !== false)
        || (QUALITY_ORDER[a.quality] ?? 3) - (QUALITY_ORDER[b.quality] ?? 3));
  }, [inLang, gender, engine, installed, q]);
  // Every engine with voices in this language, grouped, with its voice count (as the language list shows its counts)
  const engineOpts = useMemo(() => {
    const n = (e) => inLang.filter((v) => ofEngine(v, e) && (!installed || v.installed !== false)).length;
    const opt = (value, label, icon, hint, group) => ({ value, label, icon, group, badge: String(n(value)),
      hint: hint ? `${hint}` : undefined, keywords: value });
    const present = (pred) => [...new Set(inLang.filter(pred).map((v) => v.engine))];
    const packs = present((v) => v.pack && v.installed !== false);
    const clouds = CLOUD_ENGINES.filter((e) => inLang.some((v) => v.cloud && v.engine === e));
    const g1 = t("vl_g_groups"), g2 = t("vl_g_local"), g3 = t("vl_packs"), g4 = t("vl_cloud");
    return [{ value: "", label: t("vl_all_engines"), badge: String(inLang.filter((v) => !installed || v.installed !== false).length) },
      opt("local", t("vl_local_all"), <Cpu size={13} />, t("vl_local_hint"), g1),
      opt("packs", t("vl_packs"), <Cpu size={13} className="text-rose-500" />, t("vl_packs_hint"), g1),
      opt("own", t("vl_own"), <Sparkles size={13} className="text-accent" />, t("vl_own_hint"), g1),
      ...(clouds.length ? [opt("cloud", t("vl_cloud"), <Cloud size={13} className="text-indigo-500" />, t("vl_cloud_hint"), g1)] : []),
      opt("edge", t("vl_online"), <Globe2 size={13} className="text-sky-500" />, t("vl_edge_hint"), g1),
      opt("piper", "Piper", <Cpu size={13} className="text-emerald-500" />, t("vl_piper_hint"), g2),
      opt("kokoro", "Kokoro", <Sparkles size={13} className="text-violet-500" />, t("vl_kokoro_hint"), g2),
      opt("chatterbox", "Chatterbox", <Sparkles size={13} className="text-amber-500" />, t("vl_cbx_hint"), g2),
      ...packs.map((e) => { const v = inLang.find((x) => x.engine === e);
        return opt(e, v?.pack_name || ENGINE_LABEL[e] || e, <Cpu size={13} className="text-rose-500" />, [v?.license, v?.speed === "slow" ? t("vl_slow") : ""].filter(Boolean).join(" · "), g3); }),
      ...clouds.map((e) => opt(e, ENGINE_LABEL[e] || e, <Cloud size={13} className="text-indigo-500" />, t("vl_cloud_paid"), g4))]
      .filter((o) => !o.value || ["local", "edge"].includes(o.value) || o.badge !== "0");
  }, [inLang, installed, t]);
  const textFor = (v) => { const l = (v.lang || v.locale.slice(0, 2)).toLowerCase(); return sample && l === lang ? sample : SAMPLES[l] || SAMPLES.en; };
  const download = async (v) => {
    setInst((s) => ({ ...s, [v.id]: 0 }));
    try {
      const d = await installVoice(v.id, (f) => setInst((s) => ({ ...s, [v.id]: f })));
      setData(d);
      useStore.getState().notify(t("vl_installed", { name: v.name }), "ok");
      return true;
    } catch (e) { useStore.getState().notify(t("vl_install_failed"), "error", e.message); return false; }
    finally { setInst((s) => { const n = { ...s }; delete n[v.id]; return n; }); }
  };
  const [playing, setPlaying] = useState("");
  useEffect(() => () => stopPreview(), []);
  const listen = async (v) => {
    if (playing === v.id) { stopPreview(); setPlaying(""); return; } // the same button pauses
    if (v.installed === false && !(await download(v))) return;
    stopPreview(); setPlaying("");
    setBusy(v.id);
    try {
      const a = await previewVoice({ text: textFor(v), voice: v.id, rate: cur.rate, pitch: cur.pitch, emotion: cur.emotion, preset: cur.studio || undefined });
      setPlaying(v.id);
      const end = () => setPlaying((p) => (p === v.id ? "" : p));
      a.addEventListener("ended", end); a.addEventListener("pause", end);
    } catch (e) { useStore.getState().notify(t("vl_listen_failed"), "error", e.message); }
    setBusy("");
  };
  const choose = async (v) => {
    if (v.installed === false && !(await download(v))) return;
    onChange({ ...cur, voice: v.id });
  };
  const auto = data ? defaultVoiceOf(all, lang, data.settings) : "";
  return (
    <div className="space-y-2">
      <div className="grid grid-cols-2 gap-1.5 sm:grid-cols-[minmax(0,1.4fr)_repeat(3,minmax(0,1fr))]">
        <div className="relative col-span-2 sm:col-span-1">
          <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-subtle" />
          <input className={`${inputCls} !rounded-lg !py-1.5 !pl-7 !text-[12.5px]`} value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("vl_search")} />
        </div>
        <Select size="sm" value={lang} onChange={setLang} searchable ariaLabel={t("vl_lang")}
          options={[{ value: "", label: t("vl_all_langs") }, ...langs.map((l) => ({ value: l, label: LANG_NAMES[l] || l, badge: l.toUpperCase(),
            hint: [`${all.filter((v) => !v.langs && speaks(v, l) && !online(v)).length} ${t("vl_local")}`,
              `${all.filter((v) => speaks(v, l) && v.engine === "edge").length} ${t("vl_online")}`,
              ...(all.some((v) => v.cloud) ? [`${all.filter((v) => v.cloud && speaks(v, l)).length} ${t("vl_cloud_short")}`] : [])].join(" · ") }))]} />
        <Select size="sm" value={gender} onChange={setGender} ariaLabel={t("vl_gender")}
          options={[{ value: "", label: t("vl_any") }, { value: "female", label: t("vl_female"), icon: <GenderIcon g="female" /> },
            { value: "male", label: t("vl_male"), icon: <GenderIcon g="male" /> }]} />
        <Select size="sm" value={engine} onChange={setEngine} searchable ariaLabel={t("vl_engine")} options={engineOpts} />
      </div>
      <label className="flex w-fit cursor-pointer items-center gap-1.5 text-[11.5px] text-muted">
        <input type="checkbox" checked={installed} onChange={(e) => setInstalled(e.target.checked)} />{t("vl_only_ready")}
      </label>
      <div className={`${height} overflow-y-auto overscroll-contain rounded-xl border border-line bg-bg`}>
        {!data && <div className="grid h-16 place-items-center text-[12px] text-muted"><Loader2 size={15} className="animate-spin" /></div>}
        {data && list.length === 0 && <div className="p-3 text-center text-[12px] text-muted">{t("vl_none")}</div>}
        {list.map((v) => {
          const on = cur.voice === v.id;
          const dl = inst[v.id];
          return (
            <div key={v.id} onClick={() => dl === undefined && choose(v)}
              className={`flex cursor-pointer items-center gap-2 border-b border-line/60 px-2.5 py-2 text-[12.5px] last:border-0 ${on ? "bg-accent-soft" : "hover:bg-hover"}`}>
              <button onClick={(e) => { e.stopPropagation(); listen(v); }} title={playing === v.id ? t("vl_pause") : t("vl_listen")} disabled={dl !== undefined}
                className={`grid h-7 w-7 shrink-0 place-items-center rounded-full transition ${playing === v.id ? "bg-accent text-accent-fg" : "bg-hover text-muted hover:bg-accent hover:text-accent-fg"}`}>
                {busy === v.id ? <Loader2 size={12} className="animate-spin" /> : playing === v.id ? <Pause size={12} /> : <Play size={12} className="ml-0.5" />}</button>
              <GenderIcon g={v.gender} />
              <span className="min-w-0 flex-1">
                <span className="flex items-center gap-1.5">
                  <span className="truncate font-medium">{v.name}</span>
                  {v.id === auto && <span className="shrink-0 rounded bg-ok/12 px-1 text-[9.5px] font-medium text-ok">{t("vl_default")}</span>}
                </span>
                <span className="block truncate text-[10.5px] text-subtle">
                  {v.langs ? t("vl_multilingual") : v.locale} · {t(`vl_q_${v.quality || "standard"}`)}{v.cloud ? ` · ${t("vl_cloud_short")}` : ""}{v.speed === "slow" ? ` · ${t("vl_slow")}` : ""}{v.installed === false && v.mb ? ` · ${v.mb} MB` : ""}
                </span>
              </span>
              <EngineBadge engine={v.engine} />
              {dl !== undefined ? (
                <span className="flex w-14 shrink-0 items-center gap-1 text-[10.5px] text-accent"><Loader2 size={11} className="animate-spin" />{Math.round(dl * 100)}%</span>
              ) : v.installed === false ? (
                <button onClick={(e) => { e.stopPropagation(); download(v); }} title={t("vl_download")}
                  className="grid h-7 w-7 shrink-0 place-items-center rounded-lg text-muted hover:bg-hover hover:text-fg"><Download size={13} /></button>
              ) : on ? <Check size={14} className="w-7 shrink-0 text-accent" /> : <span className="w-7 shrink-0" />}
            </div>
          );
        })}
      </div>
      {tone ? <ToneSliders value={cur} onChange={onChange} presets={data?.presets} /> : (
        <div className="flex items-center gap-2 text-[11.5px] text-muted">
          <span className="shrink-0">{t("vl_rate")}</span>
          <input type="range" min={0.5} max={2} step={0.05} value={clampRate(cur.rate)} onChange={(e) => onChange({ ...cur, rate: +e.target.value })} className="min-w-0 flex-1" />
          <span className="w-10 text-right font-mono tabular-nums">{clampRate(cur.rate).toFixed(2)}×</span>
        </div>
      )}
      <div className="flex items-center gap-2 text-[11px] leading-snug text-subtle">
        <span className="min-w-0 flex-1 truncate">{cur.voice ? t("vl_chosen", { v: all.find((x) => x.id === cur.voice)?.name || cur.voice }) : t("vl_auto_note")}</span>
        {cur.voice && <button onClick={() => onChange({ ...cur, voice: undefined })} className="shrink-0 rounded-md px-1.5 py-0.5 hover:bg-hover">{t("vl_auto")}</button>}
      </div>
    </div>
  );
}

// "Text to speech": any text, any voice from the library, played and saved (download, or into the chat's folder)
export function TTSDialog() {
  const t = useT();
  const st = useStore.getState();
  const sessionId = useStore((s) => s.sessionId);
  const [text, setText] = useState("");
  const [voice, setVoice] = useState({});
  const [busy, setBusy] = useState(false);
  const [out, setOut] = useState(null); // {url, blob}
  const [saved, setSaved] = useState("");
  const close = () => useStore.setState({ dialog: null });
  const make = async () => {
    if (!text.trim()) return;
    setBusy(true); setSaved("");
    try {
      let v = voice.voice;
      if (!v) {
        const d = await loadVoices();
        v = defaultVoiceOf(d.voices || [], (st.prefs?.lang || "tr").slice(0, 2), d.settings);
      }
      const r = await fetch("/api/voices/preview", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: text.trim(), voice: v, rate: clampRate(voice.rate), pitch: voice.pitch, emotion: voice.emotion,
          preset: voice.studio || undefined }) });
      if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail?.message || `HTTP ${r.status}`);
      const blob = await r.blob();
      setOut({ url: URL.createObjectURL(blob), blob, voice: v });
    } catch (e) { st.notify(t("vl_tts_failed"), "error", e.message); }
    setBusy(false);
  };
  const save = async () => {
    if (!out || !sessionId) return;
    const name = `${(text.trim().slice(0, 30).toLowerCase().replace(/[^a-z0-9ğüşöçı]+/gi, "-").replace(/^-|-$/g, "") || "speech")}.mp3`;
    const fd = new FormData();
    fd.append("file", new File([out.blob], name, { type: "audio/mpeg" }));
    try {
      await fetch(st.fileApi("/fs/upload?path=audio"), { method: "POST", body: fd });
      setSaved(`audio/${name}`);
    } catch (e) { st.notify(t("vl_save_failed"), "error", e.message); }
  };
  return (
    <Modal title={<span className="flex items-center gap-2"><Volume2 size={17} className="text-emerald-500" />{t("vl_tts_title")}</span>} onClose={close} width="max-w-2xl"
      footer={<><Button variant="ghost" onClick={close}>{t("close")}</Button>
        <Button variant="primary" onClick={make} disabled={busy || !text.trim()}>{busy ? <Loader2 size={14} className="animate-spin" /> : <Mic size={14} />}{t("vl_make")}</Button></>}>
      <div className="space-y-3 text-[13px]">
        <p className="text-xs leading-snug text-muted">{t("vl_tts_desc")}</p>
        <textarea className={`${inputCls} h-28`} value={text} onChange={(e) => setText(e.target.value)} placeholder={t("vl_tts_ph")} maxLength={3000} />
        <div className="text-right text-[11px] text-subtle">{text.length} / 3000</div>
        <VoicePicker value={voice} onChange={setVoice} sample={text.trim().slice(0, 200)} tone />
        {out && (
          <div className="space-y-2 rounded-xl border border-line bg-elev p-2.5">
            <audio src={out.url} controls autoPlay className="w-full" />
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-mono text-[11px] text-subtle">{out.voice}</span>
              <a href={out.url} download="speech.mp3" className="ml-auto flex items-center gap-1 rounded-lg bg-hover px-2 py-1 text-[12px] hover:bg-active"><Download size={13} />{t("download")}</a>
              {sessionId && <button onClick={save} className="flex items-center gap-1 rounded-lg bg-hover px-2 py-1 text-[12px] hover:bg-active"><Save size={13} />{t("vl_save_chat")}</button>}
            </div>
            {saved && <div className="text-[12px] text-ok">✓ {t("vl_saved", { path: saved })}</div>}
          </div>
        )}
      </div>
    </Modal>
  );
}

// "Speech to text": a recording or a video -> transcript (+ subtitles), offline (faster-whisper on the CPU)
export function STTDialog() {
  const t = useT();
  const st = useStore.getState();
  const [file, setFile] = useState(null);
  const [lang, setLang] = useState("");
  const [model, setModel] = useState("base");
  const [busy, setBusy] = useState(false);
  const [res, setRes] = useState(null);
  const [copied, setCopied] = useState(false);
  const [rec, setRec] = useState(null); // MediaRecorder while recording from the microphone
  const chunks = useRef([]);
  const close = () => { rec?.stop(); useStore.setState({ dialog: null }); };
  const run = async (f = file) => {
    if (!f) return;
    setBusy(true); setRes(null);
    const fd = new FormData();
    fd.append("file", f);
    try {
      const r = await fetch(`/api/stt?language=${encodeURIComponent(lang)}&model=${model}`, { method: "POST", body: fd });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail?.message || d.detail || `HTTP ${r.status}`);
      setRes(d);
    } catch (e) { st.notify(t("vl_stt_failed"), "error", e.message); }
    setBusy(false);
  };
  const record = async () => {
    if (rec) { rec.stop(); return; }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mr = new MediaRecorder(stream);
      chunks.current = [];
      mr.ondataavailable = (e) => chunks.current.push(e.data);
      mr.onstop = () => {
        stream.getTracks().forEach((x) => x.stop());
        const f = new File([new Blob(chunks.current, { type: mr.mimeType })], "recording.webm", { type: mr.mimeType });
        setFile(f); setRec(null); run(f);
      };
      mr.start();
      setRec(mr);
    } catch (e) { st.notify(t("vl_mic_failed"), "error", e.message); }
  };
  const dl = (text, name) => { const a = document.createElement("a"); a.href = URL.createObjectURL(new Blob([text], { type: "text/plain" })); a.download = name; a.click(); };
  return (
    <Modal title={<span className="flex items-center gap-2"><FileAudio size={17} className="text-sky-500" />{t("vl_stt_title")}</span>} onClose={close} width="max-w-2xl"
      footer={<><Button variant="ghost" onClick={close}>{t("close")}</Button>
        <Button variant="primary" onClick={() => run()} disabled={busy || !file}>{busy ? <Loader2 size={14} className="animate-spin" /> : <FileAudio size={14} />}{t("vl_transcribe")}</Button></>}>
      <div className="space-y-3 text-[13px]">
        <p className="text-xs leading-snug text-muted">{t("vl_stt_desc")}</p>
        <div className="flex flex-wrap items-center gap-2">
          <label className="flex cursor-pointer items-center gap-1.5 rounded-xl border border-dashed border-line px-3 py-2 hover:bg-hover">
            <FileAudio size={15} className="text-sky-500" /><span className="max-w-[220px] truncate">{file ? file.name : t("vl_pick_file")}</span>
            <input type="file" accept="audio/*,video/*" className="hidden" onChange={(e) => { setFile(e.target.files?.[0] || null); setRes(null); }} />
          </label>
          <button onClick={record} className={`flex items-center gap-1.5 rounded-xl px-3 py-2 ${rec ? "bg-danger text-white" : "bg-hover hover:bg-active"}`}>
            {rec ? <Pause size={14} /> : <Mic size={14} />}{rec ? t("vl_stop_rec") : t("vl_record")}</button>
          <div className="w-40"><Select size="sm" value={lang} onChange={setLang} searchable ariaLabel={t("vl_lang")}
            options={[{ value: "", label: t("vl_auto_lang") }, ...Object.entries(LANG_NAMES).map(([k, v]) => ({ value: k, label: v, badge: k.toUpperCase() }))]} /></div>
          <div className="w-44"><Select size="sm" value={model} onChange={setModel} title={t("vl_model")} ariaLabel={t("vl_model")}
            options={["tiny", "base", "small", "medium"].map((m) => ({ value: m, label: t(`vl_m_${m}`) }))} /></div>
        </div>
        {busy && <div className="flex items-center gap-2 text-[12px] text-muted"><Loader2 size={14} className="animate-spin" />{t("vl_working")}</div>}
        {res && (
          <div className="space-y-2">
            <div className="flex items-center gap-2 text-[12px] text-muted">
              <span>{t("vl_detected", { lang: res.language || "?", s: Math.round(res.seconds || 0) })}</span>
              <button onClick={() => { navigator.clipboard.writeText(res.text || ""); setCopied(true); setTimeout(() => setCopied(false), 1500); }} className="ml-auto flex items-center gap-1 rounded-lg bg-hover px-2 py-1 hover:bg-active">{copied ? <Check size={13} /> : <Copy size={13} />}{t("copy")}</button>
              <button onClick={() => dl(res.text || "", "transcript.txt")} className="flex items-center gap-1 rounded-lg bg-hover px-2 py-1 hover:bg-active"><Download size={13} />TXT</button>
              {res.srt && <button onClick={() => dl(res.srt, "subtitles.srt")} className="flex items-center gap-1 rounded-lg bg-hover px-2 py-1 hover:bg-active"><Download size={13} />SRT</button>}
            </div>
            <textarea readOnly className={`${inputCls} h-56 font-[inherit] leading-relaxed`} value={res.text || ""} />
          </div>
        )}
      </div>
    </Modal>
  );
}
