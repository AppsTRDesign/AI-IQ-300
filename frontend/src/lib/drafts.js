// Unsent messages per chat: the text and the attached files of each chat's composer stay when you open another chat,
// reload the page or the computer restarts (power cut). Kept in this browser (localStorage); attachments are already
// uploaded into the chat, so only their names are stored and images get their preview back from the server.
const KEY = "aiiq-drafts";
const MAX_AGE = 30 * 24 * 3600 * 1000;

const readAll = () => {
  try { return JSON.parse(localStorage.getItem(KEY) || "{}") || {}; } catch { return {}; }
};
const writeAll = (all) => {
  try { localStorage.setItem(KEY, JSON.stringify(all)); } catch { /* storage full or blocked: drafts are a convenience */ }
};

export const draftKey = (sessionId) => sessionId || "new";

export function getDraft(key) {
  const d = readAll()[key];
  return d && Date.now() - (d.at || 0) < MAX_AGE ? d : null;
}

export function saveDraft(key, text, attachments) {
  const all = readAll();
  const att = (attachments || []).map(({ b64, ...a }) => a); // no image data: it is fetched again
  if (!text?.trim() && !att.length) delete all[key];
  else all[key] = { text: text || "", attachments: att, at: Date.now() };
  for (const [k, v] of Object.entries(all)) if (Date.now() - (v.at || 0) > MAX_AGE) delete all[k];
  writeAll(all);
}

export function moveDraft(from, to) {
  const all = readAll();
  if (all[from]) { all[to] = all[from]; delete all[from]; writeAll(all); }
}

// Images of a restored draft: their base64 copy for vision models comes back from the chat's upload folder.
export async function restoreImages(sessionId, attachments) {
  return Promise.all((attachments || []).map(async (a) => {
    if (a.kind !== "image" || a.b64 || !sessionId) return a;
    try {
      const r = await fetch(`/api/sessions/${sessionId}/upload/raw?name=${encodeURIComponent(a.name)}`);
      if (!r.ok) return a;
      const blob = await r.blob();
      const b64 = await new Promise((res) => { const fr = new FileReader(); fr.onload = () => res(String(fr.result).split(",")[1]); fr.readAsDataURL(blob); });
      return { ...a, b64, mime: a.mime || blob.type };
    } catch { return a; }
  }));
}
