import { create } from "zustand";
import { api, setErrorTranslator } from "./api";
import { docKind, isImage } from "./fileTypes";

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

const PREFS_KEY = "aiiq.prefs";
const loadPrefs = () => { try { return JSON.parse(localStorage.getItem(PREFS_KEY)) || {}; } catch { return {}; } };
const savePrefs = (p) => { try { localStorage.setItem(PREFS_KEY, JSON.stringify(p)); } catch {} };

export const emptyRun = (extra = {}) => ({ id: null, text: "", steps: [], todos: [], approvals: [], status: "starting", error: null, role: null, ...extra });

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
  confirmState: null, // { title, message, confirmLabel, danger, resolve }
  saveState: { state: "idle", at: null, error: null }, // settings persistence indicator
  lastSeq: 0,
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
  // File API base for the current chat; before a chat exists it targets the selected project or workspace/.
  fileApi(path) {
    const { sessionId, scope, projectId } = get();
    const q = !sessionId && scope === "project" && projectId ? `project_id=${projectId}` : "";
    const sep = path.includes("?") ? "&" : "?";
    return `/api/sessions/${sessionId || "new"}${path}${q ? sep + q : ""}`;
  },

  async loadLanguage(code) {
    const dict = await api.get(`/api/languages/${code}`);
    get().setPref("lang", code);
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
    get().loadModels();
    get().loadCatalog();
    api.get("/api/processes").then((list) => set({ processes: Object.fromEntries(list.map((p) => [p.id, p])) }));
    if (projects[0]) set({ projectId: projects[0].id });
  },
  // Each provider's models load in parallel and appear as soon as they arrive (no waiting for the slowest one).
  async loadModels() {
    let providers;
    try { providers = await api.get("/api/models/providers"); } catch { return; }
    set((s) => ({ models: Object.fromEntries(Object.entries(providers).map(([pid, p]) =>
      [pid, s.models[pid] ? { ...s.models[pid], ...p } : { ...p, models: [], loading: true }])) }));
    await Promise.all(Object.keys(providers).map((pid) => get().loadProviderModels(pid)));
    get().ensureModel();
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
  loadCatalog: () => Promise.all([api.get("/api/skills"), api.get("/api/agents")])
    .then(([skills, agents]) => set({ catalog: { skills, agents } })).catch(() => {}),

  async updateSettings(patch) {
    const settings = await get().persist(() => api.patch("/api/settings", patch));
    set((s) => ({ settings: { ...settings, secrets: s.settings?.secrets } }));
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
    try { set({ context: await api.get(`/api/sessions/${get().sessionId || "new"}/context?model=${encodeURIComponent(model)}`) }); } catch {}
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
    set((s) => ({ sessionId: null, messages: [], attachments: [], view: "chat", sidebarOpen: false,
      ...(projectId ? { projectId, scope: "project" } : {}) }));
    get().loadContext();
  },
  selectProject(id) { set((s) => ({ projectId: id, scope: "project", expanded: { ...s.expanded, [id]: true } })); get().newChat(); },
  async openSession(id) {
    const s = get().sessions.find((x) => x.id === id);
    set({ sessionId: id, view: "chat", sidebarOpen: false,
      projectId: s?.project_id || get().projectId, scope: s?.project_id ? "project" : "computer" });
    const [msgs, active] = await Promise.all([api.get(`/api/sessions/${id}/messages`), api.get(`/api/sessions/${id}/active`)]);
    if (get().sessionId !== id) return;
    set((st) => {
      const runs = { ...st.runs };
      if (active?.run_id && !runs[id]) runs[id] = emptyRun({ id: active.run_id, text: active.text, steps: active.steps, todos: active.todos || [], role: active.role, status: "running" });
      if (!active?.run_id) delete runs[id];
      // The live run's user message is already stored; the answer is not yet.
      return { messages: msgs, runs };
    });
    get().loadContext();
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
  async refreshSessions() { set({ sessions: await api.get("/api/sessions") }); },

  modelCaps(id = get().currentModel()) {
    const [pid, ...rest] = id.split(":");
    return get().models[pid]?.models.find((m) => m.id === rest.join(":"));
  },
  async send(text, opts = {}) {
    const sid = await get().ensureSession();
    const { attachments, settings } = get();
    const images = attachments.filter((a) => a.kind === "image" && a.b64).map((a) => a.b64);
    if (images.length && get().modelCaps()?.vision === false) get().notify(get().t("no_vision_warning"), "warn");
    const meta = attachments.map(({ b64, ...a }) => a);
    set((s) => ({
      messages: [...s.messages, { id: `local-${Date.now()}`, role: "user", content: text, meta: { attachments: meta } }],
      runs: { ...s.runs, [sid]: emptyRun() },
      attachments: [],
    }));
    try {
      const { run_id } = await api.post(`/api/sessions/${sid}/chat`, {
        text, model: get().currentModel(), permission_mode: settings?.permission_mode,
        plan_mode: !!opts.planMode, goal_mode: !!opts.goalMode, images, attachments: meta, ui_lang: get().prefs.lang,
      });
      set((s) => ({ runs: { ...s.runs, [sid]: { ...s.runs[sid], id: run_id, status: "running" } } }));
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
  viewImages: (paths, index = 0) => set({ dialog: { type: "images", paths, index } }),
  browse: (target) => set({ dialog: { type: "browser", ...target } }), // { path } in the working folder or { url }
  async openFile(path) {
    if (docKind(path)) return get().previewFile(path); // office/PDF documents open in the previewer
    if (isImage(path)) return get().viewImages([path]);
    const { content } = await api.get(get().fileApi(`/file?path=${encodeURIComponent(path)}`));
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
    for (const e of events) {
      lastSeq = Math.max(lastSeq, e.seq);
      const p = e.payload;
      if (e.topic === "process") {
        if (e.type === "log") {
          if (logs === s.logs) logs = { ...logs };
          logs[p.process_id] = [...(logs[p.process_id] || []), { stream: p.stream, line: p.line }].slice(-2000);
        } else {
          if (processes === s.processes) processes = { ...processes };
          const next = { ...(processes[p.process_id] || { id: p.process_id, owner: p.owner }) };
          if (e.type === "started") Object.assign(next, { argv: p.argv, pid: p.pid, cwd: p.cwd, state: "running", started: e.ts });
          if (e.type === "state") next.state = p.state;
          if (e.type === "exit") Object.assign(next, { state: p.state, exit_code: p.exit_code });
          processes[p.process_id] = next;
        }
        continue;
      }
      if (e.topic === "model") { modelStatus = { model: p.model, state: e.type, message: p.message }; continue; }
      if (e.type === "location.request") { // the model asked where the user is (map search "near me")
        if (Date.now() / 1000 - e.ts < 20) answerLocation(p.request_id); // never for replayed old requests
        continue;
      }
      if (e.topic !== "run") continue;
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
        if (runs[sid]) { if (runs === s.runs) runs = { ...runs }; delete runs[sid]; }
        if (sid === s.sessionId) {
          messages = [...messages, { id: `run-${p.run_id}`, role: "assistant", content: p.text,
            meta: { steps: p.steps, todos: p.todos, outputs: p.outputs, timing: p.timing, changes: p.changes, status: p.status, error: s.runs[sid]?.error, errorCode: s.runs[sid]?.errorCode } }];
          context = p.context_used;
          setTimeout(() => get().loadContext(), 0); // refresh the detailed context stats
          const pr = s.prefs;  // spoken replies: only answers of a run seen live here (not history replays)
          if (pr.voiceReply && s.runs[sid] && p.status === "ok" && p.text) {
            import("./speech").then((sp) => sp.speak(`run-${p.run_id}`, p.text, sp.speechOpts(pr)));
          }
        }
        refresh = true;
        continue;
      }
      if (e.type === "context") { // live context use while the task runs (each model turn)
        if (sid === s.sessionId) context = p.used;
        continue;
      }
      const run = touchRun(sid);
      run.id = run.id || p.run_id;
      run.status = "running";
      if (e.type === "delta") run.text += p.text;
      else if (e.type === "reset_text") run.text = "";
      else if (e.type === "agent") run.role = p.role;
      else if (e.type === "todos") run.todos = p.todos;
      else if (e.type === "step_remove") run.steps = run.steps.filter((x) => x.id !== p.step_id);
      else if (e.type === "error") { run.error = p.message; run.errorCode = p.code; }
      else if (e.type === "step") {
        if (p.step.status === "done" && ["write_file", "edit_file", "delete_file", "make_doc"].includes(p.step.data?.tool)) fsTick += 1;
        if (p.step.status === "done" && p.step.data?.tool === "save_catalog") get().loadCatalog(); // new skill/agent shows at once
        const i = run.steps.findIndex((x) => x.id === p.step.id);
        run.steps = i < 0 ? [...run.steps, p.step] : run.steps.map((x, j) => (j === i ? p.step : x));
      }
    }
    set({ runs, processes, logs, messages, modelStatus, lastSeq, fsTick,
      ...(context != null && s.context ? { context: { ...s.context, used: context } } : {}) });
    if (refresh) get().refreshSessions();
  },
}));

// Localized catalog metadata (title_<lang>, description_<lang>) with fallback to the generic field.
export const loc = (item, field) => item?.[`${field}_${useStore.getState().prefs.lang}`] || item?.[field] || "";

export const useT = () => {
  useStore((s) => s.dict);
  return useStore.getState().t;
};
