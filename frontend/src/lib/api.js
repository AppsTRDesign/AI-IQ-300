// Thin REST client. All execution state lives in the backend.
// Backend errors carry {code, message}; the code is translated (err_<code>) when a translation exists.
let translate = null;
export const setErrorTranslator = (fn) => { translate = fn; };

async function req(method, url, body, isForm) {
  const res = await fetch(url, {
    method,
    headers: body && !isForm ? { "Content-Type": "application/json" } : undefined,
    body: body ? (isForm ? body : JSON.stringify(body)) : undefined,
  });
  if (!res.ok) {
    let detail = res.statusText, code = null;
    try {
      const d = (await res.json()).detail;
      if (d && typeof d === "object" && !Array.isArray(d)) { code = d.code; detail = d.message || detail; }
      else if (Array.isArray(d)) detail = d.map((x) => x.msg).join("; ");
      else if (d) detail = d;
    } catch {}
    const translated = code && translate ? translate(code) : null;
    const err = new Error(translated || detail);
    err.code = code; err.status = res.status; err.detail = detail;
    throw err;
  }
  return res.json();
}

export const api = {
  get: (u) => req("GET", u),
  post: (u, b) => req("POST", u, b || {}),
  put: (u, b) => req("PUT", u, b),
  patch: (u, b) => req("PATCH", u, b),
  del: (u) => req("DELETE", u),
  upload: (u, file) => { const f = new FormData(); f.append("file", file); return req("POST", u, f, true); },
};
