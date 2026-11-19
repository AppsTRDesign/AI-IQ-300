import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import {
  Bot, Check, ChevronDown, ChevronLeft, ChevronRight, Copy, Film, Image as ImageIcon, Loader2, Mic, Music2, Pause, Play,
  Plus, Redo2, RotateCcw, Send, SkipBack, Sparkles, Trash2, Type, Undo2, Upload, Wand2, X, ZoomIn, ZoomOut,
} from "lucide-react";
import { useStore, useT } from "../lib/store";
import { api } from "../lib/api";
import { inputCls } from "./ui";
import { VoicePicker } from "./VoiceLibrary";

// Video Studio: a live, interactive editor over the same project file the edit_video tool renders
// (<name>.timeline.json). The browser plays it with the engine's own timing (scene starts, transitions, Ken Burns,
// text animations, effects, music); "Render" makes the final MP4 with ffmpeg. Every text and picture can be dragged
// and styled; the AI box changes the project live (a patch from the model, applied at once).

const IMG = /\.(png|jpe?g|webp|bmp|gif|tiff?)$/i;
const AUD = /\.(mp3|wav|m4a|aac|ogg|flac|opus)$/i;
const kindOf = (p = "") => (IMG.test(p) ? "image" : AUD.test(p) ? "audio" : "video");
const ASPECTS = { "16:9": [1280, 720], "9:16": [720, 1280], "1:1": [1080, 1080], "4:5": [1080, 1350], "4:3": [1280, 960], "21:9": [1680, 720] };
const AUTO_M = ["zoom_in", "pan_right", "zoom_out", "pan_left", "pan_up", "zoom_in", "pan_down", "zoom_out"];
const AUTO_T = ["fade", "slideleft", "circleopen", "smoothleft", "dissolve", "wipeleft", "zoomin", "radial"];
const MOTIONS = ["auto", "zoom_in", "zoom_out", "pan_left", "pan_right", "pan_up", "pan_down", "none"];
const TRANSITIONS = ["auto", "fade", "dissolve", "fadeblack", "fadewhite", "slideleft", "slideright", "slideup", "slidedown",
  "wipeleft", "wiperight", "circleopen", "circleclose", "radial", "smoothleft", "smoothright", "zoomin", "pixelize", "cut"];
const LOOKS = ["none", "warm", "cinematic", "vivid", "bw", "vintage", "cool"];
const LOOK_CSS = {
  none: "", warm: "sepia(0.14) saturate(1.12) contrast(1.05)", cinematic: "contrast(1.1) saturate(0.88) brightness(0.98)",
  vivid: "saturate(1.35) contrast(1.08)", bw: "grayscale(1) contrast(1.15)", vintage: "sepia(0.35) saturate(0.85) contrast(0.95)",
  cool: "hue-rotate(-8deg) saturate(1.05) brightness(1.02)",
};
const VIGNETTE = { cinematic: 0.45, vintage: 0.55 };
const MUSIC = ["", "corporate", "upbeat", "lofi", "cinematic", "acoustic", "electronic", "ambient", "calm"];
const MOODS = ["corporate", "happy", "calm", "cinematic", "acoustic", "electronic", "lofi", "piano", "epic", "romantic"];
const ANIMS = ["fade", "slide_up", "slide_left", "pop", "none"];
export const FONTS = ["sans", "serif", "display", "mono", "script", "condensed"];
export const FONT_CSS = { sans: "Arial, Helvetica, sans-serif", serif: "Georgia, 'Times New Roman', serif", display: "Impact, 'Arial Black', sans-serif",
  mono: "Consolas, 'Courier New', monospace", script: "'Segoe Script', 'Brush Script MT', cursive", condensed: "Bahnschrift, 'Arial Narrow', sans-serif" };
const EFFECTS = ["grain", "old_film", "vhs", "glitch", "shake", "letterbox", "glow", "light_leak", "sepia", "bw", "dreamy", "vignette", "sharpen", "flash_in"];
const SCENE_TEXT = [["title", "vs_title_f"], ["subtitle", "vs_subtitle_f"], ["caption", "vs_caption_f"], ["lower_third", "vs_lower_third_f"], ["text", "vs_text"]];
// what the engine draws for a scene text object without its own style fields (video_edit.STYLE_DEFAULTS)
const STYLE_DEFAULTS = {
  title: { x: "center", y: "38%", size_pct: 9.5, bold: true, animation: "slide_up", align: "center" },
  subtitle: { x: "center", y: "54%", size_pct: 4.5, animation: "slide_up", align: "center", delay: 0.35 },
  caption: { x: "center", y: "82%", size_pct: 4.6, box: "black@0.45", animation: "slide_up", align: "center" },
  lower_third: { x: "5%", y: "76%", size_pct: 5, bold: true, box: "0xE8A33D@0.92", animation: "slide_left" },
  text: { x: "center", y: "82%", size_pct: 4.6, box: "black@0.45", animation: "fade", align: "center" },
};
const TEXT_PRESETS = {
  heading: { x: "center", y: "40%", size_pct: 10, bold: true, animation: "slide_up", align: "center", outline: "black@0.4" },
  caption: { x: "center", y: "80%", size_pct: 4.8, box: "black@0.5", animation: "fade", align: "center" },
  price: { x: "6%", y: "70%", size_pct: 8, bold: true, font: "display", box: "#C0392B@0.92", animation: "pop" },
  quote: { x: "center", y: "44%", size_pct: 6.5, font: "serif", align: "center", animation: "fade" },
  social: { x: "64%", y: "88%", size_pct: 3.6, font: "mono", box: "black@0.55", animation: "slide_left" },
  cta: { x: "center", y: "84%", size_pct: 5.4, bold: true, color: "#111111", box: "#FFD34D@0.95", animation: "pop", align: "center" },
};
const clamp = (v, a, b) => Math.min(b, Math.max(a, v));
const fmt = (s) => `${Math.floor(s / 60)}:${(s % 60).toFixed(1).padStart(4, "0")}`;
const ease = (q) => 1 - Math.pow(1 - clamp(q, 0, 1), 3);
const num = (v, d) => (v === "" || v == null || Number.isNaN(+v) ? d : +v);
const asObj = (v) => (v && typeof v === "object" ? v : { text: v || "" });

// ffmpeg colours ("white", "black@0.5", "#ffcc00", "0xE8A33D@0.9") as CSS
export function cssColor(c = "white") {
  const [base, a] = String(c).split("@");
  const b = base.startsWith("0x") ? "#" + base.slice(2) : base;
  if (a == null) return b;
  if (b.startsWith("#") && b.length === 7) {
    const n = parseInt(b.slice(1), 16);
    return `rgba(${n >> 16},${(n >> 8) & 255},${n & 255},${a})`;
  }
  return `color-mix(in srgb, ${b} ${Math.round(+a * 100)}%, transparent)`;
}
const hexOf = (c, d = "#000000") => {
  const b = String(c || "").split("@")[0];
  if (/^#[0-9a-f]{6}$/i.test(b)) return b;
  if (/^0x[0-9a-f]{6}$/i.test(b)) return "#" + b.slice(2);
  return { white: "#ffffff", black: "#000000", red: "#ff0000", yellow: "#ffff00" }[b] || d;
};
const alphaOf = (c, d = 1) => (String(c || "").includes("@") ? +String(c).split("@")[1] : d);

// The engine's scene timing (video_edit._scene_length / plan): start, length, transition into the next.
function timing(tl, media) {
  const sc = tl.scenes || [];
  let L = 0;
  let prevTd = 0;
  const out = [];
  sc.forEach((s, k) => {
    let dur;
    if (kindOf(s.src) === "image") dur = num(s.dur, 4);
    else {
      const total = (media[s.src]?.duration || 0) - num(s.in, 0);
      dur = s.dur ? (total > 0 ? Math.min(+s.dur, total) : +s.dur) : total > 0 ? total : 4;
    }
    const start = k === 0 ? 0 : L - prevTd;
    L = start + dur;
    let tr = s.transition || tl.transition || "auto";
    if (tr === "auto") tr = AUTO_T[k % AUTO_T.length];
    let td = num(s.transition_dur ?? tl.transition_dur, 0.8);
    if (k + 1 < sc.length) td = Math.min(td, dur / 2, num(sc[k + 1].dur, 4) / 2);
    prevTd = tr === "cut" || tr === "none" ? 0.04 : Math.max(td, 0.05);
    out.push({ start, dur, tr, td: prevTd, motion: s.motion && s.motion !== "auto" ? s.motion : AUTO_M[k % AUTO_M.length] });
  });
  return { scenes: out, L };
}

function totalLength(tl, tm) {
  let end = tm.L;
  for (const c of tl.clips || []) if (!(c._logo && !c.dur)) end = Math.max(end, num(c.start, 0) + num(c.dur, c.type === "text" ? 3 : 5));
  const d = num(tl.duration, 0);
  return d > 0 ? Math.min(d, Math.max(end, 0.5)) : Math.max(end, 0.5);
}

// position of a layer (engine semantics: % or px = top-left, words = edges / centre) as CSS
function posStyle(v, axis, frame) {
  const s = String(v ?? (axis === "x" ? "center" : "bottom")).trim().toLowerCase();
  const pct = s.match(/^(-?\d+(?:\.\d+)?)\s*%$/);
  if (pct) return { [axis === "x" ? "left" : "top"]: `${pct[1]}%` };
  if (/^-?\d+(\.\d+)?$/.test(s)) return { [axis === "x" ? "left" : "top"]: `${(+s / frame) * 100}%` };
  const m = s.match(/^(left|center|middle|right|top|bottom)\s*([+-]\s*\d+)?$/);
  const off = m?.[2] ? (parseFloat(m[2].replace(/\s/g, "")) / frame) * 100 : 0;
  const w = m?.[1] || "center";
  if (axis === "x") {
    if (w === "left") return { left: `${off}%` };
    if (w === "right") return { left: `${100 + off}%`, tx: -100 };
    return { left: `${50 + off}%`, tx: -50 };
  }
  if (w === "top") return { top: `${off}%` };
  if (w === "bottom") return { top: `${100 + off}%`, ty: -100 };
  return { top: `${50 + off}%`, ty: -50 };
}

function useStageSize(ref) {
  const [size, setSize] = useState({ w: 640, h: 360 });
  useLayoutEffect(() => {
    if (!ref.current) return;
    const ro = new ResizeObserver(([e]) => setSize({ w: e.contentRect.width, h: e.contentRect.height }));
    ro.observe(ref.current);
    return () => ro.disconnect();
  }, [ref]);
  return size;
}

// ---------------------------------------------------------------- effects (preview approximations of the ffmpeg ones)
const GRAIN = `url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='160' height='160'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='2' stitchTiles='stitch'/></filter><rect width='100%' height='100%' filter='url(%23n)' opacity='0.55'/></svg>")`;
function fxLook(list = [], t = 0) {
  const f = [];
  let transform = "";
  if (list.includes("sepia") || list.includes("old_film")) f.push("sepia(0.85)");
  if (list.includes("bw")) f.push("grayscale(1) contrast(1.12)");
  if (list.includes("dreamy")) f.push("blur(0.6px) brightness(1.04) saturate(1.12)");
  if (list.includes("glow")) f.push("brightness(1.06) saturate(1.1)");
  if (list.includes("sharpen")) f.push("contrast(1.05)");
  if (list.includes("vhs")) f.push("saturate(0.85) contrast(1.05)");
  if (list.includes("old_film")) f.push(`brightness(${1 + 0.03 * Math.sin(t * 37)})`);
  if (list.includes("glitch") && t % 2.6 < 0.13) { f.push("hue-rotate(80deg) saturate(1.6)"); transform += ` translateX(${Math.sin(t * 90) * 1.5}%)`; }
  if (list.includes("shake")) transform += ` translate(${Math.sin(t * 19) * 1.2}%, ${Math.sin(t * 27) * 1.2}%) scale(1.04)`;
  return { filter: f.join(" "), transform };
}
function FxOverlays({ list = [], t = 0, local = null }) {
  const out = [];
  if (list.includes("grain") || list.includes("old_film") || list.includes("vhs"))
    out.push(<div key="g" className="pointer-events-none absolute inset-0 mix-blend-overlay" style={{ backgroundImage: GRAIN, opacity: list.includes("old_film") ? 0.5 : 0.32, backgroundPosition: `${(t * 997) % 160}px ${(t * 613) % 160}px` }} />);
  if (list.includes("vhs"))
    out.push(<div key="v" className="pointer-events-none absolute inset-0" style={{ background: "repeating-linear-gradient(transparent 0 3px, rgba(0,0,0,.18) 3px 4px)" }} />);
  if (list.includes("vignette") || list.includes("old_film"))
    out.push(<div key="vg" className="pointer-events-none absolute inset-0" style={{ background: "radial-gradient(ellipse at center, transparent 55%, rgba(0,0,0,.5) 100%)" }} />);
  if (list.includes("light_leak"))
    out.push(<div key="l" className="pointer-events-none absolute inset-0 mix-blend-screen" style={{ background: `radial-gradient(circle at ${50 + 35 * Math.sin(t * 0.7)}% ${40 + 25 * Math.cos(t * 0.5)}%, rgba(255,160,64,.5), rgba(255,79,122,.18) 35%, transparent 65%)` }} />);
  if (list.includes("glow"))
    out.push(<div key="gl" className="pointer-events-none absolute inset-0 mix-blend-screen" style={{ background: "radial-gradient(ellipse at center, rgba(255,255,255,.12), transparent 70%)" }} />);
  if (list.includes("letterbox"))
    out.push(<div key="lb" className="pointer-events-none absolute inset-0"><div className="absolute inset-x-0 top-0 h-[11%] bg-black" /><div className="absolute inset-x-0 bottom-0 h-[11%] bg-black" /></div>);
  if (list.includes("flash_in") && local != null && local < 0.35)
    out.push(<div key="f" className="pointer-events-none absolute inset-0 bg-white" style={{ opacity: 1 - local / 0.35 }} />);
  return out;
}

// ---------------------------------------------------------------- texts
// One styled text (object form): the same layout rules as video_edit.free_text
function TextBox({ spec, A, B, t, playing, stage, frame, selected, onDown, onResize, z = 100 }) {
  const anim = spec.animation || "fade";
  const dur = Math.max(B - A, 0.1);
  const fi = num(spec.fade_in, anim === "none" ? 0 : Math.min(0.45, dur / 3));
  const fo = num(spec.fade_out, anim === "none" ? 0 : Math.min(0.35, dur / 3));
  let op = 1;
  if (playing && fi > 0) op = Math.min(op, (t - A) / fi);
  if (playing && fo > 0) op = Math.min(op, (B - t) / fo);
  const e = playing ? ease((t - A) / 0.6) : 1;
  let dx = 0;
  let dy = 0;
  if (anim === "slide_up") dy = stage.h * 0.045 * (1 - e);
  if (anim === "slide_left") dx = -stage.w * 0.12 * (1 - e);
  if (anim === "pop" && playing) dy = -stage.h * 0.02 * Math.sin(clamp((t - A) / 0.35, 0, 1) * Math.PI);
  const px = posStyle(spec.x ?? "center", "x", frame.W);
  const py = posStyle(spec.y ?? "bottom", "y", frame.H);
  const short = Math.min(stage.w, stage.h);
  const fs = spec.size_pct ? (num(spec.size_pct, 5) / 100) * short : (num(spec.size, 48) * stage.w) / frame.W;
  const boxOn = spec.box && !["false", "no", "none"].includes(String(spec.box).toLowerCase());
  const box = boxOn ? (spec.box === true || ["true", "yes"].includes(String(spec.box)) ? "rgba(0,0,0,.5)" : cssColor(spec.box)) : "transparent";
  const outline = spec.outline ? cssColor(spec.outline === true ? "black" : spec.outline) : null;
  const ow = Math.max(1, fs * 0.05);
  const shadows = [spec.shadow === false ? null : "1px 2px 3px rgba(0,0,0,.55)",
    ...(outline ? [`${ow}px 0 ${outline}`, `-${ow}px 0 ${outline}`, `0 ${ow}px ${outline}`, `0 -${ow}px ${outline}`] : [])].filter(Boolean);
  return (
    <div onPointerDown={onDown}
      className={`absolute cursor-move touch-none select-none rounded-sm ${selected ? "outline outline-2 outline-offset-2 outline-accent" : "hover:outline hover:outline-1 hover:outline-white/60"}`}
      style={{ left: px.left, top: py.top, zIndex: z, opacity: clamp(op, 0, 1),
        transform: `translate(${px.tx || 0}%, ${py.ty || 0}%) translate(${dx}px, ${dy}px)`,
        fontSize: fs, color: cssColor(spec.color || "white"), fontWeight: spec.bold ? 700 : 400, fontFamily: FONT_CSS[spec.font || "sans"],
        background: box, padding: boxOn ? `${fs * 0.22}px ${fs * 0.38}px` : 0, textShadow: shadows.join(","), lineHeight: 1.25,
        textAlign: spec.align === "center" ? "center" : "left", whiteSpace: "pre-wrap", maxWidth: (stage.w * num(spec.wrap, 90)) / 100,
        width: "max-content" }}>
      {spec.text || " "}
      {selected && <span onPointerDown={(ev) => { ev.stopPropagation(); onResize(ev); }} className="absolute -bottom-2 -right-2 h-4 w-4 cursor-nwse-resize rounded-full border-2 border-white bg-accent" />}
    </div>
  );
}

// The house styles of plain-string scene texts (video_edit.text_filters); dragging one turns it into an object
// (same look) that can be placed and styled.
function SceneTexts({ s, k, info, t: now, stage, frame, playing, sel, onDown, onResize }) {
  const short = Math.min(stage.w, stage.h);
  const A0 = info.start + (info.start ? 0.35 : 0.25);
  const B = info.start + info.dur - 0.2;
  const t = playing ? now : clamp(now, A0 + 1.2, B);
  const alpha = (a) => (playing ? clamp(Math.min((t - a) / 0.6, (B - t) / 0.5), 0, 1) : 1);
  const rise = (a, d) => (playing ? 1 - ease((t - a) / d) : 0);
  const sh = "0 2px 6px rgba(0,0,0,.6)";
  const out = [];
  for (const [key] of SCENE_TEXT) {
    const v = s[key];
    if (!v || (typeof v === "object" && !String(v.text || "").trim())) continue;
    const selected = sel?.kind === "stext" && sel.i === k && sel.key === key;
    const down = (e) => onDown(e, key);
    const ring = selected ? "outline outline-2 outline-offset-2 outline-accent" : "hover:outline hover:outline-1 hover:outline-white/60";
    if (typeof v === "object") {
      const spec = { ...STYLE_DEFAULTS[key], ...v };
      const A = A0 + num(spec.delay, 0);
      out.push(<TextBox key={key} spec={spec} A={A} B={B} t={now} playing={playing} stage={stage} frame={frame} selected={selected}
        onDown={down} onResize={(e) => onResize(e, key)} z={60 + k} />);
      continue;
    }
    const common = { onPointerDown: down };
    if (key === "title") out.push(<div key={key} {...common} className={`absolute left-1/2 max-w-[90%] cursor-move touch-none select-none text-center font-bold leading-tight text-white ${ring}`} style={{ top: "50%", fontSize: short * 0.095, textShadow: sh, opacity: alpha(A0), transform: `translate(-50%, calc(-50% - ${short * 0.04}px + ${short * 0.05 * rise(A0, 0.8)}px))`, zIndex: 60 + k }}>{v}</div>);
    else if (key === "subtitle") out.push(<div key={key} {...common} className={`absolute left-1/2 max-w-[90%] cursor-move touch-none select-none text-center leading-tight text-white ${ring}`} style={{ top: `calc(50% + ${short * 0.06}px)`, fontSize: short * 0.045, textShadow: sh, opacity: alpha(A0 + 0.35), transform: `translate(-50%, ${short * 0.03 * rise(A0 + 0.35, 0.8)}px)`, zIndex: 60 + k }}>{v}</div>);
    else if (key === "lower_third") out.push(<div key={key} {...common} className={`absolute cursor-move touch-none select-none ${ring}`} style={{ left: stage.w * 0.05, bottom: stage.h * 0.12, opacity: alpha(A0), transform: `translateX(-${rise(A0, 0.7) * 120}%)`, zIndex: 60 + k }}><span className="block rounded-sm px-[0.45em] py-[0.25em] font-bold text-white" style={{ fontSize: short * 0.05, background: "rgba(232,163,61,.92)" }}>{v}</span></div>);
    else out.push(<div key={key} {...common} className={`absolute left-1/2 max-w-[90%] cursor-move touch-none select-none ${ring}`} style={{ bottom: stage.h * 0.08, opacity: alpha(A0), transform: `translate(-50%, ${short * 0.025 * rise(A0, 0.6)}px)`, zIndex: 60 + k }}><span className="block rounded px-[0.5em] py-[0.2em] text-center text-white" style={{ fontSize: short * 0.046, background: "rgba(0,0,0,.45)" }}>{v}</span></div>);
  }
  return out;
}

// ---------------------------------------------------------------- preview layers
function SceneLayer({ s, k, tm, t, url, stage, frame, playing, videoRefs, sceneVol, sel, onTextDown, onTextResize }) {
  const info = tm.scenes[k];
  const local = t - info.start;
  const p = clamp(local / info.dur, 0, 1);
  const prev = k > 0 ? tm.scenes[k - 1] : null;
  const q = prev ? clamp(local / prev.td, 0, 1) : 1;
  const e = ease(q);
  let style = { opacity: 1 };
  if (prev && q < 1) {
    const tr = prev.tr;
    if (tr === "slideleft" || tr === "smoothleft") style = { transform: `translateX(${(1 - e) * 100}%)` };
    else if (tr === "slideright" || tr === "smoothright") style = { transform: `translateX(${-(1 - e) * 100}%)` };
    else if (tr === "slideup") style = { transform: `translateY(${(1 - e) * 100}%)` };
    else if (tr === "slidedown") style = { transform: `translateY(${-(1 - e) * 100}%)` };
    else if (tr === "circleopen" || tr === "radial") style = { clipPath: `circle(${e * 75}% at 50% 50%)` };
    else if (tr === "circleclose") style = { clipPath: `circle(${e * 75}% at 50% 50%)`, opacity: e };
    else if (tr === "wipeleft") style = { clipPath: `inset(0 0 0 ${(1 - e) * 100}%)` };
    else if (tr === "wiperight") style = { clipPath: `inset(0 ${(1 - e) * 100}% 0 0)` };
    else if (tr === "zoomin") style = { opacity: q, transform: `scale(${1 + 0.25 * (1 - e)})` };
    else if (tr === "fadeblack" || tr === "fadewhite") style = { opacity: clamp(q * 2 - 1, 0, 1) };
    else style = { opacity: q };
  }
  const moving = !!s.animated_src; // an AI-animated photo plays its clip
  const kind = moving ? "video" : kindOf(s.src);
  let kb = "";
  if (kind === "image") {
    const m = info.motion;
    const sh = (0.14 / 1.14 / 2) * 100;
    if (m === "zoom_in") kb = `scale(${1 + 0.16 * p})`;
    else if (m === "zoom_out") kb = `scale(${1.16 - 0.16 * p})`;
    else if (m === "pan_right") kb = `scale(1.14) translateX(${sh - 2 * sh * p}%)`;
    else if (m === "pan_left") kb = `scale(1.14) translateX(${-sh + 2 * sh * p}%)`;
    else if (m === "pan_down") kb = `scale(1.14) translateY(${sh - 2 * sh * p}%)`;
    else if (m === "pan_up") kb = `scale(1.14) translateY(${-sh + 2 * sh * p}%)`;
  }
  const fit = s.fit || "cover";
  const objFit = fit === "cover" ? "cover" : "contain";
  const fx = fxLook(s.effects || [], local);
  const media = kind === "image"
    ? <img src={url(s.src)} alt="" draggable={false} className="absolute inset-0 h-full w-full" style={{ objectFit: objFit, transform: kb }} />
    : <video ref={(el) => { if (el) videoRefs.current[k] = el; }} src={url(moving ? s.animated_src : s.src)} muted={!sceneVol || moving} playsInline preload="auto"
        className="absolute inset-0 h-full w-full" style={{ objectFit: objFit }} />;
  return (
    <div className="absolute inset-0 overflow-hidden" style={{ ...style, zIndex: k + 1 }}>
      <div className="absolute inset-0" style={{ filter: fx.filter || undefined, transform: fx.transform || undefined }}>
        {fit === "blur" && <img src={url(s.src)} alt="" className="absolute inset-0 h-full w-full scale-110 object-cover blur-xl brightness-90" />}
        {fit === "contain" && <div className="absolute inset-0 bg-black" />}
        {media}
      </div>
      <FxOverlays list={s.effects || []} t={t} local={local} />
      <SceneTexts s={s} k={k} info={info} t={t} stage={stage} frame={frame} playing={playing} sel={sel}
        onDown={(ev, key) => onTextDown(ev, k, key)} onResize={(ev, key) => onTextResize(ev, k, key)} />
    </div>
  );
}

function ClipLayer({ c, i, t, stage, frame, url, selected, onSelect, onDrag, onResize, playing, T }) {
  const start = num(c.start, 0);
  const dur = c._logo && !c.dur ? T - start : num(c.dur, c.type === "text" ? 3 : 5);
  if (t < start || t > start + dur || c.type === "audio") return null;
  const down = (e) => { e.stopPropagation(); onSelect(); onDrag(e); };
  if (c.type === "text") {
    return <TextBox spec={c} A={start} B={start + dur} t={t} playing={playing} stage={stage} frame={frame} selected={selected}
      onDown={down} onResize={onResize} z={100 + i} />;
  }
  const fi = num(c.fade_in, 0);
  const fo = num(c.fade_out, 0);
  let op = 1;
  if (playing && fi > 0) op = Math.min(op, (t - start) / fi);
  if (playing && fo > 0) op = Math.min(op, (start + dur - t) / fo);
  op = clamp(op, 0, 1) * num(c.opacity, 1);
  const px = posStyle(c.x ?? (c.scale ? "center" : "left"), "x", frame.W);
  const py = posStyle(c.y ?? (c.scale ? "center" : "top"), "y", frame.H);
  const ring = selected ? "outline outline-2 outline-offset-2 outline-accent" : "hover:outline hover:outline-1 hover:outline-white/60";
  const w = c.scale ? `${num(c.scale, 0.25) * 100}%` : "100%";
  return (
    <div onPointerDown={down} className={`absolute cursor-move touch-none select-none ${ring}`}
      style={{ left: px.left, top: py.top, opacity: op, transform: `translate(${px.tx || 0}%, ${py.ty || 0}%)`, zIndex: 100 + i, width: w, height: c.scale ? "auto" : "100%" }}>
      {c.type === "image"
        ? <img src={url(c.src)} alt="" draggable={false} className="pointer-events-none block h-auto w-full" />
        : <video src={url(c.src)} muted playsInline className="pointer-events-none block w-full" />}
      {selected && c.scale && <span onPointerDown={(e) => { e.stopPropagation(); onResize(e); }} className="absolute -bottom-2 -right-2 h-4 w-4 cursor-nwse-resize rounded-full border-2 border-white bg-accent" />}
    </div>
  );
}

// ---------------------------------------------------------------- small inputs
const Field = ({ label, children, wide }) => (
  <label className={`block text-[11.5px] text-muted ${wide ? "col-span-2" : ""}`}><span className="mb-0.5 block">{label}</span>{children}</label>
);
const fieldCls = `${inputCls} !px-2 !py-1.5 !text-[12.5px]`;
function NumIn({ value, onChange, step = 0.1, min = 0, max }) {
  return <input type="number" className={fieldCls} value={value ?? ""} step={step} min={min} max={max}
    onChange={(e) => onChange(e.target.value === "" ? undefined : +e.target.value)} />;
}
function Sel({ value, onChange, options, labels }) {
  return (
    <select className={fieldCls} value={value ?? ""} onChange={(e) => onChange(e.target.value)}>
      {options.map((o) => <option key={o} value={o}>{labels?.[o] ?? (o || "—")}</option>)}
    </select>
  );
}
function Range({ value, onChange, min, max, step }) {
  return (
    <div className="flex items-center gap-2">
      <input type="range" className="min-w-0 flex-1 accent-[var(--accent)]" value={value} min={min} max={max} step={step} onChange={(e) => onChange(+e.target.value)} />
      <span className="w-10 text-right font-mono text-[11px] tabular-nums">{(+value).toFixed(2).replace(/\.?0+$/, "")}</span>
    </div>
  );
}
function Chips({ options, value = [], onChange, label }) {
  const set = new Set(value || []);
  return (
    <div className="flex flex-wrap gap-1">
      {options.map((o) => (
        <button key={o} type="button" onClick={() => { const n = new Set(set); n.has(o) ? n.delete(o) : n.add(o); onChange([...n]); }}
          className={`rounded-md border px-1.5 py-0.5 text-[11px] ${set.has(o) ? "border-accent bg-accent/15 text-accent" : "border-line text-muted hover:bg-hover"}`}>{label(o)}</button>
      ))}
    </div>
  );
}

// all style fields of a text (scene text object or text layer)
function TextStyleFields({ t, v, onChange, labels }) {
  const boxOn = v.box && !["false", "no", "none"].includes(String(v.box).toLowerCase());
  const outOn = !!v.outline;
  return (
    <div className="grid grid-cols-2 gap-2">
      <Field label={t("vs_text")} wide><textarea className={`${fieldCls} h-14`} value={v.text || ""} onChange={(e) => onChange({ text: e.target.value })} /></Field>
      <Field label={t("vs_size")} wide><Range value={num(v.size_pct, 5)} min={1.5} max={30} step={0.5} onChange={(x) => onChange({ size_pct: x, size: undefined })} /></Field>
      <Field label={t("vs_color")}><input type="color" className="h-8 w-full cursor-pointer rounded-lg border border-line bg-bg" value={hexOf(v.color, "#ffffff")} onChange={(e) => onChange({ color: e.target.value })} /></Field>
      <Field label={t("vs_font")}><Sel value={v.font || "sans"} onChange={(x) => onChange({ font: x })} options={FONTS} labels={labels(FONTS, "vs_font_")} /></Field>
      <Field label={t("vs_animation")}><Sel value={v.animation || "fade"} onChange={(x) => onChange({ animation: x })} options={ANIMS} labels={labels(ANIMS, "vs_a_")} /></Field>
      <Field label={t("vs_align")}><Sel value={v.align || "left"} onChange={(x) => onChange({ align: x })} options={["left", "center"]} labels={{ left: t("vs_align_left"), center: t("vs_align_center") }} /></Field>
      <label className="flex items-center gap-2 text-[12px]"><input type="checkbox" checked={!!v.bold} onChange={(e) => onChange({ bold: e.target.checked || undefined })} />{t("vs_bold")}</label>
      <label className="flex items-center gap-2 text-[12px]"><input type="checkbox" checked={v.shadow !== false} onChange={(e) => onChange({ shadow: e.target.checked ? undefined : false })} />{t("vs_shadow")}</label>
      <label className="col-span-2 flex items-center gap-2 text-[12px]"><input type="checkbox" checked={!!boxOn} onChange={(e) => onChange({ box: e.target.checked ? "black@0.5" : false })} />{t("vs_box")}</label>
      {boxOn && <>
        <Field label={t("vs_box_color")}><input type="color" className="h-8 w-full cursor-pointer rounded-lg border border-line bg-bg" value={hexOf(v.box)} onChange={(e) => onChange({ box: `${e.target.value}@${alphaOf(v.box, 0.5)}` })} /></Field>
        <Field label={t("vs_box_alpha")}><Range value={alphaOf(v.box, 0.5)} min={0.05} max={1} step={0.05} onChange={(x) => onChange({ box: `${hexOf(v.box)}@${x}` })} /></Field>
      </>}
      <label className="col-span-2 flex items-center gap-2 text-[12px]"><input type="checkbox" checked={outOn} onChange={(e) => onChange({ outline: e.target.checked ? "black" : undefined })} />{t("vs_outline")}</label>
      {outOn && <Field label={t("vs_outline_color")} wide><input type="color" className="h-8 w-full cursor-pointer rounded-lg border border-line bg-bg" value={hexOf(v.outline)} onChange={(e) => onChange({ outline: e.target.value })} /></Field>}
      <Field label="X"><input className={fieldCls} value={v.x ?? ""} onChange={(e) => onChange({ x: e.target.value })} /></Field>
      <Field label="Y"><input className={fieldCls} value={v.y ?? ""} onChange={(e) => onChange({ y: e.target.value })} /></Field>
    </div>
  );
}

// voice-over clip: text read by a chosen free neural voice, placed on the timeline at the playhead
function VoiceOverPanel({ t, st, onAdd, defaultVoice, onClose }) {
  const [text, setText] = useState("");
  const [voice, setVoice] = useState(defaultVoice || {});
  const [busy, setBusy] = useState(false);
  const make = async () => {
    if (!text.trim()) return;
    setBusy(true);
    try {
      const r = await api.post(st.fileApi("/video/voice"), { text: text.trim(), voice: voice.voice || "", rate: num(voice.rate, 1) });
      onAdd(r);
      setText("");
    } catch (e) { st.notify(t("vs_voice_failed"), "error", e.message); }
    finally { setBusy(false); }
  };
  return (
    <div className="space-y-2">
      <div className="flex items-center"><h3 className="mr-auto text-[13px] font-semibold">{t("vs_voiceover")}</h3>
        <button onClick={onClose} className="rounded-lg p-1 text-muted hover:bg-hover"><X size={15} /></button></div>
      <p className="text-[11.5px] leading-snug text-subtle">{t("vs_voiceover_desc")}</p>
      <textarea className={`${fieldCls} h-20`} value={text} onChange={(e) => setText(e.target.value)} placeholder={t("vs_voiceover_ph")} />
      <VoicePicker value={voice} onChange={setVoice} sample={text} />
      <button onClick={make} disabled={busy || !text.trim()} className="flex w-full items-center justify-center gap-1.5 rounded-lg bg-accent py-2 text-[12.5px] font-medium text-accent-fg disabled:opacity-50">
        {busy ? <Loader2 size={14} className="animate-spin" /> : <Mic size={14} />}{t("vs_voiceover_add")}</button>
    </div>
  );
}

// ---------------------------------------------------------------- the studio
export default function VideoStudio() {
  const t = useT();
  const st = useStore.getState();
  const dialog = useStore((s) => s.dialog);
  const sessionId = useStore((s) => s.sessionId);
  const projectId = useStore((s) => s.projectId);
  const run = useStore((s) => (s.sessionId ? s.runs?.[s.sessionId] : null));
  const [tl, setTlRaw] = useState(null);
  const [project, setProject] = useState(null);
  const [mediaList, setMediaList] = useState([]);
  const [sel, setSel] = useState(null); // {kind: "scene"|"clip"|"music"|"project"|"stext", i, key}
  const [time, setTime] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [pps, setPps] = useState(40);
  const [saved, setSaved] = useState("saved");
  const [render, setRender] = useState(null);
  const [side, setSide] = useState("props"); // props | media | voice
  const [binFilter, setBinFilter] = useState("all");
  const [presets, setPresets] = useState(false);
  const [ai, setAi] = useState("");
  const [aiBusy, setAiBusy] = useState(false);
  const [aiLog, setAiLog] = useState([]);
  const [agent, setAgent] = useState(false); // the chat agent works on this project (new media etc.)
  const [mobileAi, setMobileAi] = useState(false);
  const hist = useRef({ past: [], future: [] });
  const lastLocal = useRef(0);
  const lastSaved = useRef("");
  const stageRef = useRef(null);
  const stageBox = useRef(null);
  const videoRefs = useRef({});
  const musicRef = useRef(null);
  const audioRefs = useRef({});
  const logEnd = useRef(null);
  const timelineRef = useRef(null);
  const propsRef = useRef(null);
  const stage = useStageSize(stageRef);

  const raw = useCallback((p) => st.fileApi(`/fs/raw?path=${encodeURIComponent(p)}`), [st]);
  const media = useMemo(() => Object.fromEntries(mediaList.map((m) => [m.path, m])), [mediaList]);
  const loadMedia = useCallback(() => api.get(st.fileApi("/video/media")).then((r) => setMediaList(r.media || [])).catch(() => {}), [st]);
  const log = (role, text, extra = {}) => setAiLog((l) => [...l.slice(-40), { role, text, at: Date.now(), ...extra }]);

  useEffect(() => {
    api.get(st.fileApi(`/video/project?path=${encodeURIComponent(dialog?.path || "")}`)).then((r) => {
      setTlRaw(r.timeline);
      setProject(r.project);
      lastSaved.current = JSON.stringify(r.timeline);
      if (!r.timeline.scenes?.length && !r.timeline.clips?.length) setSide("media");
    }).catch((e) => st.notify(t("vs_open_failed"), "error", e.message));
    loadMedia();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const setTl = (fn, keepHistory = true) => setTlRaw((cur) => {
    const next = typeof fn === "function" ? fn(cur) : fn;
    if (keepHistory && cur) {
      hist.current.past = [...hist.current.past.slice(-60), cur];
      hist.current.future = [];
    }
    lastLocal.current = Date.now();
    return next;
  });
  const undo = () => { const h = hist.current; if (!h.past.length) return; setTlRaw((cur) => { h.future.push(cur); return h.past.pop(); }); lastLocal.current = Date.now(); };
  const redo = () => { const h = hist.current; if (!h.future.length) return; setTlRaw((cur) => { h.past.push(cur); return h.future.pop(); }); lastLocal.current = Date.now(); };

  // autosave (1.2 s after the last change)
  useEffect(() => {
    if (!tl) return;
    const s = JSON.stringify(tl);
    if (s === lastSaved.current) return;
    setSaved("saving");
    const h = setTimeout(async () => {
      try {
        const r = await api.put(st.fileApi("/video/project"), { timeline: tl, project_id: projectId || null });
        lastSaved.current = s;
        if (r.project) setProject(r.project);
        setSaved("saved");
      } catch { setSaved("error"); }
    }, 1200);
    return () => clearTimeout(h);
  }, [tl]); // eslint-disable-line react-hooks/exhaustive-deps

  // live: the project file changed by the agent (edit_video saves it before rendering) arrives here
  const agentRunning = agent && run?.status === "running";
  useEffect(() => {
    if (!project) return;
    const h = setInterval(async () => {
      if (!agentRunning) loadMedia();
      if (Date.now() - lastLocal.current < 5000 || render?.busy) return;
      try {
        const r = await api.get(st.fileApi(`/video/project?path=${encodeURIComponent(project)}`));
        const s = JSON.stringify(r.timeline);
        if (s !== lastSaved.current) {
          lastSaved.current = s;
          setTlRaw((cur) => { hist.current.past.push(cur); return r.timeline; });
          loadMedia();
          log("ai", t("vs_ai_updated"));
        }
      } catch { /* offline for a moment */ }
    }, agentRunning ? 1500 : 4000);
    return () => clearInterval(h);
  }, [project, render?.busy, agentRunning]); // eslint-disable-line react-hooks/exhaustive-deps

  // the agent's steps, live
  const steps = run?.steps || [];
  const lastStep = steps[steps.length - 1];
  useEffect(() => {
    if (!agent || !lastStep) return;
    log("step", `${lastStep.title || lastStep.kind}`, { status: lastStep.status });
  }, [agent, steps.length]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (agent && run && run.status !== "running") {
      setAgent(false);
      log("ai", run.text ? String(run.text).slice(0, 400) : t("vs_ai_agent_done"));
      loadMedia();
    }
  }, [run?.status]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { logEnd.current?.scrollIntoView({ block: "end" }); }, [aiLog.length]);

  const frame = useMemo(() => {
    if (!tl) return { W: 1280, H: 720 };
    const [W, H] = tl.width && tl.height ? [+tl.width, +tl.height] : ASPECTS[tl.aspect || "16:9"] || ASPECTS["16:9"];
    return { W, H };
  }, [tl]);
  const tm = useMemo(() => (tl ? timing(tl, media) : { scenes: [], L: 0 }), [tl, media]);
  const T = useMemo(() => (tl ? totalLength(tl, tm) : 1), [tl, tm]);

  // playback clock
  useEffect(() => {
    if (!playing) return;
    let last = performance.now();
    let raf;
    const tick = (now) => {
      const dt = (now - last) / 1000;
      last = now;
      setTime((x) => {
        const n = x + dt;
        if (n >= T) { setPlaying(false); return T; }
        return n;
      });
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [playing, T]);

  // keep videos and sounds in step with the clock
  useEffect(() => {
    if (!tl) return;
    (tl.scenes || []).forEach((s, k) => {
      const el = videoRefs.current[k];
      const info = tm.scenes[k];
      const moving = !!s.animated_src;
      if (!el || !info || (!moving && kindOf(s.src) !== "video")) return;
      const active = time >= info.start && time < info.start + info.dur;
      const rate = moving && el.duration ? clamp(el.duration / info.dur, 0.4, 1) : 1;
      if (moving && Math.abs(el.playbackRate - rate) > 0.01) el.playbackRate = rate;
      const want = (moving ? 0 : num(s.in, 0)) + clamp(time - info.start, 0, info.dur) * rate;
      if (playing && active) {
        if (el.paused) el.play().catch(() => {});
        if (Math.abs(el.currentTime - want) > 0.35) el.currentTime = want;
      } else {
        if (!el.paused) el.pause();
        if (Math.abs(el.currentTime - want) > 0.05) el.currentTime = want;
      }
    });
    const sync = (el, inPt, start, dur, vol, fi, fo) => {
      if (!el) return;
      const local = time - start;
      const on = local >= 0 && local < dur;
      let v = clamp(vol, 0, 1);
      if (fi > 0) v *= clamp(local / fi, 0, 1);
      if (fo > 0) v *= clamp((dur - local) / fo, 0, 1);
      el.volume = clamp(v, 0, 1);
      const len = el.duration || 0;
      let want = inPt + Math.max(local, 0);
      if (len && el.loop) want %= len;
      if (playing && on) {
        if (el.paused) el.play().catch(() => {});
        if (Math.abs(el.currentTime - want) > 0.35) el.currentTime = want;
      } else if (!el.paused) el.pause();
    };
    const m = tl.music && (typeof tl.music === "string" ? { src: tl.music } : tl.music);
    if (m?.src) {
      const span = T - num(m.start, 0);
      sync(musicRef.current, num(m.in, 0), num(m.start, 0), span, num(m.volume, hasVoice(tl) ? 0.22 : 0.45) * 1.6, num(m.fade_in, Math.min(1.2, span / 4)), num(m.fade_out, Math.min(2.5, span / 3)));
    }
    (tl.clips || []).forEach((c, i) => {
      if (c.type === "audio") sync(audioRefs.current[i], num(c.in, 0), num(c.start, 0), num(c.dur, media[c.src]?.duration || 5), num(c.volume, 1), num(c.fade_in, 0), num(c.fade_out, 0));
    });
  }, [time, playing, tl, tm, T, media]);

  useEffect(() => {
    const k = (e) => {
      if (/input|textarea|select/i.test(e.target.tagName)) return;
      if (e.key === " ") { e.preventDefault(); toggle(); }
      else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z") { e.preventDefault(); e.shiftKey ? redo() : undo(); }
      else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "y") { e.preventDefault(); redo(); }
      else if ((e.key === "Delete" || e.key === "Backspace") && sel) { e.preventDefault(); removeSel(); }
      else if (e.key === "Escape") { if (sel) setSel(null); else close(); }
    };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  });

  const close = () => { setPlaying(false); useStore.setState({ dialog: null }); };
  const toggle = () => { if (time >= T - 0.05) setTime(0); setPlaying((p) => !p); };
  const showProps = () => { setSide("props"); setMobileAi(false); };
  // Whatever is clicked (on the preview or the timeline) opens its settings: the playhead moves into it when it is not
  // on screen, the timeline scrolls to its block and the settings panel scrolls to the top.
  const spanOf = (s) => {
    if (!tl || !s) return null;
    if (s.kind === "scene" || s.kind === "stext") return tm.scenes[s.i] ? [tm.scenes[s.i].start, tm.scenes[s.i].dur] : null;
    if (s.kind === "clip" && tl.clips?.[s.i]) {
      const c = tl.clips[s.i];
      const a = num(c.start, 0);
      return [a, c._logo && !c.dur ? T - a : num(c.dur, c.type === "text" ? 3 : 5)];
    }
    if (s.kind === "music" && tl.music) { const a = num(tl.music.start, 0); return [a, T - a]; }
    return null;
  };
  const focus = (next, { seek = true } = {}) => {
    setSel(next);
    showProps();
    const sp = spanOf(next);
    if (seek && sp && (time < sp[0] || time >= sp[0] + sp[1])) {
      setPlaying(false);
      setTime(clamp(sp[0] + Math.min(0.6, sp[1] / 2), 0, T));
    }
    requestAnimationFrame(() => {
      propsRef.current?.scrollTo({ top: 0, behavior: "smooth" });
      const el = timelineRef.current;
      if (sp && el) {
        const a = sp[0] * pps + 72;
        const b = (sp[0] + sp[1]) * pps + 72;
        if (a < el.scrollLeft + 72 || a > el.scrollLeft + el.clientWidth - 40) el.scrollTo({ left: Math.max(0, a - 96), behavior: "smooth" });
        else if (b < el.scrollLeft) el.scrollTo({ left: Math.max(0, a - 96), behavior: "smooth" });
      }
    });
  };
  // a click on the picture itself (not on a text or layer) opens the scene on screen
  const sceneAt = (x) => tm.scenes.findIndex((s) => x >= s.start && x < s.start + s.dur);

  // ------------------------------------------------ edits
  const clean = (o) => Object.fromEntries(Object.entries(o).filter(([, v]) => v !== undefined && v !== ""));
  const upd = (kind, i, patch) => setTl((cur) => {
    if (kind === "project") return clean({ ...cur, ...patch });
    if (kind === "music") {
      const m = typeof cur.music === "string" ? { src: cur.music } : cur.music || {};
      return { ...cur, music: { ...m, ...patch } };
    }
    const key = kind === "scene" ? "scenes" : "clips";
    return { ...cur, [key]: cur[key].map((x, j) => (j === i ? clean({ ...x, ...patch }) : x)) };
  });
  // a scene text: string (house style) or object; style changes make it an object
  const updText = (k, key, patch) => setTl((cur) => ({
    ...cur,
    scenes: cur.scenes.map((s, j) => {
      if (j !== k) return s;
      const old = s[key];
      if (patch.__reset) return { ...s, [key]: asObj(old).text || undefined };
      const onlyText = Object.keys(patch).length === 1 && "text" in patch && typeof old !== "object";
      if (onlyText) return clean({ ...s, [key]: patch.text });
      return { ...s, [key]: clean({ ...asObj(old), ...patch }) };
    }),
  }));
  const removeSel = () => {
    if (!sel) return;
    if (sel.kind === "music") setTl((c) => ({ ...c, music: null }));
    else if (sel.kind === "stext") setTl((c) => ({ ...c, scenes: c.scenes.map((s, j) => (j === sel.i ? clean({ ...s, [sel.key]: undefined }) : s)) }));
    else if (sel.kind !== "project") {
      const key = sel.kind === "scene" ? "scenes" : "clips";
      setTl((c) => ({ ...c, [key]: c[key].filter((_, j) => j !== sel.i) }));
    }
    setSel(null);
  };
  const duplicate = () => {
    if (!sel || !["scene", "clip"].includes(sel.kind)) return;
    const key = sel.kind === "scene" ? "scenes" : "clips";
    setTl((c) => { const a = [...c[key]]; a.splice(sel.i + 1, 0, { ...a[sel.i], ...(key === "clips" ? { start: num(a[sel.i].start, 0) + 0.5 } : {}) }); return { ...c, [key]: a }; });
  };
  const moveScene = (d) => {
    if (sel?.kind !== "scene") return;
    const j = sel.i + d;
    setTl((c) => { const a = [...c.scenes]; if (j < 0 || j >= a.length) return c; [a[sel.i], a[j]] = [a[j], a[sel.i]]; return { ...c, scenes: a }; });
    setSel({ kind: "scene", i: clamp(sel.i + d, 0, tl.scenes.length - 1) });
  };
  const addMedia = (m, as) => {
    const k = m.kind;
    if (as === "music" || (k === "audio" && as !== "clip")) {
      setTl((c) => ({ ...c, music: { src: m.path, volume: 0.45 } }));
      setSel({ kind: "music" });
    } else if (as === "layer") {
      setTl((c) => ({ ...c, clips: [...(c.clips || []), k === "audio"
        ? { type: "audio", src: m.path, start: +time.toFixed(2), dur: m.duration || 5, volume: 1 }
        : { type: k, src: m.path, start: +time.toFixed(2), dur: k === "video" ? Math.min(m.duration || 5, 8) : Math.max(2, T - time), scale: 0.22, x: "72%", y: "6%" }] }));
      setSel({ kind: "clip", i: (tl.clips || []).length });
    } else if (k !== "audio") {
      setTl((c) => ({ ...c, scenes: [...(c.scenes || []), k === "image" ? { src: m.path, dur: 4 } : { src: m.path, dur: Math.min(m.duration || 6, 12) }] }));
      setSel({ kind: "scene", i: (tl.scenes || []).length });
    } else {
      setTl((c) => ({ ...c, clips: [...(c.clips || []), { type: "audio", src: m.path, start: +time.toFixed(2), dur: m.duration || 5, volume: 1 }] }));
    }
  };
  const addText = (preset = "caption") => {
    const p = TEXT_PRESETS[preset] || TEXT_PRESETS.caption;
    setTl((c) => ({ ...c, clips: [...(c.clips || []), { type: "text", ...p, text: t(`vs_preset_${preset}_text`), start: +time.toFixed(2), dur: 3 }] }));
    setSel({ kind: "clip", i: (tl.clips || []).length });
    setPresets(false);
    showProps();
  };
  const addVoiceClip = (r) => {
    setTl((c) => ({ ...c, clips: [...(c.clips || []), { type: "audio", src: r.path, start: +time.toFixed(2), dur: r.duration || 4, volume: 1, name: "voice" }] }));
    loadMedia();
    log("ai", t("vs_voiceover_added", { s: (r.duration || 0).toFixed(1) }));
  };

  // ------------------------------------------------ dragging on the preview (top-left in % of the frame)
  const dragRect = (onMove) => (e) => {
    const box = stageBox.current.getBoundingClientRect();
    const el = e.currentTarget.getBoundingClientRect();
    const ox = e.clientX - el.left;
    const oy = e.clientY - el.top;
    const sx = e.clientX;
    const sy = e.clientY;
    let first = true;
    const move = (ev) => {
      if (first && Math.hypot(ev.clientX - sx, ev.clientY - sy) < 3) return; // a click, not a drag
      const x = clamp(((ev.clientX - ox - box.left) / box.width) * 100, -50, 100);
      const y = clamp(((ev.clientY - oy - box.top) / box.height) * 100, -50, 100);
      onMove(`${x.toFixed(1)}%`, `${y.toFixed(1)}%`, first);
      first = false;
    };
    const up = () => { window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", up); window.removeEventListener("pointercancel", up); };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
    window.addEventListener("pointercancel", up);
  };
  const dragLayer = (i) => dragRect((x, y, first) =>
    setTl((c) => ({ ...c, clips: c.clips.map((x0, j) => (j === i ? { ...x0, x, y } : x0)) }), first));
  const resizeLayer = (i) => (e) => {
    const box = stageBox.current.getBoundingClientRect();
    const c0 = tl.clips[i];
    const sx = e.clientX;
    const sy = e.clientY;
    let first = true;
    const move = (ev) => {
      const patch = c0.type === "text"
        ? { size_pct: +clamp(num(c0.size_pct, 5) + ((ev.clientY - sy) / box.height) * 60, 1.5, 30).toFixed(1), size: undefined }
        : { scale: +clamp(num(c0.scale, 0.25) + (ev.clientX - sx) / box.width, 0.03, 1).toFixed(3) };
      setTl((c) => ({ ...c, clips: c.clips.map((x0, j) => (j === i ? clean({ ...x0, ...patch }) : x0)) }), first);
      first = false;
    };
    const up = () => { window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", up); window.removeEventListener("pointercancel", up); };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
    window.addEventListener("pointercancel", up);
  };
  const textDown = (e, k, key) => {
    e.stopPropagation();
    focus({ kind: "stext", i: k, key }, { seek: false });
    dragRect((x, y, first) => setTl((c) => ({
      ...c,
      scenes: c.scenes.map((s, j) => {
        if (j !== k) return s;
        const v = s[key];
        const base = v && typeof v === "object" ? v : { ...STYLE_DEFAULTS[key], text: v || "" };
        return { ...s, [key]: { ...base, x, y } };
      }),
    }), first))(e);
  };
  const textResize = (e, k, key) => {
    const box = stageBox.current.getBoundingClientRect();
    const v0 = asObj(tl.scenes[k][key]);
    const s0 = num(v0.size_pct, STYLE_DEFAULTS[key].size_pct);
    const sy = e.clientY;
    let first = true;
    const move = (ev) => {
      const size = +clamp(s0 + ((ev.clientY - sy) / box.height) * 60, 1.5, 30).toFixed(1);
      setTl((c) => ({ ...c, scenes: c.scenes.map((s, j) => (j === k ? { ...s, [key]: { ...STYLE_DEFAULTS[key], ...asObj(s[key]), size_pct: size } } : s)) }), first);
      first = false;
    };
    const up = () => { window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", up); window.removeEventListener("pointercancel", up); };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
    window.addEventListener("pointercancel", up);
  };

  // timeline drags: move a layer / the music, stretch a block, trim its start
  const dragBlock = (kind, i, mode) => (e) => {
    e.stopPropagation();
    e.preventDefault();
    focus(kind === "music" ? { kind } : { kind, i });
    const sx = e.clientX;
    const item = kind === "music" ? (typeof tl.music === "string" ? { src: tl.music } : tl.music) : kind === "scene" ? tl.scenes[i] : tl.clips[i];
    const s0 = num(item.start, 0);
    const d0 = kind === "scene" ? tm.scenes[i].dur : item._logo && !item.dur ? T - s0 : num(item.dur, 5);
    const in0 = num(item.in, 0);
    const srcLen = media[item.src]?.duration || 0;
    const move = (ev) => {
      const ds = Math.round(((ev.clientX - sx) / pps) * 20) / 20;
      let patch;
      if (mode === "move") patch = { start: +Math.max(0, s0 + ds).toFixed(2) };
      else if (mode === "end") {
        let d = Math.max(0.3, d0 + ds);
        if (srcLen && kindOf(item.src) !== "image" && kind !== "music" && !item.animated_src) d = Math.min(d, srcLen - in0);
        patch = { dur: +d.toFixed(2) };
      } else {
        const dd = clamp(ds, -Math.min(in0, s0), d0 - 0.3);
        patch = kind === "music" ? { in: +Math.max(0, in0 + ds).toFixed(2) } : { in: +(in0 + dd).toFixed(2), start: +(s0 + (kind === "clip" ? dd : 0)).toFixed(2), dur: +(d0 - dd).toFixed(2) };
      }
      upd(kind, i, patch);
    };
    const up = () => { window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", up); window.removeEventListener("pointercancel", up); };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
    window.addEventListener("pointercancel", up);
  };
  const scrub = (e) => {
    const box = e.currentTarget.getBoundingClientRect();
    const go = (ev) => setTime(clamp((ev.clientX - box.left - 72) / pps, 0, T)); // 72 px: the track labels
    setPlaying(false);
    go(e);
    const up = () => { window.removeEventListener("pointermove", go); window.removeEventListener("pointerup", up); };
    window.addEventListener("pointermove", go);
    window.addEventListener("pointerup", up);
  };

  // ------------------------------------------------ render / upload / AI
  const doRender = async () => {
    setPlaying(false);
    setRender({ busy: true, started: Date.now(), animate: !!tl.animate || (tl.scenes || []).some((s) => s.animate && !s.animated_src) });
    try {
      const r = await api.post(st.fileApi("/video/render"), { timeline: tl, project_id: projectId || null });
      setRender({ result: r });
      if (r.project) setProject(r.project);
      loadMedia();
      // the render filled in the animated clips: reload the project so the preview plays them
      const p = await api.get(st.fileApi(`/video/project?path=${encodeURIComponent(r.project || project || "")}`)).catch(() => null);
      if (p?.timeline) { lastSaved.current = JSON.stringify(p.timeline); setTlRaw(p.timeline); }
    } catch (e) { setRender({ error: e.message }); }
  };
  const upload = async (files) => {
    for (const f of files) {
      const fd = new FormData();
      fd.append("file", f);
      try {
        await fetch(st.fileApi(`/fs/upload?path=media`), { method: "POST", body: fd });
      } catch (e) { st.notify(t("vs_upload_failed"), "error", e.message); }
    }
    loadMedia();
  };
  const sendToAgent = async (request) => {
    if (!sessionId) { st.notify(t("vs_no_chat"), "error"); return; }
    const p = project || (tl.output || "videos/studio.mp4").replace(/\.\w+$/, ".timeline.json");
    await api.put(st.fileApi("/video/project"), { timeline: tl, project_id: projectId || null }).catch(() => {});
    st.send(t("vs_ai_prompt", { project: p, output: tl.output || "videos/studio.mp4", request }));
    setAgent(true);
    log("ai", t("vs_ai_sent"));
  };
  const askAi = async () => {
    const request = ai.trim();
    if (!request || aiBusy) return;
    setAi("");
    log("user", request);
    setAiBusy(true);
    try {
      const r = await api.post(st.fileApi("/video/ai"), { timeline: tl, request, model: st.currentModel(), project_id: projectId || null,
        lang: st.prefs?.lang });
      if (r.need_agent) {
        log("ai", r.message || t("vs_ai_need_agent"));
        await sendToAgent(request);
      } else {
        setTl(r.timeline);
        log("ai", r.message || t("vs_ai_applied"), { ms: r.ms });
        if (r.ignored?.length) log("warn", t("vs_ai_ignored", { keys: r.ignored.join(", ") }));
      }
    } catch (e) {
      log("warn", e.detail && e.detail !== e.message ? `${e.message} · ${String(e.detail).slice(0, 200)}` : e.message);
    } finally { setAiBusy(false); }
  };

  if (!tl) {
    return <div className="fixed inset-0 z-50 grid place-items-center bg-bg"><Loader2 className="animate-spin text-accent" /></div>;
  }

  const music = tl.music && (typeof tl.music === "string" ? { src: tl.music } : tl.music);
  const musicUrl = music?.src ? (MUSIC.includes(music.src) ? `/api/video/music?kind=${music.src}&seconds=${Math.ceil(T + 2)}&seed=${music.seed || 0}` : raw(music.src)) : "";
  const sceneVolDefault = !music?.src && !hasVoice(tl);
  const selItem = sel?.kind === "scene" ? tl.scenes[sel.i] : sel?.kind === "clip" ? tl.clips[sel.i] : sel?.kind === "music" ? music
    : sel?.kind === "stext" ? tl.scenes[sel.i]?.[sel.key] : null;
  const fadeOn = tl.fade ?? (tl.scenes || []).length > 0;
  const globalOp = fadeOn && playing ? clamp(Math.min(time / 0.6, (T - time) / 0.8), 0, 1) : 1;
  const ratio = frame.W / frame.H;
  const labels = (keys, prefix) => Object.fromEntries(keys.map((k) => [k, t(prefix + (k || "none"))]));
  const width = Math.max(T * pps + 80, 600);
  const toolBtn = "flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-[12px] hover:bg-hover sm:px-2 sm:py-1";
  const lbl = "hidden sm:inline"; // phones: colored icons only (the title tells what they do)

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-bg text-fg" onDragOver={(e) => e.preventDefault()}
      onDrop={(e) => { e.preventDefault(); if (e.dataTransfer.files?.length) upload([...e.dataTransfer.files]); }}>
      <header className="flex shrink-0 items-center gap-2 border-b border-line px-3 py-2">
        <button onClick={close} className="rounded-lg p-1.5 text-muted hover:bg-hover" title={t("vs_close")}><X size={18} /></button>
        <Film size={17} className="text-violet-500" />
        <span className="font-semibold">{t("vs_title")}</span>
        <span className="hidden truncate font-mono text-[11px] text-subtle sm:inline">{project || tl.output}</span>
        <span className={`hidden text-[11px] sm:inline ${saved === "error" ? "text-danger" : "text-subtle"}`}>{t(`vs_${saved}`)}</span>
        {(aiBusy || agentRunning) && <span className="flex items-center gap-1 rounded-md bg-accent/10 px-1.5 py-0.5 text-[11px] text-accent"><Loader2 size={11} className="animate-spin" />{t("vs_ai_working")}</span>}
        <div className="ml-auto flex items-center gap-1">
          <button onClick={undo} className="rounded-lg p-1.5 text-muted hover:bg-hover" title={`${t("vs_undo")} (Ctrl+Z)`}><Undo2 size={16} /></button>
          <button onClick={redo} className="rounded-lg p-1.5 text-muted hover:bg-hover" title={`${t("vs_redo")} (Ctrl+Y)`}><Redo2 size={16} /></button>
          <button onClick={doRender} disabled={render?.busy || !(tl.scenes?.length || tl.clips?.length)}
            className="flex items-center gap-1.5 rounded-xl bg-accent px-3 py-1.5 text-[13px] font-medium text-accent-fg disabled:opacity-50">
            {render?.busy ? <Loader2 size={14} className="animate-spin" /> : <Wand2 size={14} />}<span className="hidden sm:inline">{t("vs_render")}</span>
          </button>
        </div>
      </header>

      <div className="flex min-h-0 flex-1 flex-col lg:flex-row">
        {/* phones: picture, controls and timeline keep their height; the settings panel below gets the rest and scrolls */}
        <section className="flex shrink-0 flex-col lg:min-h-0 lg:flex-1 lg:shrink">
          <div ref={stageRef} className="relative flex h-[32vh] min-h-[170px] shrink-0 items-center justify-center bg-[#0b0b0f] p-1.5 sm:p-3 lg:h-auto lg:min-h-[200px] lg:flex-1"
            onPointerDown={() => setSel(null)}>
            <div ref={stageBox} className="relative isolate overflow-hidden bg-black shadow-2xl"
              onPointerDown={(e) => { e.stopPropagation(); const k = sceneAt(time); if (k >= 0) focus({ kind: "scene", i: k }, { seek: false }); else setSel(null); }}
              style={{ aspectRatio: `${frame.W} / ${frame.H}`, width: `min(100%, ${Math.max(stage.h - (stage.w < 640 ? 12 : 24), 40) * ratio}px)` }}>
              <StageInner tl={tl} tm={tm} time={time} raw={raw} frame={frame} sel={sel} setSel={(s) => focus(s, { seek: false })} playing={playing}
                videoRefs={videoRefs} sceneVol={sceneVolDefault} dragLayer={dragLayer} resizeLayer={resizeLayer} globalOp={globalOp} T={T}
                onTextDown={textDown} onTextResize={textResize} />
              {!(tl.scenes?.length || tl.clips?.length) && (
                <div className="absolute inset-0 grid place-items-center p-4 text-center text-[13px] text-white/70">
                  <div><Upload className="mx-auto mb-2" />{t("vs_empty")}</div>
                </div>
              )}
            </div>
          </div>
          <div className="flex shrink-0 flex-wrap items-center gap-0.5 border-t border-line px-1.5 py-1 sm:gap-1.5 sm:px-3 sm:py-1.5">
            <button onClick={() => { setTime(0); setPlaying(false); }} className="rounded-lg p-1.5 hover:bg-hover"><SkipBack size={16} /></button>
            <button onClick={toggle} className="grid h-8 w-8 place-items-center rounded-full bg-fg text-bg">{playing ? <Pause size={15} /> : <Play size={15} className="ml-0.5" />}</button>
            <span className="font-mono text-[11px] tabular-nums text-muted sm:text-[12px]">{fmt(time)} / {fmt(T)}</span>
            <div className="ml-auto flex items-center gap-0.5 sm:hidden">
              <button onClick={() => setPps((p) => Math.max(10, p / 1.4))} className="rounded-lg p-1.5 hover:bg-hover"><ZoomOut size={15} /></button>
              <button onClick={() => setPps((p) => Math.min(200, p * 1.4))} className="rounded-lg p-1.5 hover:bg-hover"><ZoomIn size={15} /></button>
            </div>
            <div className="mx-1 hidden h-5 w-px bg-line sm:block" />
            <div className="flex w-full items-center justify-between gap-0.5 sm:contents">
            <button title={t("vs_media")} onClick={() => { setBinFilter("all"); if (side === "media") showProps(); else { setSide("media"); setMobileAi(false); } }} className={`${toolBtn} ${side === "media" ? "bg-active" : ""}`}><Plus size={14} className="text-sky-500" /><span className={lbl}>{t("vs_media")}</span></button>
            <div className="relative">
              <button title={t("vs_add_text")} onClick={() => setPresets(!presets)} className={toolBtn}><Type size={14} className="text-blue-500" /><span className={lbl}>{t("vs_add_text")}</span><ChevronDown size={12} /></button>
              {presets && (
                <div className="absolute bottom-full left-0 z-[70] mb-1 w-52 rounded-xl border border-line bg-elev p-1 shadow-xl">
                  {Object.keys(TEXT_PRESETS).map((p) => (
                    <button key={p} onClick={() => addText(p)} className="flex w-full items-center justify-between rounded-lg px-2 py-1.5 text-left text-[12.5px] hover:bg-hover">
                      <span>{t(`vs_preset_${p}`)}</span>
                      <span className="rounded px-1 text-[10px]" style={{ fontFamily: FONT_CSS[TEXT_PRESETS[p].font || "sans"], background: TEXT_PRESETS[p].box ? cssColor(TEXT_PRESETS[p].box) : "transparent", color: TEXT_PRESETS[p].color || (TEXT_PRESETS[p].box ? "#fff" : "inherit"), fontWeight: TEXT_PRESETS[p].bold ? 700 : 400 }}>Aa</span>
                    </button>
                  ))}
                </div>
              )}
            </div>
            <button title={t("vs_add_image")} onClick={() => { setBinFilter("image"); setSide("media"); setMobileAi(false); }} className={toolBtn}><ImageIcon size={14} className="text-violet-500" /><span className={lbl}>{t("vs_add_image")}</span></button>
            <button title={t("vs_voiceover")} onClick={() => { if (side === "voice") showProps(); else { setSide("voice"); setMobileAi(false); } }} className={`${toolBtn} ${side === "voice" ? "bg-active" : ""}`}><Mic size={14} className="text-emerald-500" /><span className={lbl}>{t("vs_voiceover")}</span></button>
            <button title={t("vs_music")} onClick={() => { if (!music?.src) setTl((c) => ({ ...c, music: { src: "ambient", volume: 0.45 } })); focus({ kind: "music" }, { seek: false }); }}
              className={`${toolBtn} ${sel?.kind === "music" && !mobileAi && side === "props" ? "bg-active" : ""}`}><Music2 size={14} className="text-amber-500" /><span className={lbl}>{t("vs_music")}</span></button>
            <button title={t("vs_project")} onClick={() => focus({ kind: "project" })} className={`${toolBtn} ${(!sel || sel.kind === "project") && !mobileAi && side === "props" ? "bg-active" : ""}`}><Sparkles size={14} className="text-pink-500" /><span className={lbl}>{t("vs_project")}</span></button>
            <button onClick={() => setMobileAi(!mobileAi)} className={`${toolBtn} lg:hidden ${mobileAi ? "bg-active" : ""}`}><Bot size={14} className="text-accent" />AI</button>
            </div>
            <div className="ml-auto hidden items-center gap-1 sm:flex">
              <button onClick={() => setPps((p) => Math.max(10, p / 1.4))} className="rounded-lg p-1.5 hover:bg-hover"><ZoomOut size={15} /></button>
              <button onClick={() => setPps((p) => Math.min(200, p * 1.4))} className="rounded-lg p-1.5 hover:bg-hover"><ZoomIn size={15} /></button>
            </div>
          </div>
          <div ref={timelineRef} className="relative max-h-[24vh] shrink-0 overflow-auto overscroll-contain border-t border-line bg-elev/50 lg:max-h-[34vh]">
            <div className="relative select-none" style={{ width }} onPointerDown={scrub}>
              <Ruler T={T} pps={pps} />
              <Track label={t("vs_scenes")} icon={Film}>
                {(tl.scenes || []).map((s, k) => {
                  const info = tm.scenes[k];
                  if (!info) return null;
                  const active = (sel?.kind === "scene" || sel?.kind === "stext") && sel.i === k;
                  const label = [s.title, s.caption, s.lower_third].map((v) => (v && typeof v === "object" ? v.text : v)).find(Boolean);
                  return (
                    <div key={k} onPointerDown={(e) => { e.stopPropagation(); focus({ kind: "scene", i: k }); }}
                      className={`absolute top-1 bottom-1 [@media(pointer:coarse)]:touch-pan-x overflow-hidden rounded-md border text-[10.5px] text-white ${active ? "border-accent ring-2 ring-accent/40" : "border-white/20"}`}
                      style={{ left: info.start * pps, width: Math.max(info.dur * pps - 2, 8), zIndex: active ? 5 : 1 }}>
                      {kindOf(s.src) === "image" ? <img src={raw(s.src)} alt="" className="absolute inset-0 h-full w-full object-cover opacity-70" draggable={false} />
                        : <video src={`${raw(s.src)}#t=${num(s.in, 0) + 0.2}`} muted preload="metadata" className="absolute inset-0 h-full w-full object-cover opacity-70" />}
                      <span className="relative block truncate bg-black/45 px-1">{k + 1}. {label || s.src.split("/").pop()}</span>
                      {k > 0 && <span className="absolute bottom-0 left-0 bg-accent/90 px-1 text-[9px]">{tm.scenes[k - 1].tr}</span>}
                      <span className="absolute bottom-0 right-4 flex gap-0.5 text-[9px]">{s.animate && <span title={t("vs_animate")}>{s.animated_src ? "🎬" : "✨"}</span>}{s.say && <span>🎙</span>}{s.effects?.length ? <span>fx</span> : null}</span>
                      <span onPointerDown={dragBlock("scene", k, "end")} className="absolute inset-y-0 right-0 z-[2] w-2.5 touch-none cursor-ew-resize [@media(pointer:coarse)]:w-5 bg-white/30 hover:bg-accent" />
                    </div>
                  );
                })}
              </Track>
              {(tl.clips || []).map((c, i) => (
                <Track key={i} label={c.type === "text" ? t("vs_text") : c.type === "audio" ? (c.name === "voice" ? t("vs_voiceover") : t("vs_sound")) : c._logo ? "Logo" : t("vs_layer")} icon={c.type === "text" ? Type : c.type === "audio" ? (c.name === "voice" ? Mic : Music2) : ImageIcon} small>
                  <div onPointerDown={dragBlock("clip", i, "move")}
                    className={`absolute top-1 bottom-1 [@media(pointer:coarse)]:touch-pan-x cursor-grab overflow-hidden rounded-md text-[10.5px] text-white ${c.type === "text" ? "bg-sky-600/80" : c.type === "audio" ? "bg-emerald-600/80" : "bg-violet-600/80"} ${sel?.kind === "clip" && sel.i === i ? "ring-2 ring-accent" : ""}`}
                    style={{ left: num(c.start, 0) * pps, width: Math.max((c._logo && !c.dur ? T - num(c.start, 0) : num(c.dur, c.type === "text" ? 3 : 5)) * pps, 10) }}>
                    {c.type !== "text" && <span onPointerDown={dragBlock("clip", i, "trim")} className="absolute inset-y-0 left-0 z-[2] w-2.5 touch-none cursor-ew-resize [@media(pointer:coarse)]:w-5 bg-white/30 hover:bg-accent" />}
                    <span className="block truncate px-2.5 leading-[22px]">{c.type === "text" ? c.text : (c.src || "").split("/").pop()}</span>
                    <span onPointerDown={dragBlock("clip", i, "end")} className="absolute inset-y-0 right-0 z-[2] w-2.5 touch-none cursor-ew-resize [@media(pointer:coarse)]:w-5 bg-white/30 hover:bg-accent" />
                  </div>
                </Track>
              ))}
              {music?.src && (
                <Track label={t("vs_music")} icon={Music2} small>
                  <div onPointerDown={dragBlock("music", 0, "move")}
                    className={`absolute top-1 bottom-1 [@media(pointer:coarse)]:touch-pan-x cursor-grab overflow-hidden rounded-md bg-amber-600/80 text-[10.5px] text-white ${sel?.kind === "music" ? "ring-2 ring-accent" : ""}`}
                    style={{ left: num(music.start, 0) * pps, width: Math.max((T - num(music.start, 0)) * pps, 10) }}>
                    <span onPointerDown={dragBlock("music", 0, "trim")} className="absolute inset-y-0 left-0 z-[2] w-2.5 touch-none cursor-ew-resize [@media(pointer:coarse)]:w-5 bg-white/30 hover:bg-accent" title={t("vs_trim")} />
                    <span className="block truncate px-2.5 leading-[22px]">♪ {MUSIC.includes(music.src) ? t(`vs_music_${music.src}`) : music.src.split("/").pop()}{num(music.in, 0) ? ` · ${t("vs_in")} ${num(music.in, 0)}s` : ""}</span>
                  </div>
                </Track>
              )}
              <div className="pointer-events-none absolute inset-y-0 w-px bg-red-500" style={{ left: time * pps + 72 }}>
                <span className="absolute -top-0.5 -translate-x-1/2 border-x-[5px] border-t-[7px] border-x-transparent border-t-red-500" />
              </div>
            </div>
          </div>
        </section>

        <aside className="flex min-h-0 w-full flex-1 flex-col border-t border-line lg:w-[350px] lg:flex-none lg:border-l lg:border-t-0">
          <div ref={propsRef} className={`min-h-0 flex-1 overflow-y-auto overscroll-contain p-3 ${mobileAi ? "hidden lg:block" : ""}`}>
            {side === "media" ? (
              <MediaBin list={mediaList} raw={raw} t={t} onAdd={addMedia} onUpload={upload} filter={binFilter} setFilter={setBinFilter} onClose={showProps} />
            ) : side === "voice" ? (
              <VoiceOverPanel t={t} st={st} onAdd={addVoiceClip} defaultVoice={tl.voice && typeof tl.voice === "object" ? tl.voice : tl.voice ? { voice: tl.voice } : {}} onClose={showProps} />
            ) : (
              <Inspector t={t} sel={sel} item={selItem} tl={tl} tm={tm} media={mediaList} upd={upd} updText={updText} labels={labels}
                onDelete={removeSel} onDuplicate={duplicate} onMove={moveScene} setSel={setSel} />
            )}
          </div>
          <div className={`shrink-0 border-t border-line ${mobileAi ? "flex min-h-0 flex-1 flex-col" : "hidden lg:block"}`}>
            {aiLog.length > 0 && (
              <div className="max-h-44 min-h-0 flex-1 space-y-1 overflow-y-auto px-2 pt-2 text-[11.5px]">
                {aiLog.map((m, n) => (
                  <div key={n} className={m.role === "user" ? "ml-6 rounded-lg bg-accent/10 px-2 py-1" : m.role === "warn" ? "rounded-lg bg-warn/10 px-2 py-1 text-warn"
                    : m.role === "step" ? "flex items-center gap-1 px-1 text-muted" : "mr-4 rounded-lg bg-hover px-2 py-1"}>
                    {m.role === "step" && (m.status === "running" ? <Loader2 size={10} className="animate-spin" /> : <Check size={10} className="text-ok" />)}
                    {m.role === "ai" && <Bot size={11} className="mr-1 inline text-accent" />}{m.text}{m.ms ? <span className="ml-1 text-subtle">· {(m.ms / 1000).toFixed(1)} s</span> : null}
                  </div>
                ))}
                <div ref={logEnd} />
              </div>
            )}
            <div className="flex items-end gap-1.5 p-2">
              <Bot size={16} className="mb-2 shrink-0 text-accent" />
              <textarea value={ai} onChange={(e) => setAi(e.target.value)} rows={1} placeholder={t("vs_ai_placeholder")}
                onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); askAi(); } }}
                className={`${inputCls} max-h-24 min-h-[36px] resize-none !py-2 !text-[12.5px]`} />
              <button onClick={askAi} disabled={!ai.trim() || aiBusy} className="mb-0.5 rounded-lg bg-accent p-2 text-accent-fg disabled:opacity-40">
                {aiBusy ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />}</button>
            </div>
          </div>
        </aside>
      </div>

      {musicUrl && <audio ref={musicRef} src={musicUrl} loop preload="auto" />}
      {(tl.clips || []).map((c, i) => c.type === "audio" && c.src
        ? <audio key={i} ref={(el) => { audioRefs.current[i] = el; }} src={raw(c.src)} preload="auto" /> : null)}

      {render && !render.busy && (render.result || render.error) && <RenderResult r={render} raw={raw} t={t} onClose={() => setRender(null)} />}
      {render?.busy && <RenderBusy started={render.started} animate={render.animate} t={t} />}
    </div>
  );
}

const hasVoice = (tl) => !!(tl.voiceover || (tl.scenes || []).some((s) => s.say));

function StageInner({ tl, tm, time, raw, frame, sel, setSel, playing, videoRefs, sceneVol, dragLayer, resizeLayer, globalOp, T, onTextDown, onTextResize }) {
  const ref = useRef(null);
  const size = useStageSize(ref);
  const vign = VIGNETTE[tl.look];
  const gfx = fxLook(tl.effects || [], time);
  return (
    <div ref={ref} className="absolute inset-0" style={{ opacity: globalOp, transform: gfx.transform || undefined }}>
      <div className="absolute inset-0" style={{ filter: [LOOK_CSS[tl.look || "none"], gfx.filter].filter(Boolean).join(" ") || undefined }}>
        {(tl.scenes || []).map((s, k) => {
          const info = tm.scenes[k];
          if (!info || time < info.start - 0.01 || time > info.start + info.dur + 0.01) {
            const moving = s.animated_src;
            return moving || kindOf(s.src) === "video" ? <video key={k} ref={(el) => { if (el) videoRefs.current[k] = el; }} src={raw(moving || s.src)} muted preload="auto" className="hidden" /> : null;
          }
          return <SceneLayer key={k} s={s} k={k} tm={tm} t={time} url={raw} stage={size} frame={frame} playing={playing} videoRefs={videoRefs}
            sceneVol={sceneVol && num(s.volume, 1) > 0} sel={sel} onTextDown={onTextDown} onTextResize={onTextResize} />;
        })}
        {vign && <div className="pointer-events-none absolute inset-0" style={{ zIndex: 90, background: `radial-gradient(ellipse at center, transparent 55%, rgba(0,0,0,${vign}) 100%)` }} />}
      </div>
      <div className="pointer-events-none absolute inset-0" style={{ zIndex: 95 }}><FxOverlays list={tl.effects || []} t={time} /></div>
      {(tl.clips || []).map((c, i) => (
        <ClipLayer key={i} c={c} i={i} t={time} stage={size} frame={frame} url={raw} selected={sel?.kind === "clip" && sel.i === i}
          onSelect={() => setSel({ kind: "clip", i })} onDrag={dragLayer(i)} onResize={resizeLayer(i)} playing={playing} T={T} />
      ))}
    </div>
  );
}

function Ruler({ T, pps }) {
  const step = pps >= 80 ? 1 : pps >= 30 ? 2 : pps >= 15 ? 5 : 10;
  const marks = [];
  for (let s = 0; s <= T + step; s += step) marks.push(s);
  return (
    <div className="sticky top-0 z-10 h-5 border-b border-line bg-elev pl-[72px] text-[10px] text-subtle">
      <div className="relative h-full">
        {marks.map((s) => <span key={s} className="absolute top-0 h-full border-l border-line pl-0.5" style={{ left: s * pps }}>{s}s</span>)}
      </div>
    </div>
  );
}

function Track({ label, icon: Icon, children, small }) {
  return (
    <div className={`relative flex border-b border-line/60 ${small ? "h-7" : "h-14"}`}>
      <div className="sticky left-0 z-10 flex w-[72px] shrink-0 items-center gap-1 border-r border-line bg-elev px-1.5 text-[10.5px] text-muted">
        <Icon size={12} className="shrink-0" /><span className="truncate">{label}</span>
      </div>
      <div className="relative flex-1">{children}</div>
    </div>
  );
}

function MediaBin({ list, raw, t, onAdd, onUpload, onClose, filter, setFilter }) {
  const input = useRef(null);
  const shown = list.filter((m) => filter === "all" || m.kind === filter);
  return (
    <div className="space-y-2">
      <div className="flex items-center gap-1.5">
        <span className="text-[13px] font-semibold">{t("vs_media")}</span>
        <button onClick={() => input.current.click()} className="ml-auto flex items-center gap-1 rounded-lg bg-accent px-2 py-1 text-[12px] text-accent-fg"><Upload size={13} />{t("vs_upload")}</button>
        <button onClick={onClose} className="rounded-lg p-1 text-muted hover:bg-hover"><X size={15} /></button>
        <input ref={input} type="file" multiple accept="image/*,video/*,audio/*" className="hidden" onChange={(e) => { onUpload([...e.target.files]); e.target.value = ""; }} />
      </div>
      <div className="flex gap-1">
        {["all", "image", "video", "audio"].map((f) => <button key={f} onClick={() => setFilter(f)} className={`rounded-md px-2 py-0.5 text-[11px] ${filter === f ? "bg-active font-medium" : "text-muted hover:bg-hover"}`}>{t(`vs_f_${f}`)}</button>)}
      </div>
      <p className="text-[11px] leading-snug text-subtle">{t(filter === "image" ? "vs_logo_hint" : "vs_drop")}</p>
      {shown.length === 0 && <p className="py-6 text-center text-[12px] text-muted">{t("vs_no_media")}</p>}
      <div className="grid grid-cols-2 gap-2">
        {shown.map((m) => (
          <div key={m.path} className="group overflow-hidden rounded-xl border border-line bg-elev">
            <div className="relative aspect-video bg-[repeating-conic-gradient(#8882_0_25%,transparent_0_50%)] bg-[length:12px_12px]">
              {m.kind === "image" && <img src={raw(m.path)} alt="" loading="lazy" className="h-full w-full object-contain" />}
              {m.kind === "video" && <video src={`${raw(m.path)}#t=0.5`} muted preload="metadata" className="h-full w-full bg-black object-cover" />}
              {m.kind === "audio" && <div className="grid h-full place-items-center bg-black text-white/70"><Music2 /></div>}
              {m.duration > 0 && <span className="absolute bottom-1 right-1 rounded bg-black/70 px-1 font-mono text-[10px] text-white">{m.duration.toFixed(1)}s</span>}
            </div>
            <div className="truncate px-1.5 pt-1 text-[10.5px] text-muted" title={m.path}>{m.path.split("/").pop()}</div>
            <div className="flex gap-1 p-1.5 pt-1">
              {m.kind !== "audio" && <button onClick={() => onAdd(m, "scene")} className="flex-1 rounded-md bg-hover py-0.5 text-[10.5px] hover:bg-active">{t("vs_as_scene")}</button>}
              <button onClick={() => onAdd(m, m.kind === "audio" ? "music" : "layer")} className="flex-1 rounded-md bg-hover py-0.5 text-[10.5px] hover:bg-active">{t(m.kind === "audio" ? "vs_as_music" : "vs_as_layer")}</button>
              {m.kind === "audio" && <button onClick={() => onAdd(m, "clip")} className="flex-1 rounded-md bg-hover py-0.5 text-[10.5px] hover:bg-active">{t("vs_as_sound")}</button>}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function Inspector({ t, sel, item, tl, tm, media, upd, updText, labels, onDelete, onDuplicate, onMove, setSel }) {
  const mediaPaths = media.map((m) => m.path);
  const fxLabel = (o) => t(`vs_fx_${o}`);
  if (!sel || sel.kind === "project") {
    return (
      <div className="space-y-3">
        <h3 className="text-[13px] font-semibold">{t("vs_project")}</h3>
        <div className="grid grid-cols-2 gap-2">
          <Field label={t("vs_aspect")}><Sel value={tl.aspect || "16:9"} onChange={(v) => upd("project", 0, { aspect: v, width: undefined, height: undefined })} options={Object.keys(ASPECTS)} /></Field>
          <Field label={t("vs_look")}><Sel value={tl.look || "none"} onChange={(v) => upd("project", 0, { look: v })} options={LOOKS} labels={labels(LOOKS, "vs_look_")} /></Field>
          <Field label={t("vs_transition")}><Sel value={tl.transition || "auto"} onChange={(v) => upd("project", 0, { transition: v })} options={TRANSITIONS} /></Field>
          <Field label={t("vs_transition_dur")}><NumIn value={tl.transition_dur ?? 0.8} step={0.1} max={3} onChange={(v) => upd("project", 0, { transition_dur: v })} /></Field>
          <Field label={t("vs_quality")}><Sel value={tl.quality || "good"} onChange={(v) => upd("project", 0, { quality: v })} options={["good", "fast", "small"]} labels={labels(["good", "fast", "small"], "vs_q_")} /></Field>
          <Field label={t("vs_global_fade")}><Sel value={String(tl.fade ?? true)} onChange={(v) => upd("project", 0, { fade: v === "true" })} options={["true", "false"]} labels={{ true: t("vs_on"), false: t("vs_off") }} /></Field>
          <Field label={t("vs_output")} wide><input className={fieldCls} value={tl.output || ""} onChange={(e) => upd("project", 0, { output: e.target.value })} /></Field>
        </div>
        <h4 className="pt-1 text-[12px] font-semibold">{t("vs_effects")}</h4>
        <Chips options={EFFECTS} value={tl.effects} onChange={(v) => upd("project", 0, { effects: v.length ? v : undefined })} label={fxLabel} />
        <label className="flex items-start gap-2 rounded-xl bg-hover/60 p-2 text-[12px]">
          <input type="checkbox" className="mt-0.5" checked={!!tl.animate} onChange={(e) => upd("project", 0, { animate: e.target.checked || undefined })} />
          <span><b>{t("vs_animate_all")}</b><span className="block text-[11px] text-muted">{t("vs_animate_note")}</span></span>
        </label>
        <h4 className="pt-1 text-[12px] font-semibold">{t("vs_voice_title")}</h4>
        <VoicePicker value={tl.voice && typeof tl.voice === "object" ? tl.voice : tl.voice ? { voice: tl.voice } : {}}
          onChange={(v) => upd("project", 0, { voice: v })} sample={(tl.scenes || []).map((s) => s.say).find(Boolean)} />
        <p className="text-[11.5px] leading-snug text-subtle">{t("vs_select_hint")}</p>
        <div className="rounded-xl bg-hover/60 p-2.5 text-[11.5px] leading-snug text-muted">{t("vs_stats", { scenes: (tl.scenes || []).length, layers: (tl.clips || []).length, sec: tm.L.toFixed(1) })}</div>
      </div>
    );
  }
  const head = (title) => (
    <div className="flex items-center gap-1">
      <h3 className="mr-auto text-[13px] font-semibold">{title}</h3>
      {sel.kind === "scene" && <><button onClick={() => onMove(-1)} className="rounded p-1 hover:bg-hover"><ChevronLeft size={15} /></button><button onClick={() => onMove(1)} className="rounded p-1 hover:bg-hover"><ChevronRight size={15} /></button></>}
      {["scene", "clip"].includes(sel.kind) && <button onClick={onDuplicate} title={t("vs_duplicate")} className="rounded p-1 hover:bg-hover"><Copy size={14} /></button>}
      <button onClick={onDelete} title={t("vs_delete")} className="rounded p-1 text-danger hover:bg-hover"><Trash2 size={14} /></button>
    </div>
  );
  if (sel.kind === "stext") {
    const key = sel.key;
    const v = { ...STYLE_DEFAULTS[key], ...asObj(item) };
    return (
      <div className="space-y-3">
        {head(`${t("vs_scene")} ${sel.i + 1} · ${t(SCENE_TEXT.find(([k]) => k === key)?.[1] || "vs_text")}`)}
        <TextStyleFields t={t} v={v} labels={labels} onChange={(p) => updText(sel.i, key, p)} />
        <div className="flex gap-1.5">
          <button onClick={() => setSel({ kind: "scene", i: sel.i })} className="flex-1 rounded-lg bg-hover py-1.5 text-[12px] hover:bg-active">{t("vs_back_scene")}</button>
          {item && typeof item === "object" && <button onClick={() => updText(sel.i, key, { __reset: true })}
            className="flex flex-1 items-center justify-center gap-1 rounded-lg bg-hover py-1.5 text-[12px] hover:bg-active"><RotateCcw size={12} />{t("vs_reset_style")}</button>}
        </div>
        <p className="text-[11.5px] leading-snug text-subtle">{t("vs_drag_hint")}</p>
      </div>
    );
  }
  if (!item) return null;
  const u = (patch) => upd(sel.kind, sel.i, patch);
  if (sel.kind === "music") {
    return (
      <div className="space-y-3">
        {head(t("vs_music"))}
        <div className="grid grid-cols-2 gap-2">
          <Field label={t("vs_source")} wide>
            <select className={fieldCls} value={item.src} onChange={(e) => u({ src: e.target.value })}>
              {MUSIC.filter(Boolean).map((m) => <option key={m} value={m}>{t(`vs_music_${m}`)}</option>)}
              {media.filter((m) => m.kind === "audio" || (m.kind === "video" && m.audio)).map((m) => <option key={m.path} value={m.path}>{m.path}</option>)}
            </select>
          </Field>
          <Field label={t("vs_volume")} wide><Range value={num(item.volume, 0.45)} min={0} max={1.5} step={0.05} onChange={(v) => u({ volume: v })} /></Field>
          <Field label={t("vs_in")}><NumIn value={item.in ?? 0} onChange={(v) => u({ in: v })} /></Field>
          <Field label={t("vs_start")}><NumIn value={item.start ?? 0} onChange={(v) => u({ start: v })} /></Field>
          <Field label={t("vs_fade_in")}><NumIn value={item.fade_in} onChange={(v) => u({ fade_in: v })} /></Field>
          <Field label={t("vs_fade_out")}><NumIn value={item.fade_out} onChange={(v) => u({ fade_out: v })} /></Field>
        </div>
        {MUSIC.includes(item.src) && (
          <button onClick={() => u({ seed: Math.floor(Math.random() * 100000) + 1 })} className="flex w-full items-center justify-center gap-1.5 rounded-lg bg-hover py-1.5 text-[12px] hover:bg-active">
            <Sparkles size={13} className="text-amber-500" />{t("vs_music_variation")}</button>
        )}
        <p className="text-[11.5px] leading-snug text-subtle">{t("vs_music_note")}</p>
        <MusicLibrary t={t} onPick={(r) => u({ src: r.path, seed: undefined, in: 0 })} />
      </div>
    );
  }
  if (sel.kind === "scene") {
    const isImg = kindOf(item.src) === "image";
    const info = tm.scenes[sel.i];
    return (
      <div className="space-y-3">
        {head(`${t("vs_scene")} ${sel.i + 1}`)}
        <div className="grid grid-cols-2 gap-2">
          <Field label={t("vs_source")} wide><Sel value={item.src} onChange={(v) => u({ src: v, animated_src: undefined })} options={mediaPaths.includes(item.src) ? mediaPaths : [item.src, ...mediaPaths]} /></Field>
          <Field label={t("vs_duration")}><NumIn value={item.dur ?? +(info?.dur || 4).toFixed(2)} onChange={(v) => u({ dur: v })} /></Field>
          {!isImg && <Field label={t("vs_in")}><NumIn value={item.in ?? 0} onChange={(v) => u({ in: v })} /></Field>}
          {isImg && <Field label={t("vs_motion")}><Sel value={item.motion || "auto"} onChange={(v) => u({ motion: v })} options={MOTIONS} labels={labels(MOTIONS, "vs_m_")} /></Field>}
          <Field label={t("vs_fit")}><Sel value={item.fit || "cover"} onChange={(v) => u({ fit: v })} options={["cover", "blur", "contain"]} labels={labels(["cover", "blur", "contain"], "vs_fit_")} /></Field>
          <Field label={t("vs_transition_next")}><Sel value={item.transition || "auto"} onChange={(v) => u({ transition: v })} options={TRANSITIONS} /></Field>
          {!isImg && <Field label={t("vs_volume")}><Range value={num(item.volume, 0)} min={0} max={2} step={0.05} onChange={(v) => u({ volume: v })} /></Field>}
        </div>
        {isImg && (
          <label className="flex items-start gap-2 rounded-xl bg-hover/60 p-2 text-[12px]">
            <input type="checkbox" className="mt-0.5" checked={!!item.animate} onChange={(e) => u({ animate: e.target.checked || undefined })} />
            <span><b>{t("vs_animate")}</b> {item.animated_src && <span className="text-ok">✓ {t("vs_animated_ready")}</span>}
              <span className="block text-[11px] text-muted">{t("vs_animate_note")}</span></span>
          </label>
        )}
        {isImg && item.animate && <Field label={t("vs_motion_prompt")}><input className={fieldCls} value={item.motion_prompt || ""} placeholder={t("vs_motion_prompt_ph")} onChange={(e) => u({ motion_prompt: e.target.value, animated_src: undefined })} /></Field>}
        <h4 className="text-[12px] font-semibold">{t("vs_texts")}</h4>
        <div className="space-y-1.5">
          {SCENE_TEXT.map(([k, label]) => {
            const v = item[k];
            const txt = v && typeof v === "object" ? v.text || "" : v || "";
            return (
              <div key={k} className="flex items-end gap-1.5">
                <div className="min-w-0 flex-1"><Field label={t(label)}><input className={fieldCls} value={txt} onChange={(e) => updText(sel.i, k, { text: e.target.value })} /></Field></div>
                <button disabled={!txt} onClick={() => setSel({ kind: "stext", i: sel.i, key: k })} title={t("vs_style_text")}
                  className="mb-0.5 shrink-0 rounded-lg bg-hover px-2 py-1.5 text-[11px] hover:bg-active disabled:opacity-40">{t("vs_style")}</button>
              </div>
            );
          })}
          <Field label={t("vs_say_f")}><input className={fieldCls} value={item.say || ""} onChange={(e) => u({ say: e.target.value || undefined })} /></Field>
        </div>
        {item.say && <p className="text-[11.5px] leading-snug text-subtle">🎙 {t("vs_say_note")}</p>}
        <h4 className="text-[12px] font-semibold">{t("vs_effects")}</h4>
        <Chips options={EFFECTS} value={item.effects} onChange={(v) => u({ effects: v.length ? v : undefined })} label={fxLabel} />
      </div>
    );
  }
  // layers
  return (
    <div className="space-y-3">
      {head(item.type === "text" ? t("vs_text") : item.type === "audio" ? (item.name === "voice" ? t("vs_voiceover") : t("vs_sound")) : item._logo ? "Logo" : t("vs_layer"))}
      {item.type === "text" ? (
        <TextStyleFields t={t} v={item} labels={labels} onChange={u} />
      ) : (
        <div className="grid grid-cols-2 gap-2">
          <Field label={t("vs_source")} wide><Sel value={item.src} onChange={(v) => u({ src: v })} options={mediaPaths.includes(item.src) ? mediaPaths : [item.src, ...mediaPaths]} /></Field>
          {item.type !== "audio" && <Field label={t("vs_scale")} wide><Range value={num(item.scale, 1)} min={0.03} max={1} step={0.01} onChange={(v) => u({ scale: v })} /></Field>}
          {item.type !== "audio" && <Field label={t("vs_opacity")} wide><Range value={num(item.opacity, 1)} min={0} max={1} step={0.05} onChange={(v) => u({ opacity: v })} /></Field>}
          {item.type !== "image" && <Field label={t("vs_volume")} wide><Range value={num(item.volume, 1)} min={0} max={2} step={0.05} onChange={(v) => u({ volume: v })} /></Field>}
          {item.type !== "image" && <Field label={t("vs_in")}><NumIn value={item.in ?? 0} onChange={(v) => u({ in: v })} /></Field>}
          {item.type !== "audio" && <Field label="X"><input className={fieldCls} value={item.x ?? ""} onChange={(e) => u({ x: e.target.value })} /></Field>}
          {item.type !== "audio" && <Field label="Y"><input className={fieldCls} value={item.y ?? ""} onChange={(e) => u({ y: e.target.value })} /></Field>}
        </div>
      )}
      <div className="grid grid-cols-2 gap-2">
        <Field label={t("vs_start")}><NumIn value={item.start ?? 0} onChange={(v) => u({ start: v })} /></Field>
        <Field label={t("vs_duration")}><NumIn value={item.dur} onChange={(v) => u({ dur: v })} /></Field>
        <Field label={t("vs_fade_in")}><NumIn value={item.fade_in} onChange={(v) => u({ fade_in: v })} /></Field>
        <Field label={t("vs_fade_out")}><NumIn value={item.fade_out} onChange={(v) => u({ fade_out: v })} /></Field>
      </div>
      {item.type !== "audio" && <p className="text-[11.5px] leading-snug text-subtle">{t("vs_drag_hint")}</p>}
    </div>
  );
}

// royalty-free tracks (Openverse: Jamendo, Freesound...; commercial-use licences): search by mood, listen, add
function MusicLibrary({ t, onPick }) {
  const st = useStore.getState();
  const [q, setQ] = useState("");
  const [rows, setRows] = useState(null);
  const [busy, setBusy] = useState("");
  const [playing, setPlaying] = useState("");
  const audio = useRef(null);
  useEffect(() => () => audio.current?.pause(), []);
  const search = async (query) => {
    setBusy("search");
    try { setRows((await api.get(`/api/music/library?q=${encodeURIComponent(query || q || "background music")}`)).tracks || []); }
    catch (e) { st.notify(t("vs_lib_failed"), "error", e.message); setRows([]); }
    setBusy("");
  };
  const play = (r) => {
    audio.current?.pause();
    if (playing === r.url) { setPlaying(""); return; }
    audio.current = new Audio(r.url);
    audio.current.play().catch(() => {});
    setPlaying(r.url);
  };
  const add = async (r) => {
    setBusy(r.url);
    try {
      const d = await api.post(st.fileApi("/music/download"), { url: r.url, title: r.title, creator: r.creator, license: r.license, source: r.source });
      audio.current?.pause(); setPlaying("");
      onPick(d);
    } catch (e) { st.notify(t("vs_lib_failed"), "error", e.message); }
    setBusy("");
  };
  return (
    <div className="space-y-2 rounded-xl border border-line p-2">
      <div className="text-[12px] font-semibold">{t("vs_lib_title")}</div>
      <div className="flex gap-1.5">
        <input className={fieldCls} value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => e.key === "Enter" && search()} placeholder={t("vs_lib_search")} />
        <button onClick={() => search()} className="shrink-0 rounded-lg bg-accent px-2.5 text-[12px] text-accent-fg">{busy === "search" ? <Loader2 size={13} className="animate-spin" /> : t("vs_lib_go")}</button>
      </div>
      <div className="flex flex-wrap gap-1">
        {MOODS.map((m) => <button key={m} onClick={() => { setQ(m); search(m); }} className="rounded-md border border-line px-1.5 py-0.5 text-[10.5px] text-muted hover:bg-hover">{t(`vs_mood_${m}`)}</button>)}
      </div>
      {rows && rows.length === 0 && <div className="text-center text-[11.5px] text-muted">{t("vs_lib_none")}</div>}
      <div className="max-h-52 space-y-1 overflow-y-auto">
        {(rows || []).map((r) => (
          <div key={r.url} className="flex items-center gap-1.5 rounded-lg px-1 py-1 text-[11.5px] hover:bg-hover">
            <button onClick={() => play(r)} className="grid h-6 w-6 shrink-0 place-items-center rounded-full bg-hover">{playing === r.url ? <Pause size={11} /> : <Play size={11} className="ml-0.5" />}</button>
            <span className="min-w-0 flex-1"><span className="block truncate font-medium">{r.title}</span><span className="block truncate text-[10.5px] text-subtle">{r.creator} · {r.license} · {r.duration ? `${Math.round(r.duration)} s` : ""}</span></span>
            <button onClick={() => add(r)} disabled={!!busy} className="shrink-0 rounded-md bg-accent/15 px-1.5 py-0.5 text-[11px] text-accent">{busy === r.url ? <Loader2 size={11} className="animate-spin" /> : t("vs_lib_add")}</button>
          </div>
        ))}
      </div>
      <p className="text-[10.5px] leading-snug text-subtle">{t("vs_lib_note")}</p>
    </div>
  );
}

function RenderBusy({ started, animate, t }) {
  const [, tick] = useState(0);
  useEffect(() => { const h = setInterval(() => tick((x) => x + 1), 500); return () => clearInterval(h); }, []);
  return (
    <div className="absolute inset-0 z-[60] grid place-items-center bg-black/55 backdrop-blur-sm">
      <div className="max-w-xs rounded-2xl bg-elev px-6 py-5 text-center shadow-2xl">
        <Loader2 className="mx-auto animate-spin text-accent" size={28} />
        <div className="mt-2 font-medium">{t("vs_rendering")}</div>
        <div className="font-mono text-[12px] text-muted">{((Date.now() - started) / 1000).toFixed(0)} s</div>
        {animate && <div className="mt-1 text-[11.5px] leading-snug text-muted">{t("vs_rendering_animate")}</div>}
      </div>
    </div>
  );
}

function RenderResult({ r, raw, t, onClose }) {
  const res = r.result;
  return (
    <div className="absolute inset-0 z-[60] grid place-items-center bg-black/55 p-3 backdrop-blur-sm" onPointerDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="w-full max-w-2xl overflow-hidden rounded-2xl bg-elev shadow-2xl">
        <div className="flex items-center gap-2 border-b border-line px-4 py-2.5">
          {res ? <Check className="text-ok" size={17} /> : <X className="text-danger" size={17} />}
          <span className="font-medium">{res ? t("vs_done") : t("vs_render_failed")}</span>
          <button onClick={onClose} className="ml-auto rounded-lg p-1 text-muted hover:bg-hover"><X size={16} /></button>
        </div>
        {res ? (
          <div className="space-y-2 p-3">
            <video src={`${raw(res.path)}&v=${Date.now()}`} controls autoPlay className="max-h-[55vh] w-full rounded-xl bg-black" />
            <div className="flex flex-wrap items-center gap-2 text-[12px] text-muted">
              <span className="font-mono">{res.path}</span>
              <span>· {res.duration.toFixed(1)} s · {res.width}×{res.height} · {(res.size / 1048576).toFixed(1)} MB · {(res.ms / 1000).toFixed(1)} s</span>
              <a href={`${raw(res.path)}&download=true`} className="ml-auto rounded-lg bg-accent px-2.5 py-1 text-accent-fg">{t("download")}</a>
            </div>
            {res.gaps?.length > 0 && <div className="rounded-lg bg-warn/10 px-2 py-1 text-[12px] text-warn">{t("vs_gaps", { spans: res.gaps.map((g) => `${g[0]}-${g[1]}s`).join(", ") })}</div>}
            {res.animated?.failed?.length > 0 && <div className="rounded-lg bg-warn/10 px-2 py-1 text-[12px] text-warn">{t("vs_animate_failed")}<div className="mt-0.5 font-mono text-[10.5px] opacity-80">{res.animated.failed.join(" · ")}</div></div>}
          </div>
        ) : <div className="whitespace-pre-wrap break-words p-4 font-mono text-[12px] text-danger">{r.error}</div>}
      </div>
    </div>
  );
}
