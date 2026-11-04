// Voice task control: continuous speech recognition. A whole utterance that is a command runs it ("send", "stop",
// "approve"...); an utterance ending with the send word is dictated and sent; anything else is dictated into the
// message box. Listening pauses while an answer is read aloud, so the app never hears itself.
import { onSpeech, speakingId } from "./speech";

const WORDS = {
  tr: {
    send: ["gönder", "başlat", "yolla", "çalıştır", "tamam gönder"],
    stop: ["dur", "durdur", "iptal", "iptal et", "görevi durdur"],
    approve: ["onayla", "onay ver", "evet onayla", "izin ver"],
    deny: ["reddet", "hayır", "reddet onu", "izin verme"],
    new: ["yeni sohbet", "yeni konuşma"],
    clear: ["temizle", "metni sil"],
    read: ["oku", "sesli oku", "cevabı oku"],
    quiet: ["sus", "sessiz", "okumayı durdur"],
    off: ["dinlemeyi kapat", "komut modunu kapat", "sesli komutu kapat"],
  },
  en: {
    send: ["send", "start", "go", "send it", "submit"],
    stop: ["stop", "cancel", "stop the task", "abort"],
    approve: ["approve", "yes approve", "allow", "accept"],
    deny: ["deny", "reject", "no", "decline"],
    new: ["new chat", "new conversation"],
    clear: ["clear", "clear text"],
    read: ["read", "read aloud", "read the answer"],
    quiet: ["quiet", "be quiet", "stop reading", "silence"],
    off: ["stop listening", "voice off", "turn off voice commands"],
  },
};

const norm = (s) => s.toLocaleLowerCase().replace(/[.,!?;:"'’]+/g, " ").replace(/\s+/g, " ").trim();

// -> { cmd, text }: cmd is null for plain dictation; text is what to dictate (possibly with cmd "send").
export function parseUtterance(utterance, lang = "tr") {
  const words = WORDS[lang] || WORDS.en;
  const u = norm(utterance);
  if (!u) return { cmd: null, text: "" };
  for (const [cmd, list] of Object.entries(words)) if (list.includes(u)) return { cmd, text: "" };
  for (const w of words.send) {  // "... gönder": dictate the rest, then send
    if (u.endsWith(" " + w) && u.length > w.length + 1) {
      const raw = utterance.trim();
      return { cmd: "send", text: raw.slice(0, raw.toLocaleLowerCase().lastIndexOf(w)).replace(/[\s,.;:]+$/, "") };
    }
  }
  return { cmd: null, text: utterance.trim() };
}

export function createVoiceControl({ lang, onResult, onState }) {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) return null;
  let rec = null, on = false, paused = false;
  const start = () => {
    if (!on || paused || rec) return;
    rec = new SR();
    rec.lang = lang === "tr" ? "tr-TR" : lang === "en" ? "en-US" : lang;
    rec.continuous = true;
    rec.interimResults = false;
    rec.onresult = (e) => {
      for (let i = e.resultIndex; i < e.results.length; i++) {
        if (e.results[i].isFinal) onResult(parseUtterance(e.results[i][0].transcript, lang));
      }
    };
    rec.onerror = (e) => { if (e.error === "not-allowed" || e.error === "service-not-allowed") { on = false; onState("denied"); } };
    rec.onend = () => { rec = null; if (on && !paused) setTimeout(start, 250); };  // browsers stop after silence: restart
    try { rec.start(); } catch { rec = null; }
  };
  const stopRec = () => { if (rec) { try { rec.abort(); } catch {} rec = null; } };
  const off = onSpeech((id) => {  // pause while an answer is being read aloud
    paused = !!id;
    if (paused) stopRec(); else start();
  });
  return {
    enable() { on = true; paused = !!speakingId(); start(); onState("on"); },
    disable() { on = false; stopRec(); onState("off"); },
    dispose() { on = false; stopRec(); off(); },
  };
}
