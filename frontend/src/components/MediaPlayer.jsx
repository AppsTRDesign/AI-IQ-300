import { useEffect, useRef, useState } from "react";
import { Download, Gauge, Pause, Play, Repeat, SkipBack, SkipForward, Volume2, VolumeX, X } from "lucide-react";
import { useStore, useT } from "../lib/store";
import { fileType } from "../lib/fileTypes";
import VideoPlayer from "./VideoPlayer";

// Audio and video the agent produced (or files in the working folder): a video player and an audio player with a
// waveform (click to seek), speed, loop, volume and download.

const rawUrl = (path) => useStore.getState().fileApi(`/fs/raw?path=${encodeURIComponent(path)}`);
const nameOf = (path) => path.split(/[\\/]/).pop();
const fmt = (s) => (Number.isFinite(s) ? `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}` : "0:00");
const SPEEDS = [0.5, 0.75, 1, 1.25, 1.5, 2];

function useWaveform(url, bars = 160) {
  const [peaks, setPeaks] = useState(null);
  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const buf = await (await fetch(url)).arrayBuffer();
        const ctx = new (window.AudioContext || window.webkitAudioContext)();
        const audio = await ctx.decodeAudioData(buf);
        const data = audio.getChannelData(0);
        const step = Math.max(1, Math.floor(data.length / bars));
        const out = [];
        for (let i = 0; i < bars; i++) {
          let max = 0;
          for (let j = i * step; j < Math.min(data.length, (i + 1) * step); j += 16) max = Math.max(max, Math.abs(data[j]));
          out.push(max);
        }
        const top = Math.max(...out, 0.01);
        if (alive) setPeaks(out.map((v) => v / top));
        ctx.close();
      } catch { if (alive) setPeaks([]); }
    })();
    return () => { alive = false; };
  }, [url]);
  return peaks;
}

function AudioPlayer({ url }) {
  const t = useT();
  const el = useRef(null);
  const [playing, setPlaying] = useState(false);
  const [time, setTime] = useState(0);
  const [dur, setDur] = useState(0);
  const [speed, setSpeed] = useState(1);
  const [vol, setVol] = useState(1);
  const [loop, setLoop] = useState(false);
  const peaks = useWaveform(url);
  const pct = dur ? time / dur : 0;
  const seek = (e) => {
    const r = e.currentTarget.getBoundingClientRect();
    if (el.current && dur) el.current.currentTime = ((e.clientX - r.left) / r.width) * dur;
  };
  const toggle = () => (el.current.paused ? el.current.play() : el.current.pause());
  useEffect(() => {
    const k = (e) => { if (e.code === "Space" && e.target.tagName !== "INPUT") { e.preventDefault(); toggle(); } };
    addEventListener("keydown", k);
    return () => removeEventListener("keydown", k);
  }, []);
  return (
    <div className="space-y-4">
      <audio ref={el} src={url} loop={loop} preload="metadata" autoPlay
        onPlay={() => setPlaying(true)} onPause={() => setPlaying(false)} onEnded={() => setPlaying(false)}
        onTimeUpdate={(e) => setTime(e.currentTarget.currentTime)} onLoadedMetadata={(e) => setDur(e.currentTarget.duration)} />
      <div onClick={seek} className="relative flex h-28 cursor-pointer items-center gap-[2px] rounded-2xl bg-bg px-3">
        {(peaks?.length ? peaks : Array.from({ length: 160 }, () => 0.15)).map((v, i, a) => (
          <span key={i} className={`flex-1 rounded-full transition-colors ${i / a.length <= pct ? "bg-accent" : "bg-active"} ${peaks === null ? "animate-pulse" : ""}`}
            style={{ height: `${Math.max(6, v * 100)}%` }} />
        ))}
        <span className="pointer-events-none absolute inset-y-2 w-px bg-fg/60" style={{ left: `calc(12px + ${pct} * (100% - 24px))` }} />
      </div>
      <div className="flex items-center justify-between font-mono text-xs text-muted"><span>{fmt(time)}</span><span>{fmt(dur)}</span></div>
      <div className="flex flex-wrap items-center justify-center gap-2">
        <button onClick={() => { el.current.currentTime = Math.max(0, time - 10); }} title="-10s" className="grid h-9 w-9 place-items-center rounded-full hover:bg-hover"><SkipBack size={17} /></button>
        <button onClick={toggle} className="grid h-12 w-12 place-items-center rounded-full bg-accent text-accent-fg shadow-lg shadow-accent/30">
          {playing ? <Pause size={20} fill="currentColor" /> : <Play size={20} fill="currentColor" className="ml-0.5" />}
        </button>
        <button onClick={() => { el.current.currentTime = Math.min(dur, time + 10); }} title="+10s" className="grid h-9 w-9 place-items-center rounded-full hover:bg-hover"><SkipForward size={17} /></button>
      </div>
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-line px-3 py-2 text-[12.5px]">
        <div className="flex items-center gap-2">
          <button onClick={() => { const v = vol ? 0 : 1; setVol(v); el.current.volume = v; }} className="text-muted hover:text-fg">{vol ? <Volume2 size={16} /> : <VolumeX size={16} />}</button>
          <input type="range" className="slider w-28" min={0} max={1} step={0.05} value={vol} onChange={(e) => { setVol(+e.target.value); el.current.volume = +e.target.value; }} />
        </div>
        <div className="flex items-center gap-1">
          <Gauge size={14} className="text-muted" />
          {SPEEDS.map((s) => (
            <button key={s} onClick={() => { setSpeed(s); el.current.playbackRate = s; }}
              className={`rounded-md px-1.5 py-0.5 font-mono text-[11px] ${speed === s ? "bg-accent text-accent-fg" : "text-muted hover:bg-hover"}`}>{s}×</button>
          ))}
        </div>
        <button onClick={() => setLoop(!loop)} title={t("media_loop")} className={`flex items-center gap-1 rounded-md px-2 py-0.5 ${loop ? "bg-accent-soft text-accent" : "text-muted hover:bg-hover"}`}><Repeat size={14} />{t("media_loop")}</button>
      </div>
    </div>
  );
}

export function MediaPlayer() {
  const t = useT();
  const dialog = useStore((s) => s.dialog);
  const close = () => useStore.setState({ dialog: null });
  const url = rawUrl(dialog.path);
  const ft = fileType(dialog.path);
  const Icon = ft.icon;
  const video = dialog.kind === "video";
  useEffect(() => {
    const k = (e) => e.key === "Escape" && close();
    addEventListener("keydown", k);
    return () => removeEventListener("keydown", k);
  }, []);
  return (
    <div role="dialog" aria-modal="true" className="fixed inset-0 z-50 grid place-items-center bg-black/70 p-3 backdrop-blur-sm sm:p-6"
      onMouseDown={(e) => e.target === e.currentTarget && close()}>
      <div className={`fade-in flex max-h-full w-full flex-col overflow-hidden rounded-3xl border border-line bg-elev shadow-2xl ${video ? "max-w-5xl" : "max-w-2xl"}`}>
        <div className="flex items-center gap-3 border-b border-line px-4 py-3">
          <div className="grid h-9 w-9 shrink-0 place-items-center rounded-xl text-white" style={{ background: ft.color }}><Icon size={17} /></div>
          <div className="min-w-0 flex-1">
            <div className="truncate text-[13.5px] font-semibold">{nameOf(dialog.path)}</div>
            <div className="truncate font-mono text-[11px] text-subtle">{dialog.path}</div>
          </div>
          <a href={url + "&download=true"} title={t("download")} className="grid h-8 w-8 place-items-center rounded-lg text-muted hover:bg-hover"><Download size={16} /></a>
          <button onClick={close} className="grid h-8 w-8 place-items-center rounded-lg text-muted hover:bg-hover"><X size={17} /></button>
        </div>
        <div className={video ? "bg-black" : "p-5"}>
          {video
            ? <VideoPlayer url={url} path={dialog.path} />
            : <AudioPlayer url={url} />}
        </div>
      </div>
    </div>
  );
}

export default MediaPlayer;
