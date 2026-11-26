import { useEffect, useRef, useState } from "react";
import { AlertTriangle, AudioLines, CheckCircle2, Loader2, Mic, Play, Square, Star, Trash2, Upload, Wand2 } from "lucide-react";
import { useStore, useT } from "../lib/store";
import { api } from "../lib/api";
import { SAMPLES, previewVoice, stopPreview } from "../lib/voices";
import { Button, Toggle, inputCls } from "./ui";
import Select from "./Select";
import { GenderIcon } from "./VoiceLibrary";

// Settings > Voices > Clone studio: bring a recording (file or microphone, with consent), the app measures it and
// cleans it (noise, clicks, rumble, harsh "s", long pauses, loudness), you listen to the original and the cleaned one
// side by side, try it on every installed cloning engine, then keep it as your own narrator voice. A kept voice is
// listed by every cloning engine (xtts:ref-<name>, pocket:ref-<name> ...) and can be made the default voice.

const STEPS = ["highpass", "declick", "deess", "trim", "normalize"];

function Meter({ label, before, after, unit = "", good }) {
  const better = after !== undefined && good && good(after, before);
  return (
    <div className="rounded-xl bg-hover/60 px-3 py-2">
      <div className="text-[10.5px] uppercase tracking-wide text-subtle">{label}</div>
      <div className="mt-0.5 flex flex-wrap items-baseline gap-x-1.5 font-mono text-[13px]">
        <span className="whitespace-nowrap text-muted">{before}{unit}</span>
        {after !== undefined && <span className="whitespace-nowrap"><span className="text-subtle">→ </span><span className={better ? "font-semibold text-ok" : "font-semibold"}>{after}{unit}</span></span>}
      </div>
    </div>
  );
}

export default function CloneStudio({ onSaved, defaults, onMakeDefault }) {
  const t = useT();
  const st = useStore.getState();
  const [info, setInfo] = useState(null);
  const [file, setFile] = useState(null);
  const [ok, setOk] = useState(false);
  const [rec, setRec] = useState(null);
  const [secs, setSecs] = useState(0);
  const [busy, setBusy] = useState("");
  const [res, setRes] = useState(null);
  const [opts, setOpts] = useState(null);
  const [ab, setAb] = useState("clean");
  const [engine, setEngine] = useState("");
  const [text, setText] = useState(SAMPLES.tr);
  const [name, setName] = useState("");
  const [ver, setVer] = useState(0); // cache-buster for the cleaned clip after a re-clean
  const chunks = useRef([]);
  const timer = useRef(null);
  const audio = useRef(null);
  const load = () => api.get("/api/voices/studio").then((d) => { setInfo(d); setOpts((o) => o || d.defaults); setEngine((e) => e || d.engines[0]?.engine || ""); }).catch(() => setInfo({ engines: [], refs: [], defaults: {} }));
  useEffect(() => { load(); return () => { clearInterval(timer.current); stopPreview(); }; }, []);

  const record = async () => {
    if (rec) { rec.stop(); return; }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: false, autoGainControl: false } });
      const mr = new MediaRecorder(stream);
      chunks.current = [];
      mr.ondataavailable = (e) => chunks.current.push(e.data);
      mr.onstop = () => {
        stream.getTracks().forEach((x) => x.stop()); clearInterval(timer.current);
        setFile(new File([new Blob(chunks.current, { type: mr.mimeType })], "kayit.webm", { type: mr.mimeType })); setRec(null);
      };
      mr.start(); setRec(mr); setSecs(0);
      timer.current = setInterval(() => setSecs((s) => s + 1), 1000);
    } catch (e) { st.notify(t("vl_mic_failed"), "error", e.message); }
  };
  const analyse = async () => {
    if (!file || !ok) return;
    setBusy("clean");
    const fd = new FormData();
    fd.append("file", file); fd.append("consent", "true"); fd.append("options", JSON.stringify(opts || {}));
    try {
      const r = await fetch("/api/voices/studio", { method: "POST", body: fd });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail?.message || `HTTP ${r.status}`);
      setRes(d); setVer((v) => v + 1); setAb("clean");
    } catch (e) { st.notify(t("cs_failed"), "error", e.message); }
    setBusy("");
  };
  const reclean = async (o) => {
    setOpts(o);
    if (!res) return;
    setBusy("clean");
    try { const d = await api.post(`/api/voices/studio/${res.id}/clean`, { options: o }); setRes(d); setVer((v) => v + 1); }
    catch (e) { st.notify(t("cs_failed"), "error", e.message); }
    setBusy("");
  };
  const play = (kind) => {
    stopPreview(); audio.current?.pause();
    if (busy === `play-${kind}`) { setBusy(""); return; }
    const a = new Audio(`/api/voices/studio/${res.id}/${kind}.wav?v=${ver}`);
    audio.current = a; setBusy(`play-${kind}`);
    a.onended = a.onpause = () => setBusy((b) => (b === `play-${kind}` ? "" : b));
    a.play().catch(() => setBusy(""));
  };
  const tryClone = async () => {
    audio.current?.pause(); stopPreview();
    setBusy("try");
    try {
      const r = await fetch(`/api/voices/studio/${res.id}/try`, { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ engine, text, kind: ab }) });
      if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail?.message || `HTTP ${r.status}`);
      const a = new Audio(URL.createObjectURL(await r.blob()));
      audio.current = a; setBusy("play-try");
      a.onended = a.onpause = () => setBusy((b) => (b === "play-try" ? "" : b));
      a.play().catch(() => setBusy(""));
    } catch (e) { st.notify(t("cs_try_failed"), "error", e.message); setBusy(""); }
  };
  const save = async (asDefault) => {
    if (!name.trim()) return;
    setBusy("save");
    try {
      const d = await api.post(`/api/voices/studio/${res.id}/save`, { name: name.trim(), kind: ab });
      const vid = d.voices.find((v) => v.engine === engine)?.id || d.voices[0]?.id;
      if (asDefault && vid) await onMakeDefault?.(vid);
      st.notify(t(asDefault ? "cs_saved_default" : "cs_saved", { name: d.name }), "ok");
      setRes(null); setFile(null); setName(""); load(); onSaved?.();
    } catch (e) { st.notify(t("cs_failed"), "error", e.message); }
    setBusy("");
  };
  const removeRef = async (r) => {
    if (!(await st.confirm({ title: t("delete"), message: t("vp_remove_q", { name: r.name }), confirmLabel: t("delete"), danger: true }))) return;
    await api.del(`/api/voices/${encodeURIComponent(`ref:${r.name}`)}`); load(); onSaved?.();
  };
  const listenRef = (r) => { const e = info.engines.find((x) => x.engine === engine) || info.engines[0]; if (e) previewVoice({ text: SAMPLES.tr, voice: e.engine === "chatterbox" ? `chatterbox:ref-${r.name}@tr` : `${e.engine}:ref-${r.name}` }).catch((x) => st.notify(t("vl_listen_failed"), "error", x.message)); };

  if (!info) return null;
  const b = res?.before, a = res?.after;
  const scoreCls = (s) => (s >= 75 ? "text-ok" : s >= 50 ? "text-warn" : "text-danger");
  return (
    <section className="rounded-2xl border border-line bg-elev">
      <div className="border-b border-line px-4 py-3.5 @md:px-5">
        <h3 className="flex items-center gap-2 text-[14px] font-semibold"><AudioLines size={15} className="text-accent" />{t("cs_title")}</h3>
        <p className="mt-0.5 text-xs leading-snug text-muted">{t("cs_desc")}</p>
      </div>
      {!info.engines.length && <div className="px-4 py-3.5 text-[12.5px] text-muted @md:px-5">{t("cs_no_engine")}</div>}

      <div className="space-y-3 px-4 py-3.5 @md:px-5">
        <div className="text-[12.5px] font-medium">1 · {t("cs_step_source")}</div>
        <p className="text-xs leading-snug text-muted">{t("cs_tips")}</p>
        <div className="flex flex-wrap gap-2">
          <label className="flex cursor-pointer items-center gap-1.5 rounded-xl border border-dashed border-line px-3 py-2 text-[12.5px] hover:bg-hover">
            <Upload size={14} /><span className="max-w-[200px] truncate">{file ? file.name : t("vl_pick_file")}</span>
            <input type="file" accept="audio/*,video/*" className="hidden" onChange={(e) => { setFile(e.target.files?.[0] || null); setRes(null); }} />
          </label>
          <button onClick={record} className={`flex items-center gap-1.5 rounded-xl px-3 py-2 text-[12.5px] ${rec ? "bg-danger text-white" : "bg-hover hover:bg-active"}`}>
            {rec ? <Square size={13} /> : <Mic size={14} />}{rec ? `${t("vl_stop_rec")} · ${secs} s` : t("vl_record")}</button>
        </div>
        <label className="flex items-start gap-2 text-[12px] leading-snug text-muted">
          <input type="checkbox" checked={ok} onChange={(e) => setOk(e.target.checked)} className="mt-0.5" />{t("vp_own_consent")}
        </label>
        <Button variant="primary" disabled={!file || !ok || busy === "clean"} onClick={analyse}>
          {busy === "clean" ? <Loader2 size={14} className="animate-spin" /> : <Wand2 size={14} />}{t("cs_analyse")}</Button>
      </div>

      {res && (
        <>
          <div className="space-y-3 px-4 py-3.5 @md:px-5">
            <div className="flex items-center justify-between gap-2">
              <div className="text-[12.5px] font-medium">2 · {t("cs_step_clean")}</div>
              <div className="text-[12px]">{t("cs_score")}: <span className={`font-mono font-semibold ${scoreCls(b.score)}`}>{b.score}</span> → <span className={`font-mono font-semibold ${scoreCls(a.score)}`}>{a.score}</span>/100</div>
            </div>
            <div className="grid grid-cols-2 gap-2 @lg:grid-cols-4">
              <Meter label={t("cs_m_speech")} before={b.speech_s} after={a.speech_s} unit=" s" />
              <Meter label={t("cs_m_snr")} before={b.snr_db} after={a.snr_db} unit=" dB" good={(x, y) => x > y} />
              <Meter label={t("cs_m_noise")} before={b.noise_db} after={a.noise_db} unit=" dB" good={(x, y) => x < y} />
              <Meter label={t("cs_m_clip")} before={b.clip_pct} after={a.clip_pct} unit="%" good={(x, y) => x < y} />
            </div>
            <div className="flex items-center gap-2 text-[12px] text-muted"><GenderIcon g={a.gender} />{t("cs_pitch", { hz: a.pitch_hz })}</div>
            {a.warnings.length > 0 && (
              <div className="space-y-1 rounded-xl border border-warn/40 bg-warn/10 px-3 py-2 text-[12px]">
                {a.warnings.map((w) => <div key={w} className="flex items-start gap-1.5"><AlertTriangle size={13} className="mt-0.5 shrink-0 text-warn" />{t(`cs_w_${w}`)}</div>)}
              </div>
            )}
            <div className="space-y-2 rounded-xl border border-line p-3">
              <div className="flex items-center gap-3 text-[12px]">
                <span className="w-32 shrink-0 font-medium">{t("cs_denoise")}</span>
                <input type="range" min={0} max={1} step={0.05} value={opts.denoise} onChange={(e) => setOpts({ ...opts, denoise: +e.target.value })}
                  onPointerUp={() => reclean(opts)} onKeyUp={() => reclean(opts)} className="min-w-0 flex-1" />
                <span className="w-10 text-right font-mono text-subtle">{Math.round(opts.denoise * 100)}%</span>
              </div>
              <div className="grid gap-2 @md:grid-cols-2">
                {STEPS.map((k) => (
                  <label key={k} className="flex items-center justify-between gap-2 text-[12px]">
                    <span><span className="font-medium">{t(`cs_o_${k}`)}</span><span className="block text-[11px] text-subtle">{t(`cs_o_${k}_d`)}</span></span>
                    <Toggle checked={!!opts[k]} onChange={(v) => reclean({ ...opts, [k]: v })} />
                  </label>
                ))}
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button onClick={() => play("raw")}>{busy === "play-raw" ? <Square size={13} /> : <Play size={14} />}{t("cs_play_raw")}</Button>
              <Button onClick={() => play("clean")}>{busy === "play-clean" ? <Square size={13} /> : <Play size={14} />}{t("cs_play_clean")}</Button>
              <div className="ml-auto flex overflow-hidden rounded-xl border border-line text-[12px]">
                {["clean", "raw"].map((k) => (
                  <button key={k} onClick={() => setAb(k)} className={`px-3 py-1.5 ${ab === k ? "bg-accent text-white" : "hover:bg-hover"}`}>{t(`cs_use_${k}`)}</button>
                ))}
              </div>
            </div>
          </div>

          <div className="space-y-3 px-4 py-3.5 @md:px-5">
            <div className="text-[12.5px] font-medium">3 · {t("cs_step_try")}</div>
            {info.engines.length ? (
              <>
                <Select value={engine} onChange={setEngine} ariaLabel={t("cs_engine")}
                  options={info.engines.map((e) => ({ value: e.engine, label: e.name,
                    hint: [e.commercial ? "" : t("vpk_noncommercial"), e.speed === "slow" ? t("cs_slow") : ""].filter(Boolean).join(" · ") }))} />
                <textarea className={`${inputCls} min-h-[64px]`} value={text} maxLength={600} onChange={(e) => setText(e.target.value)} />
                <Button variant="primary" disabled={!engine || !text.trim() || busy === "try"} onClick={busy === "play-try" ? () => audio.current?.pause() : tryClone}>
                  {busy === "try" ? <Loader2 size={14} className="animate-spin" /> : busy === "play-try" ? <Square size={13} /> : <Play size={14} />}{busy === "try" ? t("cs_trying") : t("cs_try")}</Button>
              </>
            ) : <div className="text-[12px] text-muted">{t("cs_no_engine")}</div>}
          </div>

          <div className="space-y-3 px-4 py-3.5 @md:px-5">
            <div className="text-[12.5px] font-medium">4 · {t("cs_step_save")}</div>
            <div className="flex flex-wrap gap-2">
              <input className={`${inputCls} !w-56`} value={name} onChange={(e) => setName(e.target.value)} placeholder={t("vp_own_name")} maxLength={40} />
              <Button disabled={!name.trim() || busy === "save"} onClick={() => save(false)}>
                {busy === "save" ? <Loader2 size={14} className="animate-spin" /> : <CheckCircle2 size={14} />}{t("cs_save")}</Button>
              <Button variant="primary" disabled={!name.trim() || !engine || busy === "save"} onClick={() => save(true)}><Star size={14} />{t("cs_save_default")}</Button>
            </div>
          </div>
        </>
      )}

      {info.refs.length > 0 && (
        <div className="space-y-2 px-4 py-3.5 @md:px-5">
          <div className="text-[12.5px] font-medium">{t("cs_mine")}</div>
          <div className="divide-y divide-line rounded-xl border border-line">
            {info.refs.map((r) => {
              const isDef = Object.values(defaults || {}).some((v) => String(v).includes(`ref-${r.name}`));
              return (
                <div key={r.name} className="flex items-center gap-2 px-3 py-2 text-[12.5px]">
                  <GenderIcon g={r.gender} /><span className="min-w-0 flex-1 truncate font-medium">{r.name}</span>
                  {isDef && <span className="rounded-md bg-accent-soft px-1.5 py-0.5 text-[10.5px] text-accent">{t("cs_is_default")}</span>}
                  <span className="text-[11px] text-subtle">{r.seconds} s</span>
                  <button onClick={() => listenRef(r)} title={t("voice_test")} className="rounded-lg p-1.5 text-subtle hover:bg-hover"><Play size={13} /></button>
                  {engine && <button onClick={() => onMakeDefault?.(engine === "chatterbox" ? `chatterbox:ref-${r.name}@tr` : `${engine}:ref-${r.name}`).then(() => st.notify(t("cs_saved_default", { name: r.name }), "ok"))}
                    title={t("cs_make_default")} className="rounded-lg p-1.5 text-subtle hover:bg-hover"><Star size={13} /></button>}
                  <button onClick={() => removeRef(r)} title={t("delete")} className="rounded-lg p-1.5 text-subtle hover:bg-hover hover:text-danger"><Trash2 size={13} /></button>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </section>
  );
}
