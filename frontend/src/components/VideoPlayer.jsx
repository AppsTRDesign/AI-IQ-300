import { useCallback, useEffect, useRef, useState } from "react";
import {
  AlertTriangle, Camera, Captions, Download, Gauge, Loader2, Maximize, Minimize, Pause, PictureInPicture2, Play,
  Repeat, RotateCcw, RotateCw, Volume1, Volume2, VolumeX,
} from "lucide-react";
import { api } from "../lib/api";
import { useStore, useT } from "../lib/store";

// A full video player: custom controls that hide while watching, seek bar with buffered range, hover time and
// dragging, volume (remembered), speed, loop, subtitles (sidecar .vtt/.srt next to the video), picture-in-picture,
// fullscreen, frame capture and keyboard shortcuts. Broken or unsupported files show a clear message, not a black box.

const fmt = (s) => {
  if (!Number.isFinite(s) || s < 0) return "0:00";
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = String(Math.floor(s % 60)).padStart(2, "0");
  return h ? `${h}:${String(m).padStart(2, "0")}:${sec}` : `${m}:${sec}`;
};
const SPEEDS = [0.25, 0.5, 0.75, 1, 1.25, 1.5, 1.75, 2];
const store = {
  get: (k, d) => { try { const v = localStorage.getItem(k); return v == null ? d : JSON.parse(v); } catch { return d; } },
  set: (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* private mode */ } },
};
// SRT -> WebVTT (browsers only read VTT tracks)
const srtToVtt = (s) => "WEBVTT\n\n" + s.replace(/\r/g, "").replace(/(\d\d:\d\d:\d\d),(\d\d\d)/g, "$1.$2");

function useSubtitles(path) {
  const [subs, setSubs] = useState([]);
  useEffect(() => {
    let alive = true;
    const urls = [];
    const st = useStore.getState();
    const dir = path.includes("/") ? path.slice(0, path.lastIndexOf("/")) : "";
    const base = path.split("/").pop().replace(/\.[^.]+$/, "").toLowerCase();
    api.get(st.fileApi(`/fs/list?path=${encodeURIComponent(dir)}`)).then(async (r) => {
      const files = (r.items || []).filter((e) => !e.dir && ["vtt", "srt"].includes(e.ext) && e.size < 3_000_000);
      // the video's own subtitles first ("clip.tr.vtt", "clip.srt"), then the others in the folder
      files.sort((a, b) => (b.name.toLowerCase().startsWith(base.split("_")[0]) - a.name.toLowerCase().startsWith(base.split("_")[0])));
      const out = [];
      for (const f of files.slice(0, 6)) {
        try {
          const text = await (await fetch(st.fileApi(`/fs/raw?path=${encodeURIComponent(f.path)}`))).text();
          const url = URL.createObjectURL(new Blob([f.ext === "srt" ? srtToVtt(text) : text], { type: "text/vtt" }));
          urls.push(url);
          const lang = (f.name.match(/[._-]([a-z]{2})(?:[._-][a-z]+)?\.(vtt|srt)$/i) || [])[1] || "";
          out.push({ url, label: f.name, lang });
        } catch { /* unreadable subtitle file */ }
      }
      if (alive) setSubs(out);
    }).catch(() => {});
    return () => { alive = false; urls.forEach((u) => URL.revokeObjectURL(u)); };
  }, [path]);
  return subs;
}

export default function VideoPlayer({ url, path }) {
  const t = useT();
  const box = useRef(null);
  const el = useRef(null);
  const bar = useRef(null);
  const hideTimer = useRef(0);
  const [playing, setPlaying] = useState(false);
  const [time, setTime] = useState(0);
  const [dur, setDur] = useState(0);
  const [buffered, setBuffered] = useState(0);
  const [vol, setVol] = useState(() => store.get("aiiq.video.vol", 1));
  const [muted, setMuted] = useState(() => store.get("aiiq.video.muted", false));
  const [speed, setSpeed] = useState(1);
  const [loop, setLoop] = useState(false);
  const [waiting, setWaiting] = useState(true);
  const [error, setError] = useState("");
  const [full, setFull] = useState(false);
  const [show, setShow] = useState(true);
  const [menu, setMenu] = useState(""); // "speed" | "subs"
  const [hover, setHover] = useState(null); // {x, time}
  const [dragging, setDragging] = useState(false);
  const [track, setTrack] = useState(-1);
  const [flash, setFlash] = useState(null); // short center feedback ("+5s", "1.5x", play/pause)
  const [size, setSize] = useState("");
  const subs = useSubtitles(path);

  const v = () => el.current;
  const poke = useCallback(() => {
    setShow(true);
    clearTimeout(hideTimer.current);
    hideTimer.current = setTimeout(() => { if (v() && !v().paused) { setShow(false); setMenu(""); } }, 2600);
  }, []);
  const say = (text) => { setFlash({ text, k: Date.now() }); };
  const toggle = useCallback(() => {
    const m = v();
    if (!m || error) return;
    if (m.paused) m.play().catch(() => {}); else m.pause();
  }, [error]);
  const seekTo = (s) => { const m = v(); if (m && dur) m.currentTime = Math.min(Math.max(0, s), dur); };
  const skip = (d) => { seekTo((v()?.currentTime || 0) + d); say(`${d > 0 ? "+" : ""}${d}s`); };
  const setVolume = (x) => {
    const m = v();
    const n = Math.min(1, Math.max(0, x));
    setVol(n); setMuted(n === 0);
    if (m) { m.volume = n; m.muted = n === 0; }
    store.set("aiiq.video.vol", n); store.set("aiiq.video.muted", n === 0);
  };
  const toggleMute = () => {
    const m = v();
    const next = !muted;
    setMuted(next);
    if (m) m.muted = next;
    if (!next && vol === 0) setVolume(0.6);
    store.set("aiiq.video.muted", next);
  };
  const changeSpeed = (s) => { setSpeed(s); if (v()) v().playbackRate = s; say(`${s}×`); setMenu(""); };
  const fullscreen = () => {
    if (document.fullscreenElement) document.exitFullscreen?.();
    else box.current?.requestFullscreen?.();
  };
  const pip = async () => {
    try {
      if (document.pictureInPictureElement) await document.exitPictureInPicture();
      else await v()?.requestPictureInPicture?.();
    } catch { /* not supported */ }
  };
  const capture = () => {
    const m = v();
    if (!m || !m.videoWidth) return;
    const c = document.createElement("canvas");
    c.width = m.videoWidth; c.height = m.videoHeight;
    try {
      c.getContext("2d").drawImage(m, 0, 0);
      const a = document.createElement("a");
      a.href = c.toDataURL("image/png");
      a.download = `${path.split("/").pop().replace(/\.[^.]+$/, "")}-${fmt(m.currentTime).replace(/:/g, "-")}.png`;
      a.click();
      say(t("video_captured"));
    } catch { /* tainted canvas */ }
  };
  const pickTrack = (i) => {
    setTrack(i); setMenu("");
    const tracks = v()?.textTracks || [];
    for (let k = 0; k < tracks.length; k++) tracks[k].mode = k === i ? "showing" : "disabled";
  };

  // apply the remembered volume once the element exists
  useEffect(() => { const m = v(); if (m) { m.volume = vol; m.muted = muted; } }, []);
  // turn on the first subtitle track when subtitles are found
  useEffect(() => { if (subs.length && track === -1) setTimeout(() => pickTrack(0), 50); }, [subs.length]);
  useEffect(() => {
    const f = () => setFull(!!document.fullscreenElement);
    document.addEventListener("fullscreenchange", f);
    return () => { document.removeEventListener("fullscreenchange", f); clearTimeout(hideTimer.current); };
  }, []);
  useEffect(() => {
    if (!flash) return undefined;
    const id = setTimeout(() => setFlash(null), 650);
    return () => clearTimeout(id);
  }, [flash]);
  // keyboard: space/k play, arrows/j/l seek, up/down volume, m mute, f fullscreen, c subtitles, 0-9 jump, < > speed
  useEffect(() => {
    const k = (e) => {
      if (/^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName) || e.target.isContentEditable || e.ctrlKey || e.metaKey || e.altKey) return;
      const m = v();
      if (!m) return;
      const key = e.key;
      let hit = true;
      if (key === " " || key === "k" || key === "K") toggle();
      else if (key === "ArrowLeft") skip(-5);
      else if (key === "ArrowRight") skip(5);
      else if (key === "j" || key === "J") skip(-10);
      else if (key === "l" || key === "L") skip(10);
      else if (key === "ArrowUp") { setVolume(m.volume + 0.05); say(`${Math.round(Math.min(1, m.volume + 0.05) * 100)}%`); }
      else if (key === "ArrowDown") { setVolume(m.volume - 0.05); say(`${Math.round(Math.max(0, m.volume - 0.05) * 100)}%`); }
      else if (key === "m" || key === "M") toggleMute();
      else if (key === "f" || key === "F") fullscreen();
      else if (key === "c" || key === "C") { if (subs.length) pickTrack(track === -1 ? 0 : -1); }
      else if (key === "Home") seekTo(0);
      else if (key === "End") seekTo(dur - 0.1);
      else if (/^[0-9]$/.test(key)) seekTo((dur * +key) / 10);
      else if (key === ">" || key === ".") { if (m.paused && key === ".") m.currentTime += 1 / 30; else changeSpeed(SPEEDS[Math.min(SPEEDS.length - 1, SPEEDS.indexOf(speed) + 1)]); }
      else if (key === "<" || key === ",") { if (m.paused && key === ",") m.currentTime -= 1 / 30; else changeSpeed(SPEEDS[Math.max(0, SPEEDS.indexOf(speed) - 1)]); }
      else hit = false;
      if (hit) { e.preventDefault(); e.stopPropagation(); poke(); }
    };
    addEventListener("keydown", k, true);
    return () => removeEventListener("keydown", k, true);
  });

  const posTime = (clientX) => {
    const r = bar.current.getBoundingClientRect();
    const x = Math.min(Math.max(0, clientX - r.left), r.width);
    return { x, time: dur ? (x / r.width) * dur : 0 };
  };
  const onBarDown = (e) => {
    if (!dur) return;
    e.preventDefault();
    setDragging(true);
    seekTo(posTime(e.clientX).time);
    const move = (ev) => { const p = posTime(ev.clientX); setHover(p); seekTo(p.time); };
    const up = () => { setDragging(false); setHover(null); removeEventListener("pointermove", move); removeEventListener("pointerup", up); };
    addEventListener("pointermove", move);
    addEventListener("pointerup", up);
  };

  const pct = dur ? (time / dur) * 100 : 0;
  const VolIcon = muted || vol === 0 ? VolumeX : vol < 0.5 ? Volume1 : Volume2;
  const visible = show || !playing || menu || dragging || !!error;
  const btn = "grid h-9 w-9 place-items-center rounded-full text-white/90 transition hover:bg-white/15 hover:text-white";

  return (
    <div ref={box} onMouseMove={poke} onMouseLeave={() => playing && setShow(false)}
      className={`group relative w-full select-none overflow-hidden bg-black ${full ? "h-full" : ""} ${visible ? "video-ui-on" : "cursor-none"}`}>
      <video ref={el} src={url} autoPlay playsInline loop={loop} preload="metadata" crossOrigin="anonymous"
        className={`mx-auto block w-full bg-black ${full ? "h-full object-contain" : "max-h-[74vh]"}`}
        onClick={() => { toggle(); poke(); }} onDoubleClick={fullscreen}
        onPlay={() => { setPlaying(true); poke(); }} onPause={() => { setPlaying(false); setShow(true); }}
        onEnded={() => { setPlaying(false); setShow(true); }}
        onWaiting={() => setWaiting(true)} onPlaying={() => setWaiting(false)} onCanPlay={() => setWaiting(false)}
        onTimeUpdate={(e) => setTime(e.currentTarget.currentTime)}
        onProgress={(e) => { const b = e.currentTarget.buffered; if (b.length && dur) setBuffered((b.end(b.length - 1) / dur) * 100); }}
        onLoadedMetadata={(e) => {
          const m = e.currentTarget;
          setDur(m.duration); setWaiting(false);
          if (m.videoWidth) setSize(`${m.videoWidth}×${m.videoHeight}`);
          else setError(t("video_no_picture"));
        }}
        onError={(e) => {
          const code = e.currentTarget.error?.code;
          setWaiting(false);
          setError(code === 4 ? t("video_unsupported") : t("video_broken"));
        }}>
        {subs.map((s, i) => <track key={s.url} kind="subtitles" src={s.url} label={s.label} srcLang={s.lang || undefined} default={i === 0} />)}
      </video>

      {/* loading / error / feedback in the middle */}
      {waiting && !error && (
        <div className="pointer-events-none absolute inset-0 grid place-items-center"><Loader2 size={44} className="animate-spin text-white/80" /></div>
      )}
      {error && (
        <div className="absolute inset-0 grid place-items-center bg-black/80 p-6 text-center text-white">
          <div className="max-w-sm space-y-3">
            <AlertTriangle size={36} className="mx-auto text-amber-400" />
            <div className="text-[14px] font-semibold">{error}</div>
            <div className="text-[12px] text-white/60">{t("video_error_hint")}</div>
            <a href={url + "&download=true"} className="inline-flex items-center gap-1.5 rounded-full bg-white/15 px-4 py-1.5 text-[12.5px] hover:bg-white/25"><Download size={14} /> {t("download")}</a>
          </div>
        </div>
      )}
      {!playing && !waiting && !error && (
        <button onClick={toggle} aria-label={t("media_play")}
          className="absolute left-1/2 top-1/2 grid h-16 w-16 -translate-x-1/2 -translate-y-1/2 place-items-center rounded-full bg-black/55 text-white shadow-2xl ring-1 ring-white/20 backdrop-blur transition hover:scale-105 hover:bg-accent">
          <Play size={28} fill="currentColor" className="ml-1" />
        </button>
      )}
      {flash && (
        <div key={flash.k} className="pointer-events-none absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 animate-ping-once rounded-2xl bg-black/60 px-4 py-2 font-mono text-[15px] font-semibold text-white">{flash.text}</div>
      )}

      {/* controls */}
      <div className={`absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/85 via-black/40 to-transparent px-3 pb-2 pt-10 transition-opacity duration-200 ${visible ? "opacity-100" : "pointer-events-none opacity-0"}`}>
        <div ref={bar} onPointerDown={onBarDown} onMouseMove={(e) => dur && setHover(posTime(e.clientX))} onMouseLeave={() => !dragging && setHover(null)}
          className="group/bar relative mb-1.5 flex h-4 cursor-pointer items-center">
          <div className="relative h-1 w-full overflow-hidden rounded-full bg-white/20 transition-[height] group-hover/bar:h-1.5">
            <div className="absolute inset-y-0 left-0 bg-white/35" style={{ width: `${buffered}%` }} />
            <div className="absolute inset-y-0 left-0 bg-accent" style={{ width: `${pct}%` }} />
          </div>
          <div className="absolute h-3.5 w-3.5 -translate-x-1/2 scale-0 rounded-full bg-accent shadow transition-transform group-hover/bar:scale-100" style={{ left: `${pct}%`, transform: dragging ? "translateX(-50%) scale(1)" : undefined }} />
          {hover && (
            <div className="pointer-events-none absolute bottom-5 -translate-x-1/2 rounded-md bg-black/85 px-1.5 py-0.5 font-mono text-[11px] text-white" style={{ left: hover.x }}>{fmt(hover.time)}</div>
          )}
        </div>
        <div className="flex items-center gap-0.5 text-white">
          <button onClick={toggle} className={btn} title={`${playing ? t("media_pause") : t("media_play")} (k)`}>
            {playing ? <Pause size={19} fill="currentColor" /> : <Play size={19} fill="currentColor" className="ml-0.5" />}
          </button>
          <button onClick={() => skip(-10)} className={btn} title="-10s (j)"><RotateCcw size={17} /></button>
          <button onClick={() => skip(10)} className={btn} title="+10s (l)"><RotateCw size={17} /></button>
          <div className="group/vol flex items-center">
            <button onClick={toggleMute} className={btn} title={`${t("media_mute")} (m)`}><VolIcon size={18} /></button>
            <input type="range" min={0} max={1} step={0.02} value={muted ? 0 : vol} onChange={(e) => setVolume(+e.target.value)}
              className="video-range w-0 opacity-0 transition-all duration-200 group-hover/vol:w-20 group-hover/vol:opacity-100 focus:w-20 focus:opacity-100" aria-label={t("media_volume")} />
          </div>
          <span className="ml-2 font-mono text-[12px] tabular-nums text-white/85">{fmt(time)} <span className="text-white/45">/ {fmt(dur)}</span></span>
          <div className="flex-1" />
          {size && <span className="mr-1 hidden rounded bg-white/10 px-1.5 py-0.5 font-mono text-[10.5px] text-white/70 sm:inline">{size}</span>}
          {subs.length > 0 && (
            <div className="relative">
              <button onClick={() => setMenu(menu === "subs" ? "" : "subs")} className={`${btn} ${track >= 0 ? "text-accent" : ""}`} title={`${t("video_subtitles")} (c)`}><Captions size={18} /></button>
              {menu === "subs" && (
                <div className="absolute bottom-11 right-0 min-w-44 overflow-hidden rounded-xl bg-black/90 py-1 text-[12.5px] shadow-2xl ring-1 ring-white/10 backdrop-blur">
                  <button onClick={() => pickTrack(-1)} className={`block w-full px-3 py-1.5 text-left hover:bg-white/10 ${track === -1 ? "text-accent" : ""}`}>{t("video_subs_off")}</button>
                  {subs.map((s, i) => (
                    <button key={s.url} onClick={() => pickTrack(i)} className={`block w-full truncate px-3 py-1.5 text-left hover:bg-white/10 ${track === i ? "text-accent" : ""}`}>{s.label}</button>
                  ))}
                </div>
              )}
            </div>
          )}
          <div className="relative">
            <button onClick={() => setMenu(menu === "speed" ? "" : "speed")} className={`${btn} w-auto px-2 font-mono text-[12px]`} title={t("media_speed")}>
              {speed === 1 ? <Gauge size={18} /> : `${speed}×`}
            </button>
            {menu === "speed" && (
              <div className="absolute bottom-11 right-0 overflow-hidden rounded-xl bg-black/90 py-1 text-[12.5px] shadow-2xl ring-1 ring-white/10 backdrop-blur">
                {SPEEDS.map((s) => (
                  <button key={s} onClick={() => changeSpeed(s)} className={`block w-full px-4 py-1.5 text-left font-mono hover:bg-white/10 ${speed === s ? "text-accent" : ""}`}>{s === 1 ? t("video_normal") : `${s}×`}</button>
                ))}
              </div>
            )}
          </div>
          <button onClick={() => { setLoop(!loop); say(loop ? t("video_loop_off") : t("media_loop")); }} className={`${btn} ${loop ? "text-accent" : ""}`} title={t("media_loop")}><Repeat size={17} /></button>
          <button onClick={capture} className={btn} title={t("video_capture")}><Camera size={17} /></button>
          {document.pictureInPictureEnabled && <button onClick={pip} className={btn} title={t("video_pip")}><PictureInPicture2 size={17} /></button>}
          <button onClick={fullscreen} className={btn} title={`${t("video_fullscreen")} (f)`}>{full ? <Minimize size={18} /> : <Maximize size={18} />}</button>
        </div>
      </div>
    </div>
  );
}
