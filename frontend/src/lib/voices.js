// The voice catalog on the client: local voices (Piper, Kokoro, Chatterbox) + Microsoft's online voices, installs with
// progress, previews with tone. Every picker (Text to speech, Video Studio, Settings, spoken replies) uses this.
import { api } from "./api";

export const SAMPLES = {
  tr: "Merhaba, bu ses videonuzu ve metinlerinizi seslendirecek.", en: "Hello, this voice will narrate your videos and texts.",
  de: "Hallo, diese Stimme spricht Ihre Videos und Texte.", fr: "Bonjour, cette voix racontera vos vidéos et vos textes.",
  es: "Hola, esta voz narrará tus vídeos y textos.", it: "Ciao, questa voce narrerà i tuoi video e i tuoi testi.",
  ar: "مرحبا، هذا الصوت سيروي مقاطع الفيديو والنصوص الخاصة بك.", ru: "Привет, этот голос озвучит ваши видео и тексты.",
  pt: "Olá, esta voz vai narrar os seus vídeos e textos.", ja: "こんにちは、この声があなたの動画と文章を読み上げます。",
  zh: "你好，这个声音将为你的视频和文字配音。", nl: "Hallo, deze stem vertelt je video's en teksten.",
  hi: "नमस्ते, यह आवाज़ आपके वीडियो और लेख पढ़ेगी।",
};
export const LANG_NAMES = { tr: "Türkçe", en: "English", de: "Deutsch", fr: "Français", es: "Español", it: "Italiano", ar: "العربية",
  ru: "Русский", pt: "Português", ja: "日本語", zh: "中文", nl: "Nederlands", ko: "한국어", hi: "हिन्दी", pl: "Polski", sv: "Svenska",
  uk: "Українська", az: "Azərbaycan", fa: "فارسی", el: "Ελληνικά", da: "Dansk", fi: "Suomi", no: "Norsk", he: "עברית",
  cs: "Čeština", hu: "Magyar", ro: "Română", ka: "ქართული", kk: "Қазақ", vi: "Tiếng Việt", id: "Indonesia", ms: "Melayu", sw: "Kiswahili" };
export const ENGINE_LABEL = { piper: "Piper", kokoro: "Kokoro", chatterbox: "Chatterbox", edge: "Online" };
export const QUALITY_ORDER = { studio: 0, high: 1, standard: 2, basic: 3 };
export const isLocalVoice = (id) => /^(piper|kokoro|chatterbox):/.test(id || "");
export const clampRate = (r) => Math.min(2, Math.max(0.5, +r || 1));

let cache = null;
export async function loadVoices(force = false) {
  if (!cache || force) cache = api.get("/api/voices").catch((e) => { cache = null; throw e; });
  return cache;
}

// Download a local voice and wait for it (the backend reports progress; onProgress(frac 0..1, state))
export async function installVoice(id, onProgress) {
  await api.post("/api/voices/install", { id });
  for (;;) {
    await new Promise((r) => setTimeout(r, 900));
    const d = await loadVoices(true);
    const p = d.progress?.[id] || {};
    onProgress?.(p.frac || 0, p.state);
    if (p.state === "done") return d;
    if (p.state === "error") throw new Error(p.error || "install failed");
  }
}

let playing = null;
export function stopPreview() { playing?.pause(); playing = null; }
export async function previewVoice({ text, voice, rate = 1, pitch, emotion, preset, room, pause }) {
  stopPreview();
  const r = await fetch("/api/voices/preview", { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, voice, rate: clampRate(rate), pitch, emotion, preset, room, pause }) });
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail?.message || `HTTP ${r.status}`);
  const a = new Audio(URL.createObjectURL(await r.blob()));
  playing = a;
  await a.play().catch(() => {});
  return a;
}

// The voice a language uses when none is chosen: the user's default (Settings > Voices), else the best installed
// local voice (female first), else an online one.
export function defaultVoiceOf(list, lang, settings) {
  const own = settings?.defaults?.[lang];
  const inLang = list.filter((v) => (v.lang || v.locale?.slice(0, 2)) === lang && v.installed !== false);
  if (own && inLang.some((v) => v.id === own)) return own;
  const local = inLang.filter((v) => v.engine !== "edge" && v.engine !== "chatterbox")
    .sort((a, b) => (a.gender !== "female") - (b.gender !== "female") || (QUALITY_ORDER[a.quality] ?? 3) - (QUALITY_ORDER[b.quality] ?? 3));
  return (local[0] || inLang.find((v) => v.gender === "female") || inLang[0])?.id || "";
}
