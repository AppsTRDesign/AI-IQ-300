// Spoken replies. Two engines:
// - "edge:<voice>": Microsoft's online neural voices through the backend (edge-tts), labelled female/male; the text
//   is sent to Microsoft's read-aloud service. Sentences are fetched ahead so reading starts after the first one.
// - any other value: the browser's own speech synthesis (offline voices of the OS; nothing leaves the computer).
// An empty choice uses the active language's first female neural voice, or the browser voice when offline.
import { api } from "./api";

const synth = typeof window !== "undefined" ? window.speechSynthesis : null;
const listeners = new Set();
let current = null; // id of the message being read
let token = 0; // bumps on every speak/stop, so a stopped reading never resumes
let audio = null;
let release = null; // ends the sentence that is playing

export const speechSupported = () => !!synth || typeof Audio !== "undefined";

const notify = () => listeners.forEach((f) => f(current));
export function onSpeech(f) { listeners.add(f); return () => listeners.delete(f); }
export const speakingId = () => current;

// Markdown -> plain sentences: code blocks, links, tables, emoji, symbols and text emoticons are not read aloud
// (% and currency signs stay: they are part of what is said; arrows become a short pause).
const EMOTICON = /(^|\s)(?:[xX][dDpP]|[:;=][-'^o]?[)(\]\[dDpPoO3/\\|*]+|[)(]+[-']?[:;=]|<\/?3+|\^_*\^|[oO-]_+[oO-]|\u00af\S*\u00af|:[a-z0-9_+-]+:)(?=\s|$|[.,!?])/g;
const ARROWS = /\s*(?:-+>|=+>|<-+|<=+(?!\s*\d)|[\u2190-\u21ff\u27f0-\u27ff\u2900-\u297f])\s*/g;
const SYMBOLS = /[\p{Extended_Pictographic}\p{Emoji_Modifier}\u200d\ufe0e\ufe0f\u20e3\u{1f1e6}-\u{1f1ff}\u2300-\u23ff\u2460-\u27bf\u2b00-\u2bff\u25a0-\u25ff\u2500-\u257f\u2022\u00b7\u25e6\u2023\u2219\u00a7\u00b6\u2020\u2021\u203b]/gu;
export function speechText(md) {
  return (md || "")
    .replace(/```[\s\S]*?```/g, " ")
    .replace(/^\s*([-*_=~]\s*){3,}$/gm, " ") // separator lines
    .replace(/\[[ xX]\]\s*/g, "") // task-list boxes
    .replace(ARROWS, ", ")
    .replace(EMOTICON, "$1")
    .replace(SYMBOLS, " ")
    .replace(/`([^`]+)`/g, "$1")
    .replace(/!\[[^\]]*\]\([^)]*\)/g, " ")
    .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1")
    .replace(/^\s*\|.*\|\s*$/gm, " ")
    .replace(/^#+\s*/gm, "")
    .replace(/^\s*>+\s?/gm, "") // quotes
    .replace(/[*_~#]+/g, "")
    .replace(/^\s*[-\u2022]\s+/gm, "")
    .replace(/https?:\/\/\S+/g, "")
    .replace(/^[\s,]+|[ \t]*,(\s*,)+/gm, ",") // pauses left by removed symbols
    .replace(/^,|,(?=\s*$)/gm, "")
    .replace(/[ \t]{2,}/g, " ")
    .replace(/\s+\n/g, "\n")
    .trim();
}

export function voicesFor(lang) {
  if (!synth) return [];
  return synth.getVoices().filter((v) => v.lang?.toLowerCase().startsWith(lang));
}

// Neural voices for a language: [{id, name, gender, locale}]; an empty list (offline) is not cached.
const edgeCache = {};
export function edgeVoices(lang) {
  edgeCache[lang] ||= api.get(`/api/tts/voices?lang=${encodeURIComponent(lang)}`)
    .then((r) => r.voices || []).catch(() => [])
    .then((v) => { if (!v.length) delete edgeCache[lang]; return v; });
  return edgeCache[lang];
}
const MAIN_LOCALE = { en: "en-US", tr: "tr-TR", de: "de-DE", fr: "fr-FR", es: "es-ES", pt: "pt-BR", ar: "ar-SA", zh: "zh-CN" };
export async function defaultEdgeVoice(lang) {
  const list = await edgeVoices(lang);
  const main = list.filter((v) => v.locale === MAIN_LOCALE[lang]);
  const pool = main.length ? main : list;
  return (pool.find((v) => v.gender === "female") || pool[0])?.id || "";
}

// The voice is chosen per language (Settings > Spoken replies), so switching the language never reads
// English text with a Turkish voice.
export const speechOpts = (prefs) => {
  const lang = prefs.lang || "tr";
  return { lang, voice: prefs.voiceBy?.[lang] || "", rate: prefs.voiceRate || 1 };
};

export function stopSpeech() {
  token += 1;
  synth?.cancel();
  audio?.pause();
  release?.();
  if (current !== null) { current = null; notify(); }
}

const sentences = (text) => text.match(/[^.!?\n]+[.!?]*|\n+/g)?.map((s) => s.trim()).filter((s) => /[\p{L}\p{N}]/u.test(s)) || [text];

// First piece is one sentence (reading starts fast); later pieces join sentences up to ~260 characters.
function pieces(text) {
  const out = [];
  for (const s of sentences(text)) {
    if (out.length > 1 && (out.at(-1) + " " + s).length <= 260) out[out.length - 1] += " " + s;
    else out.push(s);
  }
  return out;
}

function speakBrowser(id, text, { lang, voice, rate }, my) {
  if (!synth) return finish(id, my);
  const v = synth.getVoices().find((x) => x.voiceURI === voice) || voicesFor(lang)[0];
  const chunks = sentences(text);
  chunks.forEach((c, i) => {
    const u = new SpeechSynthesisUtterance(c);
    u.lang = v?.lang || (lang === "tr" ? "tr-TR" : lang === "en" ? "en-US" : lang);
    if (v) u.voice = v;
    u.rate = rate;
    if (i === chunks.length - 1) u.onend = u.onerror = () => finish(id, my);
    synth.speak(u);
  });
}

function finish(id, my) {
  if (my === token && current === id) { current = null; notify(); }
}

const fetchAudio = async (text, voice, rate) => {
  const res = await fetch("/api/tts", { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, voice, rate }) });
  if (!res.ok) throw new Error(`tts ${res.status}`);
  return res.blob();
};

const play = (blob, my) => new Promise((resolve) => {
  if (my !== token) return resolve();
  const url = URL.createObjectURL(blob);
  const a = new Audio(url);
  audio = a;
  release = () => { URL.revokeObjectURL(url); resolve(); };
  a.onended = a.onerror = release;
  a.play().catch(release);
});

async function speakEdge(id, text, voice, rate, my) {
  const parts = pieces(text);
  const pending = [];
  const load = (i) => {
    if (i < parts.length && !pending[i]) { pending[i] = fetchAudio(parts[i], voice, rate); pending[i].catch(() => {}); }
  };
  for (let i = 0; i < parts.length; i++) {
    load(i); load(i + 1); load(i + 2);
    let blob;
    try { blob = await pending[i]; } catch (e) { if (i === 0) throw e; continue; } // a later failed sentence is skipped
    if (my !== token) return;
    await play(blob, my);
    if (my !== token) return;
  }
  finish(id, my);
}

export function speak(id, md, { lang = "tr", voice = "", rate = 1 } = {}) {
  stopSpeech();
  const text = speechText(md);
  if (!text) return;
  const my = token;
  current = id;
  notify();
  (async () => {
    let neural = voice.startsWith("edge:") ? voice.slice(5) : voice ? "" : await defaultEdgeVoice(lang);
    if (my !== token) return;
    if (neural) {
      try { return await speakEdge(id, text, neural, rate, my); } catch { neural = ""; } // service down: browser voice
    }
    if (my === token) speakBrowser(id, text, { lang, voice: voice.startsWith("edge:") ? "" : voice, rate }, my);
  })();
}
