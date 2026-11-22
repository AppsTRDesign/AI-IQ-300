import { create } from "zustand";
import { api, setErrorTranslator } from "./api";
import { docKind, isAudio, isImage, isTextFile, isVideo, isWebPage } from "./fileTypes";
// Static: the chat, settings and voice library import speech.js directly, so a dynamic import here split nothing off
// and only made Vite warn on every build.
import * as speech from "./speech";

// The device's position for map searches (the browser asks the user's permission once; Wi-Fi/GPS through the OS).
function answerLocation(id) {
  const send = (body) => api.post(`/api/location/${id}`, body).catch(() => {});
  if (!navigator.geolocation) { send({ error: "geolocation not supported" }); return; }
  navigator.geolocation.getCurrentPosition(
    (pos) => send({ lat: pos.coords.latitude, lon: pos.coords.longitude, accuracy: pos.coords.accuracy }),
    (err) => send({ error: err.code === 1 ? "permission denied" : err.code === 3 ? "timeout" : "position unavailable" }),
    { enableHighAccuracy: true, timeout: 15000, maximumAge: 120000 },
  );
}

// Throttle for the live "context" event's periodic full resync (see applyEvents): the quick per-event patch below
// only ever touches `used`, so if the running model changes mid-task (quota auto-switch) its window/threshold
// would otherwise stay stale until the panel is opened - this keeps them in sync without refetching every tick.
let _ctxResyncAt = 0;
let _ctxLiveAt = 0; // time of the last live context event (a slower /context answer must not overwrite it)

const readB64 = (file) => new Promise((res) => {
  const r = new FileReader();
  r.onload = () => res(String(r.result).split(",")[1]);
  r.readAsDataURL(file);
});

// First start: the browser/OS language if a translation exists, otherwise English.
export function detectLanguage(available) {
  const codes = new Set(available.map((l) => l.code));
  for (const tag of navigator.languages?.length ? navigator.languages : [navigator.language || "en"]) {
    const full = (tag || "").toLowerCase();
    if (codes.has(full)) return full;
    const base = full.split("-")[0];
    if (codes.has(base)) return base;
  }
  return "en";
}

const PAGE = 30; // messages per page when a chat opens / while scrolling up
const PREFS_KEY = "aiiq.prefs";
const loadPrefs = () => { try { return JSON.parse(localStorage.getItem(PREFS_KEY)) || {}; } catch { return {}; } };
const savePrefs = (p) => { try { localStorage.setItem(PREFS_KEY, JSON.stringify(p)); } catch {} };

export const emptyRun = (extra = {}) => ({ id: null, text: "", steps: [], todos: [], approvals: [], status: "starting", error: null, role: null, started: Date.now(), ...extra });

// Runs are kept per session, so a run keeps streaming in the background while another chat is open.
export const useStore = create((set, get) => ({
  view: "chat",
  sidebarOpen: false,
  projectsOpen: true,
  editorOpen: false,
  panel: null,
  connected: false,
  prefs: { theme: "system", ...loadPrefs() },
  dict: {},
  settings: null,
  models: {},
  modelStatus: null, // { model, state, message } for local model switching
  catalog: { skills: [], agents: [] },
  mcpTools: [], // [{name: "server/tool", description}] of the running MCP servers (the composer's # picker)
  mcpTool: null, // a tool sent from Settings > MCP > Try to the composer
  projects: [],
  sessions: [],
  expanded: {},
  sessionId: null,
  projectId: null,
  scope: "project",
  messages: [],
  runs: {}, // sessionId -> live run
  context: null,
  attachments: [],
  processes: {},
  logs: {},
  editor: { tabs: [], active: null },
  dialog: null, // { type, ... }
  toasts: [], // stacked, auto-dismissing system notifications
  net: { online: true }, // this computer's internet (backend netwatch.py): a drop pauses cloud tasks until it is back
  netToast: null,
  confirmState: null, // { title, message, confirmLabel, danger, resolve }
  saveState: { state: "idle", at: null, error: null }, // settings persistence indicator
  lastSeq: 0,
  boot: "", // the backend's start id: a different one after a reconnect means the app restarted (see socket.js)
  fsTick: 0, // bumps whenever an agent writes/deletes a file -> file manager refreshes at once

  setView: (view) => set({ view, sidebarOpen: false }),
  toggle: (k) => set((s) => ({ [k]: !s[k] })),
  setPref: (k, v) => { const prefs = { ...get().prefs, [k]: v }; savePrefs(prefs); set({ prefs }); },
  notify(text, kind = "info", detail) {
    const id = Math.random().toString(36).slice(2);
    set((s) => ({ toasts: [...s.toasts.filter((x) => x.text !== text), { id, text, kind, detail }].slice(-4) }));
    if (kind !== "busy") setTimeout(() => get().dismiss(id), kind === "error" ? 7000 : 3500);
    return id;
  },
  dismiss: (id) => set((s) => ({ toasts: s.toasts.filter((x) => x.id !== id) })),
  // Internet dropped / came back: one notice that stays while offline, replaced by a short "back" notice.
  applyNet(n) {
    const { net, netToast, t } = get();
    const online = n.online !== false;
    if (online === net.online && !(n.quiet === false)) { set({ net: { ...net, ...n, online } }); return; }
    if (netToast) get().dismiss(netToast);
    let id = null;
    if (!online) id = get().notify(t("net_down"), "busy");
    else if (!n.quiet) get().notify(n.down_secs ? t("net_up_after", { s: n.down_secs }) : t("net_up"), "ok");
    set({ net: { ...n, online }, netToast: id });
  },
  // Promise-based replacement for window.confirm(), rendered as a styled modal.
  confirm: (opts) => new Promise((resolve) => set({ confirmState: { ...opts, resolve } })),
  closeConfirm(result) {
    const c = get().confirmState;
    set({ confirmState: null });
    c?.resolve(result);
  },
  // Any settings write goes through here so the UI can always show "saving / saved / failed".
  async persist(fn) {
    set({ saveState: { state: "saving", at: get().saveState.at, error: null } });
    try {
      const r = await fn();
      set({ saveState: { state: "saved", at: Date.now(), error: null } });
      return r;
    } catch (e) {
      set({ saveState: { state: "error", at: get().saveState.at, error: e.message } });
      get().notify(get().t("save_failed"), "error", e.message);
      throw e;
    }
  },
  // File API base for the current chat; before a chat exists it targets the selected project (else no folder yet).
  fileApi(path) {
    const { sessionId, scope, projectId } = get();
    const q = !sessionId && scope === "project" && projectId ? `project_id=${projectId}` : "";
    const sep = path.includes("?") ? "&" : "?";
    return `/api/sessions/${sessionId || "new"}${path}${q ? sep + q : ""}`;
  },

  async loadLanguage(code) {
    const dict = await api.get(`/api/languages/${code}`);
    get().setPref("lang", code);
    // The backend writes notes, summaries and recovered-task messages in this language too.
    if (get().settings && get().settings.language !== code) {
      api.patch("/api/settings", { language: code }).then((s) => set((st) => ({ settings: { ...s, secrets: st.settings?.secrets } }))).catch(() => {});
    }
    document.documentElement.lang = code;
    set({ dict });
    setErrorTranslator((c) => dict[`err_${c}`] || null);
  },
  t(key, vars = {}) {
    const raw = get().dict[key] ?? key;
    return raw.replace(/\{(\w+)\}/g, (_, k) => vars[k] ?? "");
  },

  async bootstrap() {
    const [settings, projects, sessions] = await Promise.all([
      api.get("/api/settings"), api.get("/api/projects"), api.get("/api/sessions"),
    ]);
    set({ settings, projects, sessions, expanded: Object.fromEntries(projects.map((p) => [p.id, true])) });
    let lang = get().prefs.lang;
    if (!lang) lang = detectLanguage(await api.get("/api/languages").catch(() => [{ code: "en" }]));
    try { await get().loadLanguage(lang); } catch { await get().loadLanguage("en"); }
    get().loadModels().then(() => get().startSync());
    get().loadCatalog();
    api.get("/api/processes").then((list) => set({ processes: Object.fromEntries(list.map((p) => [p.id, p])) }));
    if (projects[0]) set({ projectId: projects[0].id });
    // "Open in new window": ?session=<id> opens that chat in this window.
    // A reload (an update replaced the build, F5) returns to the chat this tab had open, with its open viewer.
    let tab = {};
    try { tab = JSON.parse(sessionStorage.getItem("aiiq_tab") || "{}"); } catch { /* none */ }
    const want = new URLSearchParams(location.search).get("session") || tab.session;
    if (want && sessions.some((x) => x.id === want)) {
      await get().openSession(want);
      if (tab.dialog && tab.session === want && Date.now() - (tab.at || 0) < 60000) set({ dialog: tab.dialog });
    }
  },
  // Each provider's models load in parallel and appear as soon as they arrive (no waiting for the slowest one).
  // refresh: ask every provider again instead of the server's 5-minute cache (the refresh button).
  async loadModels(refresh = false) {
    let providers;
    try { providers = await api.get("/api/models/providers"); } catch { return; }
    set((s) => ({ models: Object.fromEntries(Object.entries(providers).map(([pid, p]) =>
      [pid, s.models[pid] ? { ...s.models[pid], ...p } : { ...p, models: [], loading: true }])) }));
    await Promise.all(Object.keys(providers).map((pid) => get().loadProviderModels(pid, refresh)));
    get().ensureModel();
  },
  // Live sync: a local server (Ollama, LM Studio) that starts or stops, and settings changed in another window or
  // by the backend, show up within seconds without a reload. The server watches and pushes a "health" event over the
  // WebSocket only when something changed; the page asks itself only at start, when it gets focus again (at most every
  // 30 s) and once a minute as a safety net. Polling every 3 s filled the server log with health requests.
  _health: { rev: null, listRev: {}, busy: false },
  async applyHealth(h) {
    const hs = get()._health;
    if (!h || hs.busy) return;
    hs.busy = true;
    try {
      if (hs.rev !== null && h.settings_rev !== hs.rev && get().saveState?.state !== "saving") {
        const before = JSON.stringify(get().settings?.providers || {});
        await get().refreshSettings();
        if (JSON.stringify(get().settings?.providers || {}) !== before) await get().loadModels(true);
      }
      hs.rev = h.settings_rev;
      for (const [pid, up] of Object.entries(h.local || {})) {
        const p = get().models[pid];
        const changed = up && h.models_rev?.[pid] && hs.listRev[pid] && hs.listRev[pid] !== h.models_rev[pid];
        if (up && h.models_rev?.[pid]) hs.listRev[pid] = h.models_rev[pid];
        if (!p) { if (up) await get().loadModels(true); continue; }
        if (p.loading) continue;
        if (up && (p.error || !p.models.length || changed)) {
          await get().loadProviderModels(pid, true);
          get().ensureModel();
        } else if (!up && !p.error) {
          set((s) => ({ models: { ...s.models, [pid]: { ...s.models[pid], error: `${p.name} is unreachable`, code: "unavailable" } } }));
        }
      }
    } catch { /* backend restarting: the next check tries again */ }
    hs.busy = false;
  },
  startSync() {
    if (get()._syncing) return;
    set({ _syncing: true });
    let last = 0;
    const tick = async (force) => {
      if (document.hidden || (!force && Date.now() - last < 30000)) return;
      last = Date.now();
      try { await get().applyHealth(await api.get("/api/models/health")); } catch { /* backend restarting */ }
    };
    tick(true);
    setInterval(() => tick(true), 60000);
    addEventListener("focus", () => tick(false));
    document.addEventListener("visibilitychange", () => !document.hidden && tick(false));
  },
  // If no model is chosen yet (fresh install) or the chosen one disappeared, use the first available model.
  ensureModel() {
    const cur = get().currentModel();
    const all = Object.entries(get().models).sort(([, a], [, b]) => b.local - a.local)
      .flatMap(([pid, p]) => p.models.map((m) => `${pid}:${m.id}`));
    if (!all.length || (cur && all.includes(cur))) return;
    const [pid] = (cur || "").split(":");
    if (cur && get().models[pid]?.error) return; // provider temporarily down: keep the user's choice
    get().setPref("model", all[0]);
    get().loadContext();
  },
  async loadProviderModels(pid, refresh = false) {
    set((s) => (s.models[pid] ? { models: { ...s.models, [pid]: { ...s.models[pid], loading: true } } } : {}));
    try {
      const r = await api.get(`/api/models/of/${pid}${refresh ? "?refresh=true" : ""}`);
      set((s) => ({ models: { ...s.models, [pid]: { ...r, loading: false } } }));
      return r;
    } catch (e) {
      set((s) => ({ models: { ...s.models, [pid]: { ...(s.models[pid] || {}), loading: false, error: e.message } } }));
      return null;
    }
  },
  // After a provider's key/URL/switch is saved: re-check only that provider at once and report the result.
  async refreshProvider(pid) {
    const t = get().t;
    const providers = await api.get("/api/models/providers").catch(() => ({}));
    if (!providers[pid]) {
      set((s) => { const m = { ...s.models }; delete m[pid]; return { models: m }; });
      return;
    }
    set((s) => ({ models: { ...s.models, [pid]: { ...providers[pid], models: s.models[pid]?.models || [], loading: true } } }));
    const r = await get().loadProviderModels(pid, true);
    if (r?.error) get().notify(t("provider_models_error", { name: r.name }), "error", r.error);
    else if (r) get().notify(t("provider_models_found", { name: r.name, n: r.models.length }), "ok");
  },
  loadMcpTools: () => api.get("/api/mcp").then((all) => set({ mcpTools: Object.entries(all || {}).filter(([, s]) => s.running)
    .flatMap(([sid, s]) => (s.tools || []).map((tl) => ({ name: `${sid}/${tl.name}`, description: tl.description || "", schema: tl.input_schema || {} }))) }))
    .catch(() => {}),
  loadCatalog: () => Promise.all([api.get("/api/skills"), api.get("/api/agents")])
    .then(([skills, agents]) => set({ catalog: { skills, agents } })).catch(() => {}),

  async updateSettings(patch) {
    const settings = await get().persist(() => api.patch("/api/settings", patch));
    set((s) => ({ settings: { ...settings, secrets: s.settings?.secrets } }));
    // The Cloudflare account id is shared with the image card: typed there, the provider re-reads its models too
    if (patch?.media && "cloudflare_account" in patch.media && settings?.providers?.cloudflare) get().refreshProvider("cloudflare");
  },
  async setSecret(name, value) {
    await get().persist(() => api.put("/api/secrets", { name, value }));
    await get().refreshSettings();
    if (name.endsWith("_api_key")) get().refreshProvider(name.slice(0, -8));
  },
  async refreshSettings() { set({ settings: await api.get("/api/settings") }); },

  currentModel() { return get().prefs.model || get().settings?.active_model || ""; },
  async selectModel(model) {
    get().setPref("model", model);
    const pid = model.split(":")[0];
    if (get().models[pid]?.local) set({ modelStatus: { model, state: "switching" } });
    await api.post("/api/models/activate", { model });
    get().loadContext();
  },
  // One place to change a model's context window: the model picker, the context panel and Settings all call it,
  // so every view shows the same value at once.
  async setModelContext(model, n) {
    const r = await get().persist(() => api.put("/api/models/context", { model, num_ctx: n }));
    set((s) => ({
      context: s.context?.model === model ? { ...s.context, current: r.current } : s.context,
      settings: s.settings ? { ...s.settings, context: { ...s.settings.context,
        num_ctx: { ...(s.settings.context?.num_ctx || {}), [model]: r.current } } } : s.settings,
    }));
    get().notify(get().t("context_size_saved", { n: r.current >= 1000 ? `${Math.round(r.current / 1000)}K` : r.current }), "ok");
    return r;
  },
  async loadContext() {
    const model = get().currentModel();
    if (!model) return;
    const asked = Date.now(), sid = get().sessionId;
    try {
      const ctx = await api.get(`/api/sessions/${sid || "new"}/context?model=${encodeURIComponent(model)}`);
      if (get().sessionId !== sid) return; // the user opened another chat meanwhile
      // A live count that arrived while this request was on its way is newer than the answer: keep it.
      const prev = get().context;
      const keepLive = _ctxLiveAt > asked && prev && get().runs[sid];
      set({ context: keepLive ? { ...ctx, used: prev.used } : ctx });
    } catch {}
  },

  // projects & sessions
  async createProject(name, path) {
    const p = await api.post("/api/projects", { name, path });
    set((s) => ({ projects: [p, ...s.projects], projectId: p.id, scope: "project", expanded: { ...s.expanded, [p.id]: true } }));
    get().newChat();
    return p;
  },
  async renameProject(id, name) {
    await api.patch(`/api/projects/${id}`, { name });
    set((s) => ({ projects: s.projects.map((p) => (p.id === id ? { ...p, name } : p)) }));
  },
  async removeProject(id) {
    const t = get().t;
    if (!(await get().confirm({ title: t("remove_project"), message: t("confirm_remove_project"), confirmLabel: t("remove_project"), danger: true }))) return;
    await api.del(`/api/projects/${id}`);
    set((s) => ({ projects: s.projects.filter((p) => p.id !== id), sessions: s.sessions.filter((x) => x.project_id !== id),
      ...(s.projectId === id ? { projectId: null, sessionId: null, messages: [] } : {}) }));
  },
  async patchSession(id, patch) {
    await api.patch(`/api/sessions/${id}`, patch);
    if (patch.archived) {
      set((s) => ({ sessions: s.sessions.filter((x) => x.id !== id) }));
      if (get().sessionId === id) get().newChat();
    } else get().refreshSessions();
  },
  async deleteSession(id) {
    const t = get().t;
    if (!(await get().confirm({ title: t("delete_chat"), message: t("confirm_delete_chat"), confirmLabel: t("delete"), danger: true }))) return;
    await api.del(`/api/sessions/${id}`);
    set((s) => ({ sessions: s.sessions.filter((x) => x.id !== id) }));
    if (get().sessionId === id) get().newChat();
  },
  newChat(projectId) {
    try { sessionStorage.removeItem("aiiq_tab"); } catch { /* no storage */ }
    set((s) => ({ sessionId: null, messages: [], hasMore: false, loadingMessages: false, quotes: [], attachments: [], msgSel: null, view: "chat", sidebarOpen: false,
      ...(projectId ? { projectId, scope: "project" } : {}) }));
    get().loadContext();
  },
  selectProject(id) { set((s) => ({ projectId: id, scope: "project", expanded: { ...s.expanded, [id]: true } })); get().newChat(); },
  async openSession(id) {
    try { sessionStorage.setItem("aiiq_tab", JSON.stringify({ session: id })); } catch { /* no storage */ }
    const s = get().sessions.find((x) => x.id === id);
    // The chat opens with its latest page (a long chat no longer loads every message at once); a loading state
    // shows until it arrives, older pages load while scrolling up (loadOlder).
    set({ sessionId: id, view: "chat", sidebarOpen: false, messages: [], hasMore: false, loadingMessages: true, msgSel: null,
      projectId: s?.project_id || get().projectId, scope: s?.project_id ? "project" : "computer",
      sessions: get().sessions.map((x) => (x.id === id && x.unread ? { ...x, unread: 0 } : x)) });
    let page, active;
    try {
      [page, active] = await Promise.all([api.get(`/api/sessions/${id}/messages?limit=${PAGE}`), api.get(`/api/sessions/${id}/active`)]);
    } catch (e) {
      if (get().sessionId === id) set({ loadingMessages: false });
      get().notify(e.message, "error");
      return;
    }
    if (get().sessionId !== id) return;
    set((st) => {
      const runs = { ...st.runs };
      if (active?.run_id && !runs[id]) runs[id] = emptyRun({ id: active.run_id, text: active.text, steps: active.steps, todos: active.todos || [], role: active.role, status: "running", started: active.started ? active.started * 1000 : Date.now() });
      // Live events may have created the run first (after a reload) with "now" as its start: the server's start
      // time wins, so the elapsed time goes on instead of starting again at 0.
      else if (active?.run_id && active.started) runs[id] = { ...runs[id], id: runs[id].id || active.run_id, started: active.started * 1000 };
      if (!active?.run_id) delete runs[id];
      // The live run's user message is already stored; the answer is not yet.
      return { messages: page.messages, hasMore: page.has_more, loadingMessages: false, runs };
    });
    get().loadContext();
  },
  hasMore: false,
  loadingMessages: false,
  loadingOlder: false,
  async loadOlder() {
    const { sessionId: id, messages, hasMore, loadingOlder } = get();
    const first = messages.find((m) => typeof m.id === "number");
    if (!id || !hasMore || loadingOlder || !first) return 0;
    set({ loadingOlder: true });
    try {
      const page = await api.get(`/api/sessions/${id}/messages?limit=${PAGE}&before=${first.id}`);
      if (get().sessionId !== id) return 0;
      set((s) => ({ messages: [...page.messages, ...s.messages], hasMore: page.has_more }));
      return page.messages.length;
    } catch { return 0; } finally { set({ loadingOlder: false }); }
  },
  // Messages added live ("local-…" sent here, "run-…" answers) get their stored ids once saved, matched by role and
  // text from the end: then they can be selected, deleted and quoted like any loaded message.
  async syncIds(sid) {
    if (get().sessionId !== sid || !get().messages.some((m) => typeof m.id !== "number")) return;
    const page = await api.get(`/api/sessions/${sid}/messages?limit=${PAGE}`).catch(() => null);
    if (!page || get().sessionId !== sid) return;
    const stored = [...page.messages];
    const taken = new Set(get().messages.filter((m) => typeof m.id === "number").map((m) => m.id));
    set((s) => ({
      messages: s.messages.map((m) => {
        if (typeof m.id === "number") return m;
        const hit = stored.slice().reverse().find((x) => !taken.has(x.id) && x.role === m.role && (x.content || "").trim() === (m.content || "").trim());
        if (!hit) return m;
        taken.add(hit.id);
        return { ...m, id: hit.id, meta: { ...hit.meta, ...m.meta } };
      }),
    }));
  },
  // Select mode from a message's "select" button: live ids are resolved first, so every message can be picked.
  async startSelect(m) {
    const sid = get().sessionId;
    set({ msgSel: new Set() });
    if (sid) await get().syncIds(sid);
    const cur = get().messages.find((x) => x === m || (x.role === m.role && x.content === m.content));
    if (cur && typeof cur.id === "number") set({ msgSel: new Set([cur.id]) });
  },
  // Selection (chat list and messages): a Set of ids while select mode is on, null otherwise.
  chatSel: null,
  msgSel: null,
  toggleSel(kind, id) {
    set((s) => {
      const cur = new Set(s[kind] || []);
      cur.has(id) ? cur.delete(id) : cur.add(id);
      return { [kind]: cur };
    });
  },
  async deleteChats(ids) {
    const t = get().t;
    if (!ids.length || !(await get().confirm({ title: t("delete_chats", { n: ids.length }), message: t("confirm_delete_chats"),
      confirmLabel: t("delete"), danger: true }))) return;
    // Gone from the list at once (also a chat that is still working); the server stops their tasks and removes the
    // folders in the background. Waiting for the answer first looked like nothing happened until a reload.
    const gone = new Set(ids);
    const before = get().sessions;
    set((s) => ({ sessions: s.sessions.filter((x) => !gone.has(x.id)), chatSel: null,
      runs: Object.fromEntries(Object.entries(s.runs).filter(([k]) => !gone.has(k))) }));
    if (gone.has(get().sessionId)) get().newChat();
    const busy = get().notify(t("deleting_chats", { n: ids.length }), "busy");
    try {
      await api.post("/api/sessions/delete", { ids });
      get().dismiss(busy);
      get().notify(t("deleted_chats", { n: ids.length }), "ok");
    } catch (e) {
      get().dismiss(busy);
      set({ sessions: before });
      get().notify(e.message, "error");
    }
  },
  async deleteMessages(all) {
    const t = get().t, sid = get().sessionId;
    const sel = get().msgSel || new Set();
    const ids = all ? [] : [...sel].filter((x) => typeof x === "number");
    if (!sid || (!all && !ids.length)) return;
    if (!(await get().confirm({ title: all ? t("delete_all_messages") : t("delete_messages", { n: ids.length }),
      message: t("confirm_delete_messages"), confirmLabel: t("delete"), danger: true }))) return;
    // Removed from the screen at once (a running task is stopped by the server first); restored if it fails.
    const gone = new Set(ids);
    const before = get().messages;
    set((s) => ({ messages: all ? [] : s.messages.filter((m) => !gone.has(m.id)), msgSel: null }));
    const n = all ? before.length : ids.length;
    const busy = get().notify(t("deleting_messages", { n }), "busy");
    try {
      await api.post(`/api/sessions/${sid}/messages/delete`, all ? { all: true } : { ids });
    } catch (e) { get().dismiss(busy); set({ messages: before }); return get().notify(e.message, "error"); }
    get().dismiss(busy);
    get().notify(t("deleted_messages", { n }), "ok");
    get().loadContext();
  },
  async deleteMessage(m) {
    const t = get().t, sid = get().sessionId;
    if (!(await get().confirm({ title: t("delete_message"), message: t("confirm_delete_message"), confirmLabel: t("delete"), danger: true }))) return;
    if (typeof m.id === "number") {
      try { await api.del(`/api/sessions/${sid}/messages/${m.id}`); } catch (e) { return get().notify(e.message, "error"); }
    } else if (sid) { // a message added live (id "run-..."/"local-..."): reload to learn its stored id, then delete
      const page = await api.get(`/api/sessions/${sid}/messages?limit=${PAGE}`).catch(() => null);
      const stored = page?.messages.slice().reverse().find((x) => x.role === m.role && x.content === m.content);
      if (stored) await api.del(`/api/sessions/${sid}/messages/${stored.id}`).catch(() => {});
    }
    set((s) => ({ messages: s.messages.filter((x) => x !== m) }));
    get().loadContext();
  },
  // "Add to chat": text selected in a message goes with the next message as a quote (optional comment).
  quotes: [],
  addQuote(q) { set((s) => ({ quotes: [...s.quotes, { ...q, id: Math.random().toString(36).slice(2) }] })); },
  removeQuote(id) { set((s) => ({ quotes: s.quotes.filter((q) => q.id !== id) })); },
  flash: null, // { messageId, text, at }: the quoted text blinks in its message
  flashQuote(q) { set({ flash: { messageId: q.messageId, text: q.text, at: Date.now() } }); },
  async moveSession(id, projectId) {
    try { await api.patch(`/api/sessions/${id}`, { project_id: projectId || null, move: true }); }
    catch (e) { return get().notify(e.message, "error"); }
    await get().refreshSessions();
    if (get().sessionId === id) set({ projectId: projectId || get().projectId, scope: projectId ? "project" : "computer" });
    get().notify(get().t("chat_moved"), "ok");
  },
  async forkSession(id) {
    try {
      const s = await api.post(`/api/sessions/${id}/fork`);
      await get().refreshSessions();
      get().openSession(s.id);
    } catch (e) { get().notify(e.message, "error"); }
  },
  async exportSession(id, mode = "copy") {
    const r = await api.get(`/api/sessions/${id}/export`);
    if (mode === "copy") { await navigator.clipboard.writeText(r.markdown); return get().notify(get().t("copied"), "ok"); }
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([r.markdown], { type: "text/markdown" }));
    a.download = `${(r.title || "chat").replace(/[\\/:*?"<>|]+/g, "_").slice(0, 60)}.md`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 2000);
  },
  async pinProject(id, pinned) {
    await api.patch(`/api/projects/${id}`, { pinned });
    set({ projects: await api.get("/api/projects") });
  },
  async archiveProjectChats(id) {
    const t = get().t;
    if (!(await get().confirm({ title: t("archive_chats"), message: t("confirm_archive_chats"), confirmLabel: t("archive") }))) return;
    await api.post(`/api/projects/${id}/archive_chats`);
    await get().refreshSessions();
    if (get().sessions.every((x) => x.id !== get().sessionId)) get().newChat(id);
  },
  async ensureSession() {
    if (get().sessionId) return get().sessionId;
    const { scope, projectId } = get();
    const s = await api.post("/api/sessions", { project_id: scope === "project" ? projectId : null });
    set((st) => ({ sessionId: s.id, sessions: [s, ...st.sessions] }));
    return s.id;
  },
  // Uploads files into the chat; images keep a base64 copy for vision models. replaceAt swaps an existing attachment.
  async addAttachments(files, replaceAt = -1) {
    const sid = await get().ensureSession();
    for (const f of files) {
      try {
        const meta = await api.upload(`/api/sessions/${sid}/upload`, f);
        const b64 = meta.kind === "image" ? await readB64(f) : undefined;
        const item = { ...meta, b64, mime: f.type || undefined };
        set((s) => ({ attachments: replaceAt >= 0 ? s.attachments.map((x, i) => (i === replaceAt ? item : x)) : [...s.attachments, item] }));
      } catch (e) { get().notify(e.message, "error"); }
    }
  },
  async refreshSessions() {
    const list = await api.get("/api/sessions");
    set({ sessions: list.map((x) => (x.id === get().sessionId ? { ...x, unread: 0 } : x)) }); // the open chat is read
  },

  modelCaps(id = get().currentModel()) {
    const [pid, ...rest] = id.split(":");
    return get().models[pid]?.models.find((m) => m.id === rest.join(":"));
  },
  async send(text, opts = {}) {
    const sid = await get().ensureSession();
    const { attachments, settings, quotes } = get();
    if (quotes.length) { // quoted parts of earlier messages go first, each with its optional comment
      text = quotes.map((q) => q.text.split("\n").map((l) => `> ${l}`).join("\n") + (q.comment ? `\n\n${q.comment}` : "")).join("\n\n")
        + "\n\n" + text;
      set({ quotes: [] });
    }
    const images = attachments.filter((a) => a.kind === "image" && a.b64).map((a) => a.b64);
    if (images.length && get().modelCaps()?.vision === false) get().notify(get().t("no_vision_warning"), "warn");
    const meta = attachments.map(({ b64, ...a }) => a);
    // The chat is working: the message is guidance for the running task (nothing stops, nothing restarts).
    const busy = !!get().runs[sid] && get().runs[sid].status !== "error";
    set((s) => ({
      messages: [...s.messages, { id: `local-${Date.now()}`, role: "user", content: text, meta: { attachments: meta, steer: busy, ...(opts.chips?.length ? { chips: opts.chips } : {}) } }],
      runs: busy ? s.runs : { ...s.runs, [sid]: emptyRun() },
      attachments: [],
    }));
    try {
      const { run_id, steered } = await api.post(`/api/sessions/${sid}/chat`, {
        text, model: get().currentModel(), permission_mode: settings?.permission_mode,
        plan_mode: !!opts.planMode, goal_mode: !!opts.goalMode, images, attachments: meta, ui_lang: get().prefs.lang,
        chips: opts.chips || [],
      });
      if (steered) { get().notify(get().t("steer_sent"), "ok"); return; }
      set((s) => ({ runs: { ...s.runs, [sid]: { ...(s.runs[sid] || emptyRun()), id: run_id, status: "running" } } }));
      if (!get().sessions.find((x) => x.id === sid)?.title) get().refreshSessions();
    } catch (e) {
      set((s) => ({ runs: { ...s.runs, [sid]: { ...s.runs[sid], status: "error", error: e.message, errorCode: "request" } } }));
    }
  },
  async cancelRun() {
    const run = get().runs[get().sessionId];
    if (run?.id) await api.post(`/api/runs/${run.id}/cancel`);
  },
  async answerApproval(sid, a, approved) {
    try { await api.post(`/api/approvals/${a.approval_id}`, { hash: a.hash, approved }); } catch {}
    set((s) => ({ runs: { ...s.runs, [sid]: { ...s.runs[sid], approvals: (s.runs[sid]?.approvals || []).filter((x) => x.approval_id !== a.approval_id) } } }));
  },

  // editor
  compressing: false,
  async compressNow() {
    const sid = get().sessionId;
    const t = get().t;
    if (get().compressing) return; // one compression at a time
    if (!sid) return get().notify(t("nothing_to_compress"), "info");
    if (get().runs[sid]) return get().notify(t("compress_busy"), "info");
    set({ compressing: true });
    const id = get().notify(t("compressing"), "busy");
    try {
      const r = await api.post(`/api/sessions/${sid}/compress`, { model: get().currentModel() });
      get().dismiss(id);
      get().notify(r.compressed ? t("compressed_result", { n: r.compressed, before: r.before, after: r.after }) : t("nothing_to_compress"), "ok");
      get().loadContext();
    } catch (e) { get().dismiss(id); get().notify(t("compress_failed"), "error", e.message); }
    finally { set({ compressing: false }); }
  },
  previewFile: (path, size) => set({ dialog: { type: "preview", path, size } }),
  playMedia: (path) => set({ dialog: { type: "media", path, kind: isVideo(path) ? "video" : "audio" } }),
  // Video Studio: a video, its <name>.timeline.json, or "" for a new project
  openStudio: (path = "") => set({ dialog: { type: "studio", path } }),
  viewImages: (paths, index = 0) => set({ dialog: { type: "images", paths, index } }),
  browse: (target) => set({ dialog: { type: "browser", ...target } }), // { path } in the working folder or { url }
  // Each kind opens in its own viewer; editor=true opens any text file (also HTML) in the code editor.
  async openFile(path, editor = false) {
    if (!editor) {
      if (docKind(path)) return get().previewFile(path); // office/PDF documents open in the previewer
      if (isImage(path)) return get().viewImages([path]);
      if (isVideo(path) || isAudio(path)) return get().playMedia(path); // video player / audio player with waveform
      if (isWebPage(path)) return get().browse({ path });
    }
    if (!isTextFile(path)) { // binary without a viewer (db, zip, exe...): download it
      window.open(get().fileApi(`/fs/raw?path=${encodeURIComponent(path)}`) + "&download=true");
      return;
    }
    // A link to a file outside the working folder (~/.claude-flow/config.json written by a command) is refused by the
    // server (403): say so instead of an uncaught promise error in the console on every click.
    let content;
    try {
      ({ content } = await api.get(get().fileApi(`/file?path=${encodeURIComponent(path)}`)));
    } catch (e) {
      get().notify(e.message || get().t("save_failed"), "error", path);
      return;
    }
    get().openBuffer({ id: path, path, content, saved: content });
  },
  openBuffer(tab) {
    set((s) => {
      const tabs = s.editor.tabs.some((t) => t.id === tab.id)
        ? s.editor.tabs.map((t) => (t.id === tab.id ? { ...t, ...tab } : t)) : [...s.editor.tabs, tab];
      return { editor: { tabs, active: tab.id }, editorOpen: true };
    });
  },
  editBuffer(id, content) {
    set((s) => ({ editor: { ...s.editor, tabs: s.editor.tabs.map((t) => (t.id === id ? { ...t, content } : t)) } }));
  },
  closeBuffer(id) {
    set((s) => {
      const tabs = s.editor.tabs.filter((t) => t.id !== id);
      return { editor: { tabs, active: tabs.at(-1)?.id || null }, editorOpen: tabs.length > 0 && s.editorOpen };
    });
  },
  async saveBuffer(id) {
    const tab = get().editor.tabs.find((t) => t.id === id);
    if (!tab) return;
    if (tab.onSave) await tab.onSave(tab.content);
    else if (tab.path) await api.put(get().fileApi("/file"), { path: tab.path, content: tab.content });
    else return;
    set((s) => ({ editor: { ...s.editor, tabs: s.editor.tabs.map((t) => (t.id === id ? { ...t, saved: t.content } : t)) } }));
    get().notify(get().t("saved"), "ok");
  },

  // After a reconnect that could not be filled from the replay buffer (or a restarted app): what may have changed
  // while this page was not listening is read again - the chat list, the open chat's messages (an answer that
  // finished meanwhile) and the processes. Running tasks arrive as snapshots through the socket itself.
  async resync() {
    const sid = get().sessionId;
    get().refreshSessions().catch(() => {});
    api.get("/api/processes").then((list) => set({ processes: Object.fromEntries(list.map((p) => [p.id, p])) })).catch(() => {});
    if (!sid) return;
    try {
      const page = await api.get(`/api/sessions/${sid}/messages?limit=${PAGE}`);
      if (get().sessionId !== sid) return;
      set((s) => {
        // Messages already loaded further up stay; the latest page replaces everything from its first message on
        // (live "run-…" / "local-…" entries are in it now with their stored ids).
        const first = page.messages[0]?.id;
        const older = first == null ? [] : s.messages.filter((m) => typeof m.id === "number" && m.id < first);
        return { messages: [...older, ...page.messages], hasMore: older.length ? s.hasMore : page.has_more };
      });
      get().loadContext();
    } catch {}
  },

  // Events are applied in batches (one state update per animation frame) to avoid flicker.
  applyEvents(events) {
    const s = get();
    let runs = s.runs, processes = s.processes, logs = s.logs, messages = s.messages;
    let { modelStatus, lastSeq } = s;
    let refresh = false, context = null, fsTick = s.fsTick;
    const touchRun = (sid) => {
      if (runs === s.runs) runs = { ...runs };
      runs[sid] = { ...(runs[sid] || emptyRun({ status: "running" })) };
      return runs[sid];
    };
    let boot = s.boot, resync = false, netEvt = null;
    const logCopied = new Set(); // a process's log array is copied once per batch, not once per line
    for (const e of events) {
      const p = e.payload || {};
      if (e.topic === "system") {
        if (e.type === "net") netEvt = p;
        if (e.type === "hello") {
          if (p.net) netEvt = { ...p.net, quiet: p.net.online }; // a (re)connect: say nothing when all is fine
          boot = p.boot;
          if (p.reset) {
            // The full state follows (a new page, the app restarted, or this client was away longer than the replay
            // buffer reaches): the server's numbering counts from here, and every running task arrives as a snapshot.
            lastSeq = e.seq || 0;
            runs = {};
            logs = {};
            logCopied.clear();
            resync = true;
          }
        }
        continue;
      }
      lastSeq = Math.max(lastSeq, e.seq || 0);
      if (e.topic === "run" && e.type === "snapshot") { // a running task as it is right now (see "hello")
        if (runs === s.runs) runs = { ...runs };
        runs[p.session_id] = emptyRun({ id: p.run_id, text: p.text || "", steps: p.steps || [], todos: p.todos || [], role: p.role,
          chat: !!p.chat, approvals: p.approvals || [], status: "running", started: p.started ? p.started * 1000 : Date.now() });
        continue;
      }
      if (e.topic === "process") {
        if (e.type === "log") {
          if (logs === s.logs) logs = { ...logs };
          if (!logCopied.has(p.process_id)) { logs[p.process_id] = [...(logs[p.process_id] || [])]; logCopied.add(p.process_id); }
          logs[p.process_id].push({ stream: p.stream, line: p.line });
        } else {
          if (processes === s.processes) processes = { ...processes };
          const next = { ...(processes[p.process_id] || { id: p.process_id, owner: p.owner }) };
          if (e.type === "started") Object.assign(next, { argv: p.argv, pid: p.pid, cwd: p.cwd, state: "running", started: e.ts });
          if (e.type === "state") Object.assign(next, { state: p.state, ...("expires_at" in p ? { expires_at: p.expires_at } : {}) });
          if (e.type === "exit") Object.assign(next, { state: p.state, exit_code: p.exit_code });
          processes[p.process_id] = next;
        }
        continue;
      }
      if (e.topic === "session" && e.type === "deleted") { // deleted here or in another window: gone from the list
        if (Date.now() / 1000 - e.ts < 60) refresh = true;
        continue;
      }
      if (e.topic === "health") { // local servers / settings changed (pushed by the server, no polling)
        setTimeout(() => get().applyHealth(p), 0);
        continue;
      }
      if (e.topic === "model" && e.type === "context") { // the backend grew a local window: picker and panel follow
        setTimeout(() => get().loadContext(), 0);
        continue;
      }
      if (e.topic === "model") { modelStatus = { model: p.model, state: e.type, message: p.message }; continue; }
      if (e.type === "location.request") { // the model asked where the user is (map search "near me")
        if (Date.now() / 1000 - e.ts < 20) answerLocation(p.request_id); // never for replayed old requests
        continue;
      }
      if (e.topic !== "run") continue;
      if (e.type === "title") { // the model named the chat after its first answer
        set((st) => ({ sessions: st.sessions.map((x) => (x.id === p.session_id ? { ...x, title: p.title, title_auto: 2 } : x)) }));
        continue;
      }
      if (e.type.startsWith("approval.")) {
        const sid = Object.keys(runs).find((k) => runs[k].id === p.run_id);
        if (!sid) continue;
        const run = touchRun(sid);
        const rest = run.approvals.filter((x) => x.approval_id !== p.approval_id);
        run.approvals = e.type === "approval.request" ? [...rest, p] : rest;
        continue;
      }
      const sid = p.session_id;
      if (!sid) continue;
      if (e.type === "done") {
        // The error may have arrived in this same batch (only in the local copy yet): read it before the run goes.
        const live = runs[sid] || s.runs[sid];
        if (runs[sid]) { if (runs === s.runs) runs = { ...runs }; delete runs[sid]; }
        // A replayed "done" (the page loaded after the task ended) of an answer already loaded from the chat is not
        // added a second time (it showed twice, and the copy could not be selected or deleted).
        const known = messages.slice(-3).some((m) => m.role === "assistant" && typeof m.id === "number"
          && (m.content || "").trim() === (p.text || "").trim());
        if (sid === s.sessionId && !known) {
          messages = [...messages, { id: `run-${p.run_id}`, role: "assistant", content: p.text,
            meta: { steps: p.steps, todos: p.todos, outputs: p.outputs, timing: p.timing, changes: p.changes, status: p.status, error: live?.error, errorCode: live?.errorCode } }];
          setTimeout(() => get().syncIds(sid), 400); // the stored ids replace the live ones (select, delete)
          context = p.context_used;
          setTimeout(() => get().loadContext(), 0); // refresh the detailed context stats
          api.patch(`/api/sessions/${sid}`, { unread: false }).catch(() => {}); // seen: the answer is on screen
          const pr = s.prefs;  // spoken replies: only answers of a run seen live here (not history replays)
          if (pr.voiceReply && s.runs[sid] && p.status === "ok" && p.text) {
            speech.speak(`run-${p.run_id}`, p.text, speech.speechOpts(pr));
          }
        }
        refresh = true;
        continue;
      }
      if (e.type === "speed") { // live output speed of the running task (tokens per second, one event a second)
        if (runs[sid]) {
          const run = touchRun(sid);
          run.tps = p.tps;
          run.tpsAt = Date.now();
        }
        continue;
      }
      if (e.type === "context") { // live context use while the task runs (each model turn)
        if (sid === s.sessionId) {
          context = p.used;
          // The task's model can change mid-run (quota auto-switch, a team member's own model): refetch the
          // window/threshold for it every few seconds so the ring's percentage never compares `used` against a
          // stale cap (the bug a user would see as the ring reading red until the panel is opened and resyncs it).
          const now = Date.now();
          _ctxLiveAt = now;
          // A model switch mid-task (quota switch, pool model): load that model's window at once.
          const switched = p.model && s.context && s.context.model !== p.model;
          // The live count itself comes with this event; the detailed panel data is refetched rarely (a request every
          // 4 s for the whole task, scanning every stored step, was most of the server log during long tasks).
          if (switched || now - _ctxResyncAt > 30000) { _ctxResyncAt = now; get().loadContext(); }
        }
        continue;
      }
      const run = touchRun(sid);
      run.id = run.id || p.run_id;
      run.status = "running";
      if (e.type === "delta") run.text += p.text;
      else if (e.type === "reset_text") run.text = "";
      else if (e.type === "agent") run.role = p.role;
      else if (e.type === "reply_mode") run.chat = !!p.chat;
      else if (e.type === "todos") run.todos = p.todos;
      else if (e.type === "step_remove") run.steps = run.steps.filter((x) => x.id !== p.step_id);
      else if (e.type === "error") { run.error = p.message; run.errorCode = p.code; }
      else if (e.type === "step") {
        if (p.step.status === "done" && ["write_file", "edit_file", "delete_file", "make_doc"].includes(p.step.data?.tool)) fsTick += 1;
        if (p.step.status === "done" && p.step.data?.tool === "save_catalog") get().loadCatalog(); // new skill/agent shows at once
        // A Markdown file the task wrote in the open chat opens in the editor (Monaco) at once: once per file and run.
        const mdPath = p.step.data?.path;
        if (p.step.status === "done" && sid === s.sessionId && ["write_file", "edit_file"].includes(p.step.data?.tool)
            && /\.(md|markdown|mdx)$/i.test(mdPath || "") && !(run.openedMd || []).includes(mdPath)) {
          run.openedMd = [...(run.openedMd || []), mdPath];
          setTimeout(() => get().openFile(mdPath).catch(() => {}), 0);
        }
        if (p.step.kind === "thinking" && (p.step.detail || "").length > 4000) p.step.detail = "…" + p.step.detail.slice(-4000);
        const i = run.steps.findIndex((x) => x.id === p.step.id);
        run.steps = i < 0 ? [...run.steps, p.step] : run.steps.map((x, j) => (j === i ? p.step : x));
      }
    }
    for (const id of logCopied) if (logs[id].length > 2000) logs[id] = logs[id].slice(-2000);
    set({ runs, processes, logs, messages, modelStatus, lastSeq, fsTick, boot,
      ...(context != null && s.context ? { context: { ...s.context, used: context } } : {}) });
    if (refresh) get().refreshSessions();
    if (resync && s.boot) get().resync(); // not on the first connection of a page (bootstrap loads everything)
    if (netEvt) get().applyNet(netEvt);
  },
}));

// Localized catalog metadata (title_<lang>, description_<lang>) with fallback to the generic field.
export const loc = (item, field) => item?.[`${field}_${useStore.getState().prefs.lang}`] || item?.[field] || "";

export const useT = () => {
  useStore((s) => s.dict);
  return useStore.getState().t;
};
