import { memo, useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowUp, Bot, Camera, Check, ChevronDown, Chrome, Cpu, Cloud, FileSpreadsheet, FileText, FileType2, FolderGit2, FolderUp, ListTodo, Loader2, Mic,
  Paperclip, PenTool, Plus, Presentation, RefreshCw, Search, Settings2, Shield, ShieldCheck, ShieldAlert, SlidersHorizontal, Sparkles, Square, Target, Gauge, AudioLines,
  MessageSquareQuote, Pencil, Trash2, X, Brain,
} from "lucide-react";
import { loc, useStore, useT } from "../lib/store";
import { api } from "../lib/api";
import { formatTokens } from "../lib/fileTypes";
import { FileChip, MenuItem, MenuSep, Popover, useOutside } from "./ui";
import RichInput from "./RichInput";
import CatalogPicker from "./CatalogPicker";
import ContextPanel from "./ContextPanel";
import DrawingDialog from "./DrawingDialog";
import { CapIcons } from "./Caps";

const PERMS = [
  { id: "ask", key: "perm_ask", icon: Shield },
  { id: "auto", key: "perm_auto", icon: ShieldCheck },
  { id: "full", key: "perm_full", icon: ShieldAlert },
];

// ---------- permission mode menu ----------
const PermissionMenu = memo(function PermissionMenu() {
  const t = useT();
  const mode = useStore((s) => s.settings?.permission_mode || "auto");
  const [open, setOpen] = useState(false);
  const set = (id) => { useStore.getState().updateSettings({ permission_mode: id }); setOpen(false); };
  useEffect(() => {
    if (!open) return;
    const k = (e) => { const i = Number(e.key) - 1; if (PERMS[i]) set(PERMS[i].id); };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [open]);
  const cur = PERMS.find((p) => p.id === mode) || PERMS[1];
  return (
    <div className="relative">
      <button onClick={() => setOpen(!open)}
        title={t(cur.key)} className={`flex h-8 shrink-0 items-center gap-1 whitespace-nowrap rounded-full px-2 text-[13px] hover:bg-hover md:px-2.5 ${mode === "full" ? "text-warn" : "text-muted"}`}>
        <cur.icon size={15} className="shrink-0" /><span className="hidden whitespace-nowrap md:inline">{t(cur.key)}</span><ChevronDown size={13} className="shrink-0" />
      </button>
      {open && (
        <Popover onClose={() => setOpen(false)} className="bottom-full left-0 mb-2 w-[300px]">
          <div className="px-2.5 pb-1 pt-1.5 text-xs font-medium text-subtle">{t("mode")}</div>
          {PERMS.map((p, i) => (
            <MenuItem key={p.id} label={t(p.key)} desc={t(p.key + "_desc")} onClick={() => set(p.id)} shortcut={String(i + 1)}
              right={mode === p.id && <Check size={15} className="mt-0.5 shrink-0 text-accent" />} />
          ))}
        </Popover>
      )}
    </div>
  );
});

// ---------- reasoning effort ----------
// Levels come from the model's API data (router.effort_spec); "prompt" models get an instruction instead.
const EffortMenu = memo(function EffortMenu() {
  const t = useT();
  const model = useStore((s) => s.prefs.model || s.settings?.active_model || "");
  const caps = useStore((s) => s.modelCaps(model));
  const prof = useStore((s) => s.settings?.model_profiles?.[model]) || {};
  const [open, setOpen] = useState(false);
  const levels = caps?.efforts || [];
  if (!model || !levels.length) return null;
  const cur = levels.includes(prof.effort) ? prof.effort : "";
  const set = async (effort) => {
    setOpen(false);
    const st = useStore.getState();
    try {
      await api.put("/api/models/profile", { thinking: "auto", vision: "auto", streaming: "auto", tools: "auto", ...prof, model, effort: effort || null });
      await st.refreshSettings();
      st.loadProviderModels(model.split(":")[0]);
    } catch (e) { st.notify(t("profile_save_failed"), "error", e.message); }
  };
  return (
    <div className="relative">
      <button onClick={() => setOpen(!open)} title={t("effort")}
        className={`flex h-8 shrink-0 items-center gap-1 rounded-full px-1.5 text-[12.5px] hover:bg-hover sm:px-2 ${open ? "bg-hover text-fg" : cur ? "text-accent" : "text-muted"}`}>
        <Gauge size={14} /><span className="hidden sm:inline">{t(cur ? `effort_${cur}` : "effort_auto")}</span><ChevronDown size={12} className="hidden sm:block" />
      </button>
      {open && (
        <Popover onClose={() => setOpen(false)} className="bottom-full right-0 mb-2 w-[290px]">
          <div className="px-2.5 pb-1 pt-1.5 text-xs leading-snug text-subtle">{t(caps.effort_via === "prompt" ? "effort_desc_prompt" : "effort_desc_api")}</div>
          {["", ...levels].map((l) => (
            <MenuItem key={l || "auto"} label={t(l ? `effort_${l}` : "effort_auto")} desc={l ? null : t("effort_auto_desc")} onClick={() => set(l)}
              right={cur === l && <Check size={15} className="mt-0.5 shrink-0 text-accent" />} />
          ))}
        </Popover>
      )}
    </div>
  );
});

// ---------- thinking on/off ----------
// Shown only when the model's API data says it can think (Ollama capabilities, OpenRouter reasoning, Anthropic...);
// saved in the model profile, which every request of that model follows.
const ThinkToggle = memo(function ThinkToggle() {
  const t = useT();
  const model = useStore((s) => s.prefs.model || s.settings?.active_model || "");
  const caps = useStore((s) => s.modelCaps(model));
  const prof = useStore((s) => s.settings?.model_profiles?.[model]) || {};
  if (!model || !(caps?.can_think ?? caps?.thinking)) return null;
  const on = prof.thinking !== "off";
  const flip = async () => {
    const st = useStore.getState();
    try {
      await api.put("/api/models/profile", { vision: "auto", streaming: "auto", tools: "auto", ...prof, model, thinking: on ? "off" : "on" });
      await st.refreshSettings();
      st.loadProviderModels(model.split(":")[0]);
    } catch (e) { st.notify(t("profile_save_failed"), "error", e.message); }
  };
  return (
    <button onClick={flip} title={t(on ? "think_on_hint" : "think_off_hint")}
      className={`flex h-8 shrink-0 items-center gap-1 rounded-full px-1.5 text-[12.5px] hover:bg-hover sm:px-2 ${on ? "text-accent" : "text-muted"}`}>
      <Brain size={14} /><span className="hidden sm:inline">{t(on ? "think_on" : "think_off")}</span>
    </button>
  );
});

// ---------- model picker ----------
// Context window of a local model, editable right here (synced with Settings > Context and the context panel).
function ContextEditor({ id, max, current, onDone }) {
  const t = useT();
  const [v, setV] = useState(current || max || 32768);
  const presets = [8192, 16384, 32768, 65536, 131072, 262144].filter((n) => !max || n <= max);
  const save = async (n) => { setV(n); await useStore.getState().setModelContext(id, n); onDone?.(); };
  return (
    <div className="fade-in mx-1 mb-1.5 rounded-xl border border-line bg-bg p-2.5" onClick={(e) => e.stopPropagation()}>
      <div className="mb-1.5 flex items-center justify-between text-[12px]">
        <span className="font-medium">{t("context_size")}</span>
        <span className="font-mono text-muted">{formatTokens(v)}{max ? ` / ${formatTokens(max)}` : ""}</span>
      </div>
      <input type="range" className="slider w-full" min={2048} max={max || 262144} step={1024} value={v}
        onChange={(e) => setV(+e.target.value)} onMouseUp={() => save(v)} onTouchEnd={() => save(v)} onKeyUp={(e) => e.key.startsWith("Arrow") && save(v)} />
      <div className="mt-2 flex flex-wrap gap-1">
        {presets.map((n) => (
          <button key={n} onClick={() => save(n)}
            className={`rounded-md px-1.5 py-0.5 font-mono text-[11px] ${n === v ? "bg-accent text-accent-fg" : "bg-hover text-muted hover:text-fg"}`}>{formatTokens(n)}</button>
        ))}
      </div>
    </div>
  );
}

// Provider id as shown before a model name: "ollama_cloud" -> "ollama-cloud".
const prefixOf = (pid) => String(pid || "").replace(/_/g, "-");

const ModelPicker = memo(function ModelPicker() {
  const t = useT();
  const models = useStore((s) => s.models);
  const status = useStore((s) => s.modelStatus);
  const overrides = useStore((s) => s.settings?.context?.num_ctx) || {};
  const ctx = useStore((s) => s.context);
  const model = useStore((s) => s.prefs.model || s.settings?.active_model || "");
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [edit, setEdit] = useState(null);
  const [loading, setLoading] = useState(false);
  // Every model carries its provider prefix (ollama:, ollama-cloud:, openrouter:...): searching "openrouter:" or
  // "cloud qwen" finds the right one among providers that serve models of the same name.
  const groups = useMemo(() => {
    const words = q.toLowerCase().split(/\s+/).filter(Boolean);
    return Object.entries(models)
      .map(([pid, p]) => ({ pid, ...p, models: p.models.filter((m) => {
        const hay = `${prefixOf(pid)}:${m.id} ${pid}:${m.id} ${p.name || ""}`.toLowerCase();
        return words.every((w) => hay.includes(w));
      }) }))
      .filter((g) => !q || g.models.length)
      .sort((a, b) => b.local - a.local);
  }, [models, q]);
  const pidOf = model.split(":")[0];
  const short = model.split(":").slice(1).join(":") || model || t("select_model");
  const switching = status?.state === "switching" && status.model === model;
  const refresh = async () => {
    if (loading) return;
    setLoading(true);
    try { await useStore.getState().loadModels(true); } finally { setLoading(false); }
  };
  // The window actually used: the saved override, the live value of the active model, or the model maximum.
  // Local models without a saved size run with the model file's num_ctx, else the backend default (router.LOCAL_DEFAULT_CTX).
  const currentOf = (id, m, local) => overrides[id] || (ctx?.model === id ? ctx.current : null)
    || (local ? Math.min(m.default_ctx || 32768, m.context || Infinity) : m.context);

  return (
    <div className="relative min-w-0 max-w-[150px] shrink sm:max-w-[240px]">
      <button onClick={() => setOpen(!open)} className={`flex h-8 max-w-full items-center gap-1 rounded-full px-2 text-[13px] hover:bg-hover sm:px-2.5 ${open ? "bg-hover text-fg" : "text-muted"}`}>
        {switching ? <Loader2 size={13} className="shrink-0 animate-spin text-accent" /> : null}
        <span className="truncate">{model && pidOf && <span className="text-subtle">{prefixOf(pidOf)}:</span>}{short}</span>
        {ctx?.model === model && ctx.current && <span className="hidden shrink-0 font-mono text-[10.5px] text-subtle sm:inline">{formatTokens(ctx.current)}</span>}
        <ChevronDown size={13} className={`shrink-0 transition ${open ? "rotate-180" : ""}`} />
      </button>
      {open && (
        <Popover onClose={() => { setOpen(false); setEdit(null); }} className="bottom-full right-0 mb-2 flex max-h-[min(520px,72vh)] w-[min(380px,calc(100vw-24px))] flex-col p-0">
          <div className="flex items-center gap-2 border-b border-line px-3 py-2.5">
            <Search size={14} className="text-subtle" />
            <input autoFocus value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("search_models")} className="min-w-0 flex-1 bg-transparent text-[13px] outline-none" />
            <button onClick={refresh} title={t("refresh")} className="rounded-md p-1 text-subtle hover:bg-hover"><RefreshCw size={13} className={loading ? "animate-spin" : ""} /></button>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto px-2 py-1.5">
            {groups.length === 0 && <div className="px-3 py-6 text-center text-xs text-subtle">{t("no_model")}</div>}
            {groups.map((g, gi) => (
              <div key={g.pid} className={gi ? "mt-2 border-t border-line pt-2" : ""}>
                <div className="flex items-center gap-1.5 px-2 pb-1.5 pt-1 text-[11px] font-semibold uppercase tracking-wide text-subtle">
                  {g.local ? <Cpu size={12} className="text-accent" /> : <Cloud size={12} className="text-accent" />}
                  <span className="truncate normal-case tracking-normal text-[12px] text-fg">{g.name}</span>
                  <span className="rounded bg-hover px-1 py-px text-[10px] font-medium normal-case tracking-normal">{g.local ? t("local") : t("cloud")}</span>
                  {g.loading && <Loader2 size={12} className="animate-spin text-accent" />}
                  {g.error && <span className="ml-auto truncate normal-case tracking-normal text-danger" title={g.error}>{t("offline")}</span>}
                </div>
                <div className="space-y-1">
                  {g.models.map((m) => {
                    const id = `${g.pid}:${m.id}`;
                    const active = id === model;
                    const cur = currentOf(id, m, g.local);
                    return (
                      <div key={id}>
                        <div onClick={() => { useStore.getState().selectModel(id); setOpen(false); setEdit(null); }} role="button"
                          className={`group flex cursor-pointer items-center gap-2 rounded-xl border px-2.5 py-2 text-[13px] transition ${active ? "border-accent/40 bg-accent-soft" : "border-transparent hover:bg-hover"}`}>
                          <span className={`min-w-0 flex-1 truncate ${active ? "font-medium" : ""}`} title={`${prefixOf(g.pid)}:${m.id}`}>
                            <span className="font-normal text-subtle">{prefixOf(g.pid)}:</span>{m.id}</span>
                          <CapIcons m={m} />
                          {cur && (
                            <button onClick={(e) => { e.stopPropagation(); if (g.local) setEdit(edit === id ? null : id); }}
                              title={g.local ? t("edit_context") : t("context")}
                              className={`flex shrink-0 items-center gap-1 rounded-md px-1.5 py-0.5 font-mono text-[10.5px] ${g.local ? "bg-elev text-muted ring-1 ring-line hover:text-accent hover:ring-accent" : "bg-hover text-muted"}`}>
                              {formatTokens(cur)}{g.local && m.context && cur !== m.context ? <span className="text-subtle">/{formatTokens(m.context)}</span> : null}
                              {g.local && <SlidersHorizontal size={10} />}
                            </button>
                          )}
                          {active && <Check size={14} className="shrink-0 text-accent" />}
                        </div>
                        {edit === id && <ContextEditor id={id} max={m.context} current={cur} />}
                      </div>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>
          <div className="border-t border-line p-1.5">
            <MenuItem icon={Settings2} label={t("manage_models")} onClick={() => { useStore.getState().setView("settings"); useStore.setState({ settingsTab: "providers" }); setOpen(false); }} />
            {status?.state === "error" && <div className="px-2.5 pb-1 text-xs text-danger">{status.message}</div>}
          </div>
        </Popover>
      )}
    </div>
  );
});

// ---------- quotes added from messages ("Add to chat") ----------
function QuoteChips() {
  const t = useT();
  const quotes = useStore((s) => s.quotes);
  const [open, setOpen] = useState(false);
  const [edit, setEdit] = useState(null);
  const [flashing, setFlashing] = useState(false);
  const ref = useRef(null);
  useOutside(ref, () => { setOpen(false); setEdit(null); }, open);
  if (!quotes.length) return null;
  const st = useStore.getState();
  const show = (q) => { st.flashQuote(q); setFlashing(true); setTimeout(() => setFlashing(false), 1900); };
  return (
    <div ref={ref} className="relative px-3 pt-3" onMouseEnter={() => setOpen(true)}>
      <div className={`inline-flex items-center gap-1.5 rounded-xl border border-line bg-hover px-2.5 py-1 text-[12.5px] font-medium ${flashing ? "chip-flash" : ""}`}>
        <button onClick={() => (quotes.length === 1 ? show(quotes[0]) : setOpen(!open))} className="flex items-center gap-1.5">
          <MessageSquareQuote size={14} className="text-accent" />{t("quotes_n", { n: quotes.length })}
        </button>
        <button onClick={() => useStore.setState({ quotes: [] })} title={t("remove")} className="rounded-full p-0.5 text-subtle hover:bg-active hover:text-fg"><X size={12} /></button>
      </div>
      {open && (
        <div className="fade-in absolute bottom-full left-3 z-40 mb-1 w-[min(420px,calc(100vw-40px))] rounded-2xl border border-line bg-elev p-1.5 shadow-xl"
          onMouseLeave={() => !edit && setOpen(false)}>
          {quotes.map((q, i) => (
            <div key={q.id} className="group flex items-start gap-2 rounded-xl px-2.5 py-2 hover:bg-hover">
              <span className="mt-0.5 text-xs text-subtle">{i + 1}.</span>
              <div className="min-w-0 flex-1 cursor-pointer" onClick={() => show(q)} title={t("show_in_chat")}>
                <div className="text-[11px] text-subtle">{t("selected_text")}:</div>
                <div className="line-clamp-2 text-[13px]">{q.text}</div>
                {edit === q.id ? (
                  <input autoFocus defaultValue={q.comment} placeholder={t("quote_comment_ph")} onClick={(e) => e.stopPropagation()}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") { useStore.setState((s) => ({ quotes: s.quotes.map((x) => (x.id === q.id ? { ...x, comment: e.target.value } : x)) })); setEdit(null); }
                      if (e.key === "Escape") setEdit(null);
                    }}
                    className="mt-1 w-full rounded-lg border border-line bg-bg px-2 py-1 text-[12.5px] outline-none focus:border-accent" />
                ) : q.comment ? <div className="mt-0.5 text-[12.5px] text-muted">“{q.comment}”</div> : null}
              </div>
              <button onClick={() => setEdit(q.id)} title={t("edit")} className="rounded p-1 text-subtle hover:text-fg"><Pencil size={13} /></button>
              <button onClick={() => st.removeQuote(q.id)} title={t("remove")} className="rounded p-1 text-subtle hover:text-danger"><Trash2 size={13} /></button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function Composer() {
  const t = useT();
  const sessionId = useStore((s) => s.sessionId);
  const running = useStore((s) => !!s.runs[s.sessionId]);
  const attachments = useStore((s) => s.attachments);
  const catalog = useStore((s) => s.catalog);
  const lang = useStore((s) => s.prefs.lang);
  const [text, setTextState] = useState("");
  const [before, setBefore] = useState(""); // text before the caret (for / and @ suggestions)
  const [menu, setMenu] = useState(false);
  const [picker, setPicker] = useState(null); // "/" or "@" browse list opened from the + menu
  const [planMode, setPlanMode] = useState(false);
  const [goalMode, setGoalMode] = useState(false);
  const [drawing, setDrawing] = useState(false);
  const folderInput = useRef(null);
  const [listening, setListening] = useState(false);
  const [sel, setSel] = useState(0);
  const [editing, setEditing] = useState(null); // index of the attached image open in the editor
  const fileInput = useRef(null);
  const ta = useRef(null); // the rich editor's handle
  const st = useStore.getState();
  const names = useMemo(() => ({ "@": new Set(catalog.agents.map((x) => x.name)), "/": new Set(catalog.skills.map((x) => x.name)) }), [catalog]);
  // Callers that used to set the textarea value: plain text into the editor (function form keeps working).
  const setText = (v) => {
    const next = typeof v === "function" ? v(ta.current?.getMarkdown() || "") : v;
    if (!next) ta.current?.clear(); else ta.current?.setText(next);
  };

  useEffect(() => { ta.current?.focus(); }, [sessionId]);
  useEffect(() => {
    const f = () => ta.current?.focus();
    addEventListener("aiiq:focus-composer", f);
    return () => removeEventListener("aiiq:focus-composer", f);
  }, []);

  const mention = useMemo(() => {
    const m = before.match(/(?:^|[\s\u00a0])([@/])([\w-]*)$/);
    if (!m) return null;
    const list = m[1] === "/" ? catalog.skills : catalog.agents;
    return list.length ? { trigger: m[1], query: m[2] } : null;
  }, [before, catalog]);
  const pickItems = useRef([]);
  useEffect(() => setSel(0), [mention?.query, mention?.trigger]);

  const submit = (override) => {
    const value = (override ?? ta.current?.getMarkdown() ?? text).trim();
    if (!value) return; // while a task runs the message steers it (store.send)
    st.send(value, { planMode, goalMode });
    if (override == null) ta.current?.clear();
  };
  const insert = (name, sig = mention?.trigger) => { ta.current?.insertMention(sig, name); setPicker(null); };
  const addFiles = (files) => st.addAttachments(files);
  // A whole folder goes into the chat's working folder with its structure; the message mentions where it is.
  const addFolder = async (files) => {
    if (!files.length) return;
    const sid = await st.ensureSession();
    const rel = (f) => f.relPath || f.webkitRelativePath;
    const top = rel(files[0]).split("/")[0];
    const id = st.notify(t("uploading_folder", { name: top, n: files.length }), "busy");
    let ok = 0;
    for (const f of files) {
      const dir = rel(f).split("/").slice(0, -1).join("/");
      try { await api.upload(`/api/sessions/${sid}/fs/upload?path=${encodeURIComponent(dir)}`, f); ok += 1; } catch {}
    }
    st.dismiss(id);
    st.notify(t("folder_uploaded", { name: top, n: ok }), ok === files.length ? "ok" : "warn");
    useStore.setState((s) => ({ fsTick: s.fsTick + 1 }));
    ta.current?.insertText(`${ta.current?.getMarkdown() ? " " : ""}${t("folder_ref", { name: top })} `);
  };
  // Files and folders dropped anywhere on the chat (ChatView's drop zone) arrive here.
  const dropRef = useRef(null);
  dropRef.current = ({ files, folders }) => { if (files.length) addFiles(files); for (const f of folders) addFolder(f); };
  useEffect(() => {
    const on = (e) => dropRef.current(e.detail);
    addEventListener("aiiq:drop", on);
    return () => removeEventListener("aiiq:drop", on);
  }, []);
  const onKeyDown = (e) => {
    const n = pickItems.current.length;
    if (mention && n) {
      if (e.key === "ArrowDown") { e.preventDefault(); return setSel((sel + 1) % n); }
      if (e.key === "ArrowUp") { e.preventDefault(); return setSel((sel - 1 + n) % n); }
      if (e.key === "Enter" || e.key === "Tab") { e.preventDefault(); return insert(pickItems.current[sel].name); }
      if (e.key === "Escape") { e.preventDefault(); return setBefore(""); }
    }
  };
  const mic = () => {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) return st.notify(t("mic_unsupported"), "error");
    const r = new SR();
    r.lang = lang === "tr" ? "tr-TR" : lang;
    r.onresult = (e) => ta.current?.insertText((ta.current?.getMarkdown() ? " " : "") + e.results[0][0].transcript);
    r.onend = () => setListening(false);
    setListening(true);
    r.start();
  };
  const prefix = (p) => { setText((x) => p + x); setMenu(false); };
  const plusRef = useRef(null);
  const menuRef = useRef(null);
  useOutside(menuRef, () => setMenu(false), menu, () => plusRef.current);
  const pickerRef = useRef(null);
  useOutside(pickerRef, () => setPicker(null), !!picker);

  // Voice task control (lib/voiceControl): commands run the app, other speech is dictated into the box.
  const [voice, setVoice] = useState("off");
  const vc = useRef(null);
  const textRef = useRef(text);
  textRef.current = text;
  const onVoice = useRef(null);
  onVoice.current = ({ cmd, text: said }) => {
    const s = useStore.getState();
    const sid = s.sessionId;
    const full = [textRef.current, said].filter(Boolean).join(" ").trim();
    if (!cmd) { if (said) setText(full); return; }
    const done = (key) => s.notify(t(key), "ok");
    if (cmd === "send") {
      if (!full) return s.notify(t("voice_nothing_to_send"), "warn");
      if (running) return s.notify(t("voice_busy"), "warn");
      setText("");
      s.send(full, { planMode, goalMode });
      return done("voice_cmd_send");
    }
    if (cmd === "stop") { if (running) { s.cancelRun(); done("voice_cmd_stop"); } return; }
    if (cmd === "approve" || cmd === "deny") {
      const a = sid && s.runs[sid]?.approvals?.[0];
      if (!a) return s.notify(t("voice_no_approval"), "warn");
      s.answerApproval(sid, a, cmd === "approve");
      return done(cmd === "approve" ? "voice_cmd_approve" : "voice_cmd_deny");
    }
    if (cmd === "new") { s.newChat(); return done("voice_cmd_new"); }
    if (cmd === "clear") return setText("");
    if (cmd === "read") {
      const m = [...(s.messages || [])].reverse().find((x) => x.role === "assistant" && x.content);
      if (m) import("../lib/speech").then((sp) => sp.speak(m.id, m.content, sp.speechOpts(s.prefs)));
      return;
    }
    if (cmd === "quiet") return import("../lib/speech").then((sp) => sp.stopSpeech());
    if (cmd === "off") vc.current?.disable();
  };
  useEffect(() => () => vc.current?.dispose(), []);
  const toggleVoice = async () => {
    if (voice !== "off") return vc.current?.disable();
    const { createVoiceControl } = await import("../lib/voiceControl");
    vc.current?.dispose();
    vc.current = createVoiceControl({ lang: lang || "tr", onResult: (r) => onVoice.current(r),
      onState: (x) => { setVoice(x === "denied" ? "off" : x); if (x === "denied") st.notify(t("mic_denied"), "error"); } });
    if (!vc.current) return st.notify(t("mic_unsupported"), "error");
    vc.current.enable();
    st.notify(t("voice_on_hint"), "info");
  };

  return (
    <div className="mx-auto w-full max-w-[60rem] px-2.5 pb-[max(10px,env(safe-area-inset-bottom))] sm:px-4 sm:pb-5">
      <div className="relative rounded-[26px] border border-line bg-elev shadow-[0_2px_12px_rgb(0_0_0/0.06)] transition focus-within:shadow-[0_4px_20px_rgb(0_0_0/0.09)]">
        {attachments.length > 0 && (
          <div className="flex gap-2 overflow-x-auto px-3 pt-3">
            {attachments.map((a, i) => (
              <FileChip key={i} file={a} onEdit={a.kind === "image" && a.b64 ? () => setEditing(i) : undefined}
                onRemove={() => useStore.setState((s) => ({ attachments: s.attachments.filter((_, j) => j !== i) }))} />
            ))}
          </div>
        )}

        <QuoteChips />

        {mention && !picker && (
          <CatalogPicker trigger={mention.trigger} query={mention.query} typed sel={sel}
            onSel={(i, items) => { pickItems.current = items; setSel(i); }} onPick={(name) => insert(name)} />
        )}
        {picker && (
          <div ref={pickerRef}>
            <CatalogPicker trigger={picker} onPick={(name) => insert(name, picker)} onClose={() => setPicker(null)} />
          </div>
        )}

        {menu && (
          <div ref={menuRef} className="fade-in absolute bottom-full left-0 right-0 z-40 mb-2 max-h-[min(520px,62vh)] overflow-y-auto rounded-2xl border border-line bg-elev p-1.5 shadow-xl">
            <div className="px-2.5 pb-0.5 pt-1 text-[11px] font-semibold uppercase tracking-wider text-subtle">{t("add")}</div>
            <MenuItem icon={Paperclip} label={t("files_and_folders")} desc={t("files_desc")} onClick={() => { fileInput.current.click(); setMenu(false); }} />
            <MenuItem icon={FolderUp} label={t("folder")} onClick={() => { folderInput.current.click(); setMenu(false); }} />
            <MenuItem icon={Sparkles} label={t("skills")} desc={t("skills_pick_desc")} shortcut="/" onClick={() => { setMenu(false); setPicker("/"); }} />
            <MenuItem icon={Bot} label={t("agents")} desc={t("agents_pick_desc")} shortcut="@" onClick={() => { setMenu(false); setPicker("@"); }} />
            <MenuItem icon={Chrome} label={t("add_chrome")} desc={t("add_chrome_desc")} onClick={() => prefix("@tester ")} />
            <MenuItem icon={FolderGit2} label={t("work_in_project")} onClick={() => { useStore.setState({ dialog: { type: "project" } }); setMenu(false); }} />
            <MenuItem icon={Target} label={t("goal")} desc={t("goal_desc")} onClick={() => { setGoalMode(!goalMode); setMenu(false); ta.current?.focus(); }} right={goalMode && <Check size={14} className="mt-0.5 text-accent" />} />
            <MenuItem icon={ListTodo} label={t("plan_mode")} desc={t("plan_mode_desc")} onClick={() => { setPlanMode(!planMode); setMenu(false); ta.current?.focus(); }} right={planMode && <Check size={14} className="mt-0.5 text-accent" />} />
            <MenuItem icon={PenTool} label={t("drawing")} desc={t("drawing_desc")} onClick={() => { setDrawing(true); setMenu(false); }} />
            <div className="min-[420px]:hidden"><MenuItem icon={AudioLines} label={t(voice === "on" ? "voice_mode_off" : "voice_mode_on")} onClick={() => { setMenu(false); toggleVoice(); }} /></div>
            <MenuItem icon={Camera} label={t("web_shot")} desc={t("web_shot_desc")} onClick={() => prefix(t("web_shot_prefix"))} />
            <MenuSep />
            <div className="px-2.5 pb-0.5 pt-1 text-[11px] font-semibold uppercase tracking-wider text-subtle">{t("plugins")}</div>
            <MenuItem icon={FileText} label={t("documents")} desc={t("documents_desc")} onClick={() => prefix("/docs Word: ")} />
            <MenuItem icon={FileType2} label={t("pdf")} desc={t("pdf_desc")} onClick={() => prefix("/docs PDF: ")} />
            <MenuItem icon={FileSpreadsheet} label={t("spreadsheets")} desc={t("spreadsheets_desc")} onClick={() => prefix("/docs Excel: ")} />
            <MenuItem icon={Presentation} label={t("presentations")} desc={t("presentations_desc")} onClick={() => prefix("/docs PowerPoint: ")} />
          </div>
        )}

        <RichInput ref={ta} names={names} placeholder={t("placeholder")} onKeyDown={onKeyDown} onSubmit={() => submit()}
          onChange={(md, b) => { setTextState(md); setBefore(b); }}
          onPaste={(e) => { const f = [...e.clipboardData.files]; if (f.length) { e.preventDefault(); addFiles(f); } }} />

        <div className="flex items-center gap-0.5 px-2 pb-2">
          <div className="relative">
            <button ref={plusRef} onClick={() => setMenu(!menu)} className={`grid h-8 w-8 place-items-center rounded-full hover:bg-hover ${menu ? "bg-hover text-fg" : "text-muted"}`} title={t("add")}><Plus size={18} className={`transition ${menu ? "rotate-45" : ""}`} /></button>
          </div>
          <input ref={fileInput} type="file" multiple hidden onChange={(e) => { addFiles([...e.target.files]); e.target.value = ""; }} />
          <input ref={folderInput} type="file" multiple hidden webkitdirectory="" directory="" onChange={(e) => { addFolder([...e.target.files]); e.target.value = ""; }} />
          {drawing && <DrawingDialog onClose={() => setDrawing(false)} onSend={(f) => addFiles([f])} />}
          {editing != null && attachments[editing] && (
            <DrawingDialog image={attachments[editing]} onClose={() => setEditing(null)}
              onSend={(f) => st.addAttachments([f], editing)} />
          )}
          <PermissionMenu />
          {planMode && <button onClick={() => setPlanMode(false)} className="flex items-center gap-1 rounded-full bg-accent-soft px-2.5 py-0.5 text-xs font-medium text-accent"><ListTodo size={12} />{t("plan_mode")} ✕</button>}
          {goalMode && <button onClick={() => setGoalMode(false)} className="flex items-center gap-1 rounded-full bg-violet-500/12 px-2.5 py-0.5 text-xs font-medium text-violet-600 dark:text-violet-300"><Target size={12} />{t("goal")} ✕</button>}
          <div className="flex-1" />
          <ModelPicker />
          <EffortMenu />
          <ThinkToggle />
          <ContextPanel />
          <button onClick={toggleVoice} title={t(voice === "on" ? "voice_mode_off" : "voice_mode_on")}
            className={`h-8 w-8 shrink-0 place-items-center rounded-full hover:bg-hover ${voice === "on" ? "grid bg-accent-soft text-accent" : "hidden text-muted min-[420px]:grid"}`}>
            <AudioLines size={17} className={voice === "on" ? "animate-pulse" : ""} /></button>
          <button onClick={mic} title={t("dictate")} className={`grid h-8 w-8 shrink-0 place-items-center rounded-full hover:bg-hover ${listening ? "text-danger" : "text-muted"}`}><Mic size={17} /></button>
          {running ? (
            <>
              {text.trim() && <button onClick={() => submit()} title={t("steer_send")} className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-accent text-accent-fg"><ArrowUp size={17} /></button>}
              <button onClick={st.cancelRun} title={t("stop")} className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-fg text-bg"><Square size={11} fill="currentColor" /></button>
            </>
          ) : (
            <button onClick={() => submit()} disabled={!text.trim()} title={t("send")} className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-accent text-accent-fg transition disabled:opacity-35"><ArrowUp size={17} /></button>
          )}
        </div>
      </div>
    </div>
  );
}
