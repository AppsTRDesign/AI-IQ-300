import { useEffect, useMemo, useRef, useState } from "react";
import { Check, Copy, Download, FileAudio, Loader2, Mic, Pause, Play, Save, Search, Volume2 } from "lucide-react";
import { useStore, useT } from "../lib/store";
import { api } from "../lib/api";
import { edgeVoices } from "../lib/speech";
import { Button, Modal, inputCls } from "./ui";

// The free voice library (Microsoft neural voices through the app, ~400 voices in 100+ languages): search, filter,
// listen, pick. Used by "Text to speech", the Video Studio (project voice, voice-over clips) and anywhere a voice is
// chosen. Value: {voice: "tr-TR-EmelNeural", rate: 1}.

const SAMPLES = {
  tr: "Merhaba, bu ses videonuzu ve metinlerinizi seslendirecek.", en: "Hello, this voice will narrate your videos and texts.",
  de: "Hallo, diese Stimme spricht Ihre Videos und Texte.", fr: "Bonjour, cette voix racontera vos vidéos et vos textes.",
  es: "Hola, esta voz narrará tus vídeos y textos.", it: "Ciao, questa voce narrerà i tuoi video e i tuoi testi.",
  ar: "مرحبا، هذا الصوت سيروي مقاطع الفيديو والنصوص الخاصة بك.", ru: "Привет, этот голос озвучит ваши видео и тексты.",
  pt: "Olá, esta voz vai narrar os seus vídeos e textos.", ja: "こんにちは、この声があなたの動画と文章を読み上げます。",
  zh: "你好，这个声音将为你的视频和文字配音。", nl: "Hallo, deze stem vertelt je video's en teksten.",
};
const LANG_NAMES = { tr: "Türkçe", en: "English", de: "Deutsch", fr: "Français", es: "Español", it: "Italiano", ar: "العربية",
  ru: "Русский", pt: "Português", ja: "日本語", zh: "中文", nl: "Nederlands", ko: "한국어", hi: "हिन्दी", pl: "Polski", sv: "Svenska",
  uk: "Українська", az: "Azərbaycan", fa: "فارسی", el: "Ελληνικά" };
const clampRate = (r) => Math.min(2, Math.max(0.5, +r || 1));

let playing = null;
async function preview(text, voice, rate) {
  if (playing) { playing.pause(); playing = null; }
  const r = await fetch("/api/tts", { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, voice, rate: clampRate(rate) }) });
  if (!r.ok) throw new Error(`tts ${r.status}`);
  const a = new Audio(URL.createObjectURL(await r.blob()));
  playing = a;
  await a.play().catch(() => {});
  return a;
}

export function VoicePicker({ value, onChange, sample, height = "max-h-56" }) {
  const t = useT();
  const cur = value && typeof value === "object" ? value : value ? { voice: value } : {};
  const ui = useStore.getState().prefs?.lang || "tr";
  const [all, setAll] = useState([]);
  const [lang, setLang] = useState((cur.voice || ui).slice(0, 2).toLowerCase());
  const [gender, setGender] = useState("");
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState("");
  useEffect(() => { edgeVoices("").then((v) => setAll(v || [])); }, []);
  const langs = useMemo(() => {
    const set = [...new Set(all.map((v) => v.locale.split("-")[0].toLowerCase()))];
    return set.sort((a, b) => (a === ui ? -1 : b === ui ? 1 : (LANG_NAMES[a] || a).localeCompare(LANG_NAMES[b] || b)));
  }, [all, ui]);
  const list = useMemo(() => {
    const qq = q.trim().toLowerCase();
    return all.filter((v) => (!lang || v.locale.toLowerCase().startsWith(lang)) && (!gender || v.gender === gender)
      && (!qq || `${v.name} ${v.locale} ${v.id}`.toLowerCase().includes(qq)));
  }, [all, lang, gender, q]);
  const listen = async (v) => {
    setBusy(v.id);
    try {
      const l = v.locale.split("-")[0].toLowerCase();
      await preview(sample && (cur.voice === v.id || l === lang) ? sample : SAMPLES[l] || SAMPLES.en, v.id, cur.rate);
    } catch (e) { useStore.getState().notify(t("vl_listen_failed"), "error", e.message); }
    setBusy("");
  };
  return (
    <div className="space-y-2">
      <div className="flex gap-1.5">
        <div className="relative min-w-0 flex-1">
          <Search size={13} className="absolute left-2 top-1/2 -translate-y-1/2 text-subtle" />
          <input className={`${inputCls} !py-1.5 !pl-7 !text-[12.5px]`} value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("vl_search")} />
        </div>
        <select className={`${inputCls} !w-auto !px-2 !py-1.5 !text-[12px]`} value={lang} onChange={(e) => setLang(e.target.value)}>
          <option value="">{t("vl_all_langs")}</option>
          {langs.map((l) => <option key={l} value={l}>{LANG_NAMES[l] || l}</option>)}
        </select>
        <select className={`${inputCls} !w-auto !px-2 !py-1.5 !text-[12px]`} value={gender} onChange={(e) => setGender(e.target.value)}>
          <option value="">{t("vl_any")}</option><option value="female">♀ {t("vl_female")}</option><option value="male">♂ {t("vl_male")}</option>
        </select>
      </div>
      <div className={`${height} overflow-y-auto rounded-xl border border-line`}>
        {!all.length && <div className="grid h-16 place-items-center text-[12px] text-muted"><Loader2 size={15} className="animate-spin" /></div>}
        {all.length > 0 && list.length === 0 && <div className="p-3 text-center text-[12px] text-muted">{t("vl_none")}</div>}
        {list.map((v) => {
          const on = cur.voice === v.id;
          return (
            <div key={v.id} onClick={() => onChange({ ...cur, voice: v.id })}
              className={`flex cursor-pointer items-center gap-2 border-b border-line/50 px-2 py-1.5 text-[12px] last:border-0 ${on ? "bg-accent/10" : "hover:bg-hover"}`}>
              <button onClick={(e) => { e.stopPropagation(); listen(v); }} title={t("vl_listen")}
                className="grid h-6 w-6 shrink-0 place-items-center rounded-full bg-hover text-muted hover:bg-accent hover:text-accent-fg">
                {busy === v.id ? <Loader2 size={11} className="animate-spin" /> : <Play size={11} className="ml-0.5" />}</button>
              <span className={`shrink-0 ${v.gender === "female" ? "text-pink-500" : "text-sky-500"}`}>{v.gender === "female" ? "♀" : "♂"}</span>
              <span className="min-w-0 flex-1 truncate font-medium">{v.name}</span>
              <span className="shrink-0 font-mono text-[10.5px] text-subtle">{v.locale}</span>
              {on && <Check size={13} className="shrink-0 text-accent" />}
            </div>
          );
        })}
      </div>
      <div className="flex items-center gap-2 text-[11.5px] text-muted">
        <span className="shrink-0">{t("vl_rate")}</span>
        <input type="range" min={0.5} max={2} step={0.05} value={clampRate(cur.rate)} onChange={(e) => onChange({ ...cur, rate: +e.target.value })} className="min-w-0 flex-1 accent-[var(--accent)]" />
        <span className="w-9 text-right font-mono tabular-nums">{clampRate(cur.rate).toFixed(2)}×</span>
        {cur.voice && <button onClick={() => onChange({ rate: cur.rate })} className="rounded-md px-1.5 py-0.5 hover:bg-hover">{t("vl_auto")}</button>}
      </div>
      <p className="text-[11px] leading-snug text-subtle">{cur.voice ? t("vl_chosen", { v: cur.voice }) : t("vl_auto_note")}</p>
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
        const list = await edgeVoices((st.prefs?.lang || "tr").slice(0, 2));
        v = (list.find((x) => x.gender === "female") || list[0])?.id;
      }
      const r = await fetch("/api/tts", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: text.trim(), voice: v, rate: clampRate(voice.rate) }) });
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
        <VoicePicker value={voice} onChange={setVoice} sample={text.trim().slice(0, 200)} />
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
          <select className={`${inputCls} !w-auto !py-1.5`} value={lang} onChange={(e) => setLang(e.target.value)}>
            <option value="">{t("vl_auto_lang")}</option>
            {Object.entries(LANG_NAMES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
          <select className={`${inputCls} !w-auto !py-1.5`} value={model} onChange={(e) => setModel(e.target.value)} title={t("vl_model")}>
            {["tiny", "base", "small", "medium"].map((m) => <option key={m} value={m}>{t(`vl_m_${m}`)}</option>)}
          </select>
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
