import { useEffect, useRef, useState } from "react";
import { Clapperboard, Check, Download, Film, Loader2, Mic2, Music2, Pause, Play, RefreshCw, SlidersHorizontal, SquareArrowOutUpRight } from "lucide-react";
import { useStore, useT } from "../lib/store";
import { api } from "../lib/api";
import { fileType, isAudio, isImage, isVideo, isWebPage } from "../lib/fileTypes";
import VideoPlayer from "./VideoPlayer";
import { AudioPlayer } from "./MediaPlayer";
import { ToneSliders } from "./VoiceLibrary";
import { loadVoices } from "../lib/voices";

const rawUrl = (path, v = 0) => useStore.getState().fileApi(`/fs/raw?path=${encodeURIComponent(path)}`) + (v ? `&v=${v}` : "");
const nameOf = (path) => path.split(/[\\/]/).pop();

// Voices of the audio's language with a live preview (the first sentence read by each voice, played at once), and
// "use this voice": the same text is written again with it, the player above reloads.
function VoicePicker({ path, tts, voice, onDone }) {
  const t = useT();
  const [voices, setVoices] = useState(null);
  const [error, setError] = useState("");
  const [playing, setPlaying] = useState("");
  const [busy, setBusy] = useState("");
  const [current, setCurrent] = useState(voice || tts.voice);
  const audio = useRef(null);
  useEffect(() => {
    api.get(`/api/tts/voices?lang=${encodeURIComponent(tts.lang || "tr")}`)
      .then((r) => setVoices((r.voices || []).filter((v) => v.installed !== false))).catch((e) => setError(String(e.message || e)));
    return () => audio.current?.pause();
  }, [tts.lang]);
  const sample = (tts.text.match(/^[\s\S]{20,180}?[.!?…](\s|$)/) || [tts.text.slice(0, 160)])[0].trim();
  const preview = async (v) => {
    audio.current?.pause();
    if (playing === v) { setPlaying(""); return; }
    setPlaying(v);
    try {
      const res = await fetch("/api/tts", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: sample, voice: v, rate: tts.rate || 1 }) });
      if (!res.ok) throw new Error(`tts ${res.status}`);
      const a = new Audio(URL.createObjectURL(await res.blob()));
      audio.current = a;
      a.onended = () => setPlaying("");
      await a.play();
    } catch (e) { setPlaying(""); setError(String(e.message || e)); }
  };
  // tone of the file: after "use this voice" the settings open, so speed / pitch / emotion / studio finish can be
  // tuned and the file written again with them
  const [tone, setTone] = useState({ rate: tts.rate || 1, pitch: tts.pitch ?? 0, emotion: tts.emotion ?? 0.5, studio: tts.studio || "" });
  const [toneOpen, setToneOpen] = useState(false);
  const [presets, setPresets] = useState(null);
  useEffect(() => { loadVoices().then((d) => setPresets(d.presets || [])).catch(() => setPresets([])); }, []);
  const write = async (v, withTone) => {
    await api.post(useStore.getState().fileApi("/tts-file").split("?")[0], {
      text: tts.text, voice: v, path, rate: withTone.rate || 1, pitch: withTone.pitch, emotion: withTone.emotion,
      preset: withTone.studio || undefined });
  };
  const choose = async (v) => {
    setBusy(v); setError("");
    try {
      await write(v, tone);
      setCurrent(v);
      onDone(v);
      setToneOpen(true);
    } catch (e) { setError(String(e.message || e)); }
    setBusy("");
  };
  const applyTone = async () => {
    setBusy("tone"); setError("");
    try { await write(current, tone); onDone(current); } catch (e) { setError(String(e.message || e)); }
    setBusy("");
  };
  return (
    <div className="mt-2 rounded-xl border border-line bg-panel/50 p-2">
      <div className="mb-1.5 flex items-center gap-1.5 px-1 text-[11.5px] text-muted"><Mic2 size={12} />{t("voice_pick_hint")}</div>
      {error && <div className="px-1 pb-1 text-[11px] text-danger">{error}</div>}
      {!voices ? <div className="flex items-center gap-1.5 px-1 py-1 text-[12px] text-subtle"><Loader2 size={12} className="animate-spin" />{t("loading")}</div> : (
        <div className="grid max-h-64 gap-1 overflow-y-auto sm:grid-cols-2">
          {voices.map((v) => (
            <div key={v.id} className={`flex items-center gap-2 rounded-lg border px-2 py-1.5 text-[12px] ${current === v.id ? "border-accent bg-accent-soft" : "border-line bg-elev"}`}>
              <button onClick={() => preview(v.id)} title={t("voice_preview")}
                className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-hover text-fg hover:bg-accent hover:text-accent-fg">
                {playing === v.id ? <Pause size={13} /> : <Play size={13} />}
              </button>
              <span className="min-w-0 flex-1">
                <span className="block truncate font-medium">{v.name}</span>
                <span className="block truncate text-[10.5px] text-subtle">{t(v.gender === "female" ? "voice_female" : "voice_male")} · {v.locale} · {v.engine === "edge" ? "Online" : (v.engine || "").replace(/^./, (c) => c.toUpperCase())}</span>
              </span>
              {current === v.id ? <span className="flex items-center gap-1 text-[11px] font-medium text-accent"><Check size={12} />{t("voice_in_use")}</span> : (
                <button onClick={() => choose(v.id)} disabled={!!busy}
                  className="shrink-0 rounded-md bg-hover px-2 py-1 text-[11px] font-medium hover:bg-accent hover:text-accent-fg disabled:opacity-50">
                  {busy === v.id ? <Loader2 size={12} className="animate-spin" /> : t("voice_use")}
                </button>
              )}
            </div>
          ))}
        </div>
      )}
      <div className="mt-2 rounded-lg border border-line bg-elev">
        <button onClick={() => setToneOpen(!toneOpen)} className="flex w-full items-center gap-1.5 px-2.5 py-1.5 text-left text-[12px] font-medium">
          <SlidersHorizontal size={13} className="text-accent" />{t("voice_tone_settings")}
          <span className="ml-auto text-[11px] font-normal text-subtle">{(tone.rate || 1).toFixed(2)}× · {tone.pitch > 0 ? "+" : ""}{(+tone.pitch || 0).toFixed(1)} · {Math.round((tone.emotion ?? 0.5) * 100)}%</span>
        </button>
        {toneOpen && (
          <div className="space-y-2 border-t border-line px-2.5 py-2">
            <ToneSliders value={tone} onChange={setTone} presets={presets} />
            <div className="flex justify-end">
              <button onClick={applyTone} disabled={!!busy}
                className="flex items-center gap-1.5 rounded-lg bg-accent px-3 py-1.5 text-[12px] font-medium text-accent-fg disabled:opacity-50">
                {busy === "tone" ? <Loader2 size={13} className="animate-spin" /> : <RefreshCw size={13} />}{t("voice_tone_apply")}</button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// A generated audio or video file: a card with a real player (like the document cards), open/download, and for
// speech made by text_to_speech the voice picker.
function MediaCard({ path, tts }) {
  const t = useT();
  const [v, setV] = useState(0);
  const [pick, setPick] = useState(false);
  const [voice, setVoice] = useState(tts?.voice || "");
  const video = isVideo(path);
  const ft = fileType(path);
  const Icon = video ? Film : Music2;
  return (
    <div className="w-full max-w-lg rounded-2xl border border-line bg-elev p-2.5 shadow-[0_1px_4px_rgb(0_0_0/0.04)]">
      <div className="flex items-center gap-3">
        <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl text-white shadow-sm" style={{ background: ft.color || "#7c3aed" }}><Icon size={20} /></span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-[13.5px] font-semibold">{nameOf(path)}</span>
          <span className="block truncate text-xs text-subtle">{t(video ? "media_video" : "media_audio")}{voice ? ` · ${voice}` : ""}</span>
        </span>
        {tts && <button onClick={() => setPick(!pick)} className={`shrink-0 rounded-lg px-2 py-1 text-[11px] font-medium ${pick ? "bg-accent text-accent-fg" : "bg-hover text-muted hover:text-fg"}`}><Mic2 size={12} className="mr-1 inline" />{t("voice_change")}</button>}
        {video && <button onClick={() => useStore.getState().openStudio(path)} title={t("vs_edit_in_studio")} className="flex shrink-0 items-center gap-1 rounded-lg bg-accent/10 px-2 py-1 text-[11px] font-medium text-accent hover:bg-accent/20"><Clapperboard size={12} />{t("vs_studio_short")}</button>}
        <a href={rawUrl(path) + "&download=true"} download={nameOf(path)} title={t("download")} className="shrink-0 rounded-lg p-1.5 text-subtle hover:bg-hover hover:text-fg"><Download size={14} /></a>
        <button type="button" onClick={(e) => { e.preventDefault(); e.stopPropagation(); useStore.getState().playMedia(path); }} title={t("open")} className="shrink-0 rounded-lg p-1.5 text-subtle hover:bg-hover hover:text-fg"><SquareArrowOutUpRight size={14} /></button>
      </div>
      {/* the same players as the full-screen viewer: custom video controls, the audio waveform */}
      <div className="mt-2">
        {video
          ? <VideoPlayer key={v} url={rawUrl(path, v)} path={path} inline />
          : <AudioPlayer key={v} url={rawUrl(path, v)} inline />}
      </div>
      {pick && tts && <VoicePicker path={path} tts={tts} voice={voice} onDone={(nv) => { setV((n) => n + 1); setVoice(nv); }} />}
    </div>
  );
}

// What a task produced: image thumbnails (open the viewer), web pages (open the browser) and audio/video players.
export default function OutputGallery({ paths, steps }) {
  const t = useT();
  const images = (paths || []).filter(isImage);
  const pages = (paths || []).filter(isWebPage);
  const media = (paths || []).filter((p) => isAudio(p) || isVideo(p));
  if (!images.length && !pages.length && !media.length) return null;
  const st = useStore.getState();
  const ttsOf = (p) => (steps || []).find((s) => s.data?.tts && s.data?.path === p)?.data.tts;
  return (
    <div className="mt-3 space-y-2">
      {media.length > 0 && <div className="flex flex-col gap-2">{media.map((p) => <MediaCard key={p} path={p} tts={ttsOf(p)} />)}</div>}
      {images.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {images.map((p, i) => (
            <button type="button" key={p} onClick={() => st.viewImages(images, i)} title={p}
              className="group relative h-36 w-36 overflow-hidden rounded-2xl border border-line bg-[conic-gradient(#8881_25%,transparent_0_50%,#8881_0_75%,transparent_0)] bg-[length:16px_16px] shadow-sm transition hover:shadow-md sm:h-44 sm:w-44">
              <img src={rawUrl(p)} alt={nameOf(p)} loading="lazy" className="h-full w-full object-contain transition group-hover:scale-[1.03]" />
              <span className="absolute inset-x-0 bottom-0 truncate bg-gradient-to-t from-black/70 to-transparent px-2 pb-1.5 pt-4 text-left text-[11px] font-medium text-white">{nameOf(p)}</span>
            </button>
          ))}
        </div>
      )}
      {pages.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {pages.map((p) => {
            const Icon = fileType(p).icon;
            return (
              <button type="button" key={p} onClick={() => st.browse({ path: p })} title={p}
                className="group flex w-full max-w-sm items-center gap-3 rounded-2xl border border-line bg-elev p-2.5 pr-4 text-left shadow-[0_1px_4px_rgb(0_0_0/0.04)] transition hover:border-subtle hover:shadow-md">
                <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-[#e34f26] text-white shadow-sm"><Icon size={22} /></span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[13.5px] font-semibold">{nameOf(p)}</span>
                  <span className="block truncate text-xs text-subtle">{t("web_page")} · {p}</span>
                </span>
                <span className="shrink-0 rounded-lg bg-hover px-2 py-1 text-[11px] font-medium text-muted group-hover:bg-accent group-hover:text-accent-fg">{t("open_browser")}</span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
