import { useEffect, useMemo, useState } from "react";
import {
  AlertCircle, AlertTriangle, Bot, Check, CheckCircle2, ChevronDown, Cloud, Cpu, Eye, EyeOff, FileText, Gauge, Globe,
  Info, KeyRound, Languages, Loader2, Monitor, Moon, Palette, Plus, RefreshCw, Save, Search, Server, ShieldCheck, Sun,
  Trash2, X, Zap,
} from "lucide-react";
import { useStore, useT } from "../lib/store";
import { api } from "../lib/api";
import { formatTokens } from "../lib/fileTypes";
import { errorText } from "../lib/errors";
import { Button, Modal, Toggle, inputCls } from "./ui";
import Select from "./Select";
import Markdown from "./Markdown";
import { CapBadges, capsHint } from "./Caps";

const TABS = [
  { id: "general", icon: Palette, key: "set_general" },
  { id: "models", icon: Bot, key: "set_models" },
  { id: "providers", icon: Server, key: "providers" },
  { id: "context", icon: Gauge, key: "context" },
  { id: "web", icon: Globe, key: "set_web" },
  { id: "security", icon: ShieldCheck, key: "set_security" },
  { id: "languages", icon: Languages, key: "set_languages" },
];

// ---------------------------------------------------------------- building blocks
const Card = ({ title, desc, children, action }) => (
  <section className="rounded-2xl border border-line bg-elev">
    {(title || action) && (
      <div className="flex items-start justify-between gap-3 border-b border-line px-5 py-3.5">
        <div className="min-w-0"><h3 className="text-[14px] font-semibold">{title}</h3>{desc && <p className="mt-0.5 text-xs text-muted">{desc}</p>}</div>
        {action}
      </div>
    )}
    <div className="divide-y divide-line">{children}</div>
  </section>
);

const Row = ({ label, desc, children, stack }) => (
  <div className={`flex gap-3 px-5 py-3.5 ${stack ? "flex-col" : "flex-col sm:flex-row sm:items-center sm:justify-between"}`}>
    <div className="min-w-0 sm:max-w-[48%]"><div className="text-[13px] font-medium">{label}</div>{desc && <div className="mt-0.5 text-xs leading-snug text-muted">{desc}</div>}</div>
    <div className={stack ? "" : "min-w-0 shrink-0 sm:w-[320px]"}>{children}</div>
  </div>
);

function Segmented({ value, options, onChange }) {
  return (
    <div className="inline-flex flex-wrap rounded-xl bg-hover p-1">
      {options.map((o) => (
        <button key={o.id} onClick={() => onChange(o.id)}
          className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-[13px] transition ${value === o.id ? "bg-elev font-medium shadow-sm" : "text-muted hover:text-fg"}`}>
          {o.icon && <o.icon size={14} />}{o.label}
        </button>
      ))}
    </div>
  );
}

function SliderRow({ label, desc, value, min, max, step = 1, unit = "", onCommit, format }) {
  const [v, setV] = useState(value);
  useEffect(() => setV(value), [value]);
  return (
    <Row label={label} desc={desc}>
      <div className="flex items-center gap-3">
        <input type="range" className="slider flex-1" min={min} max={max} step={step} value={v}
          onChange={(e) => setV(+e.target.value)} onMouseUp={() => onCommit(v)} onTouchEnd={() => onCommit(v)} onKeyUp={() => onCommit(v)} />
        <span className="w-16 text-right font-mono text-[13px]">{format ? format(v) : v}{unit}</span>
      </div>
    </Row>
  );
}

// All models of all usable providers as grouped Select options.
// vision=true: vision-capable models are listed first and the others are marked "No vision".
function useModelOptions(vision = false) {
  const models = useStore((s) => s.models);
  const t = useT();
  return useMemo(() => Object.entries(models).sort(([, a], [, b]) => b.local - a.local).flatMap(([pid, p]) => {
    const list = p.models.map((m) => ({
      value: `${pid}:${m.id}`, label: m.id, group: `${p.name} · ${p.local ? t("local") : t("cloud")}`,
      badge: m.context ? formatTokens(m.context) : undefined,
      hint: (vision && m.vision === false ? `⚠ ${t("cap_no_vision")} · ` : "") + (capsHint(t, m) || ""),
      rank: vision ? (m.vision ? 0 : m.vision == null ? 1 : 2) : 0,
    }));
    return vision ? list.sort((a, b) => a.rank - b.rank) : list;
  }), [models, vision]);
}

function ModelSelect({ value, onChange, allowEmpty, vision }) {
  const t = useT();
  const options = useModelOptions(vision);
  const opts = allowEmpty ? [{ value: "", label: `— ${t("none")} —` }, ...options] : options;
  return <Select value={value || ""} onChange={onChange} options={opts} searchable placeholder={t("select_model")} />;
}

// ---------------------------------------------------------------- general
function General() {
  const t = useT();
  const theme = useStore((s) => s.prefs.theme);
  const lang = useStore((s) => s.prefs.lang);
  const [langs, setLangs] = useState([]);
  useEffect(() => { api.get("/api/languages").then(setLangs); }, []);
  return (
    <Card title={t("appearance")}>
      <Row label={t("theme")} desc={t("theme_desc")}>
        <Segmented value={theme} onChange={(v) => { useStore.getState().setPref("theme", v); useStore.getState().notify(t("saved"), "ok"); }}
          options={[{ id: "light", label: t("light"), icon: Sun }, { id: "dark", label: t("dark"), icon: Moon }, { id: "system", label: t("system"), icon: Monitor }]} />
      </Row>
      <Row label={t("language")} desc={t("language_desc")}>
        <Select value={lang} onChange={(v) => useStore.getState().loadLanguage(v).then(() => useStore.getState().notify(useStore.getState().t("saved"), "ok"))}
          options={langs.map((l) => ({ value: l.code, label: l.name, badge: l.code }))} />
      </Row>
    </Card>
  );
}

// ---------------------------------------------------------------- models
function ModelSummary({ id }) {
  const t = useT();
  const models = useStore((s) => s.models);
  const ctx = useStore((s) => s.context);
  const [pid, ...rest] = (id || "").split(":");
  const p = models[pid];
  const m = p?.models.find((x) => x.id === rest.join(":"));
  if (!id) return null;
  return (
    <div className="flex flex-wrap items-center gap-2 text-xs">
      <span className="flex items-center gap-1 rounded-lg bg-hover px-2 py-1">{p?.local ? <Cpu size={12} /> : <Cloud size={12} />}{p?.name || pid}</span>
      {(m?.context || (ctx?.model === id && ctx.max)) && <span className="rounded-lg bg-hover px-2 py-1">{t("context")}: {formatTokens(m?.context || ctx.max)}</span>}
      {m && <CapBadges m={m} />}
      {!m && !p?.loading && <span className="flex items-center gap-1 rounded-lg bg-warn/10 px-2 py-1 text-warn"><AlertTriangle size={12} />{t("model_unavailable")}</span>}
    </div>
  );
}

function ProviderStatusList() {
  const t = useT();
  const models = useStore((s) => s.models);
  const entries = Object.entries(models);
  return (
    <Card title={t("available_models")} desc={t("available_models_desc")}
      action={<Button className="!px-2.5 !py-1" onClick={() => useStore.getState().loadModels()}><RefreshCw size={13} /> {t("refresh")}</Button>}>
      {entries.length === 0 && <div className="px-5 py-4 text-xs text-subtle">{t("no_usable_providers")}</div>}
      {entries.map(([pid, p]) => {
        const e = p.error ? errorText(t, p.code, p.error) : null;
        return (
          <div key={pid} className="flex items-center gap-3 px-5 py-2.5 text-[13px]">
            {p.local ? <Cpu size={14} className="shrink-0 text-subtle" /> : <Cloud size={14} className="shrink-0 text-subtle" />}
            <span className="min-w-0 flex-1 truncate font-medium">{p.name}</span>
            {p.loading ? <Loader2 size={14} className="animate-spin text-accent" />
              : e ? <span className="truncate text-xs text-danger" title={p.error}>{e.title}</span>
                : <span className="rounded-md bg-hover px-2 py-0.5 text-xs text-muted">{t("n_models", { n: p.models.length })}</span>}
          </div>
        );
      })}
    </Card>
  );
}

function Models() {
  const t = useT();
  const s = useStore((x) => x.settings);
  const active = useStore((x) => x.prefs.model || x.settings?.active_model || "");
  const options = useModelOptions();
  const st = useStore.getState();
  const visionOk = !s.vision_model || options.some((o) => o.value === s.vision_model);
  const visionModel = s.vision_model ? st.modelCaps(s.vision_model) : null;
  return (
    <div className="space-y-4">
      <Card title={t("active_model")} desc={t("active_model_desc")}>
        <div className="space-y-3 px-5 py-4">
          <ModelSelect value={active} onChange={(v) => { st.selectModel(v); st.updateSettings({ active_model: v }); }} />
          <ModelSummary id={active} />
        </div>
      </Card>
      <Card title={t("vision_model")} desc={t("vision_model_desc")}>
        <div className="px-5 py-4">
          <ModelSelect value={s.vision_model} allowEmpty vision onChange={(v) => st.updateSettings({ vision_model: v })} />
          {s.vision_model && visionOk && <div className="mt-3"><ModelSummary id={s.vision_model} /></div>}
          {visionModel?.vision === false && <div className="mt-2 flex items-center gap-1.5 text-xs text-warn"><AlertTriangle size={13} />{t("vision_model_no_vision")}</div>}
          {!visionOk && <div className="mt-2 flex items-center gap-1.5 text-xs text-warn"><AlertTriangle size={13} />{t("vision_unavailable", { m: s.vision_model })}</div>}
        </div>
      </Card>
      <Card title={t("cloud_fallback")} desc={t("cloud_fallback_desc")}>
        <Row label={t("enabled")}><Toggle checked={!!s.cloud_fallback} onChange={(v) => st.updateSettings({ cloud_fallback: v })} /></Row>
        <Row label={t("fallback_model")}><ModelSelect value={s.fallback_model} allowEmpty onChange={(v) => st.updateSettings({ fallback_model: v })} /></Row>
      </Card>
      <ProviderStatusList />
    </div>
  );
}

// ---------------------------------------------------------------- providers
function TermsModal({ id, onClose, onAccepted }) {
  const t = useT();
  const [terms, setTerms] = useState(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    api.get(`/api/providers/${id}/terms`).then(setTerms).catch((e) => { useStore.getState().notify(t("terms_load_failed"), "error", e.message); onClose(); });
  }, []);
  const accept = async () => {
    setBusy(true);
    try {
      await api.post(`/api/providers/${id}/terms/accept`, { version: terms.current_version });
      useStore.getState().notify(t("terms_accepted"), "ok");
      onAccepted(); onClose();
    } catch (e) { useStore.getState().notify(t("terms_accept_failed"), "error", e.message); setBusy(false); }
  };
  return (
    <Modal title={t("terms_title")} onClose={onClose} width="max-w-3xl"
      footer={<><Button variant="ghost" onClick={onClose}>{t("cancel")}</Button>
        <Button variant="primary" disabled={!terms || busy} onClick={accept}>{busy && <Loader2 size={14} className="animate-spin" />}{t("terms_accept_btn")}</Button></>}>
      {!terms ? <div className="grid h-40 place-items-center"><Loader2 className="animate-spin text-subtle" /></div> : (
        <>
          <div className="mb-3 rounded-xl bg-hover px-3 py-2 text-xs text-muted">{t("terms_version", { v: terms.current_version })} · {terms.doc_path}</div>
          <div className="max-h-[55vh] overflow-y-auto rounded-2xl border border-line p-4 text-[13px]"><Markdown text={terms.content || ""} /></div>
        </>
      )}
    </Modal>
  );
}

function ProviderModels({ id }) {
  const t = useT();
  const p = useStore((s) => s.models[id]);
  const [q, setQ] = useState("");
  if (!p) return <div className="text-xs text-subtle">{t("provider_not_usable")}</div>;
  if (p.loading) return <div className="flex items-center gap-2 text-xs text-muted"><Loader2 size={13} className="animate-spin" /> {t("loading_models")}</div>;
  if (p.error) { const e = errorText(t, p.code, p.error); return <div className="text-xs text-danger">{e.title}<div className="mt-0.5 break-words font-mono text-[11px] opacity-80">{e.detail}</div></div>; }
  const list = p.models.filter((m) => !q || m.id.toLowerCase().includes(q.toLowerCase()));
  return (
    <div>
      <div className="mb-2 flex items-center gap-2">
        <span className="text-xs font-medium">{t("n_models", { n: p.models.length })}</span>
        {p.models.length > 6 && (
          <div className="relative ml-auto w-48">
            <Search size={12} className="absolute left-2 top-1/2 -translate-y-1/2 text-subtle" />
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("search")} className="w-full rounded-lg border border-line bg-bg py-1 pl-7 pr-2 text-xs outline-none focus:border-accent" />
          </div>
        )}
      </div>
      <div className="flex max-h-40 flex-wrap gap-1.5 overflow-y-auto">
        {list.slice(0, 300).map((m) => (
          <button key={m.id} title={t("use_this_model")} onClick={() => { useStore.getState().selectModel(`${id}:${m.id}`); useStore.getState().updateSettings({ active_model: `${id}:${m.id}` }); }}
            className="flex items-center gap-1 rounded-lg border border-line bg-bg px-2 py-0.5 font-mono text-[11px] hover:border-accent hover:text-accent">
            {m.id}{m.context && <span className="text-subtle">· {formatTokens(m.context)}</span>}
          </button>
        ))}
      </div>
    </div>
  );
}

function ProviderCard({ id, cfg, hasKey }) {
  const t = useT();
  const st = useStore.getState();
  const info = useStore((s) => s.models[id]);
  const [open, setOpen] = useState(false);
  const [url, setUrl] = useState(cfg.base_url || "");
  const [key, setKey] = useState("");
  const [show, setShow] = useState(false);
  const [test, setTest] = useState(null);
  const [busy, setBusy] = useState(false);
  const [terms, setTerms] = useState(false);
  useEffect(() => setUrl(cfg.base_url || ""), [cfg.base_url]);
  const urlDirty = url !== (cfg.base_url || "");
  const save = (p) => st.updateSettings({ providers: { [id]: p } }).then(() => st.refreshProvider(id));
  const saveUrl = () => urlDirty && save({ base_url: url });
  const saveKey = async () => {
    if (!key) return;
    await st.setSecret(`${id}_api_key`, key); // also re-queries this provider's models at once
    setKey("");
  };
  const runTest = async () => {
    setBusy(true); setTest(null);
    try {
      if (key) await saveKey();
      if (urlDirty) await save({ base_url: url });
      setTest(await api.post(`/api/providers/${id}/test`));
    } catch (e) { setTest({ ok: false, code: "request", error: e.message }); }
    setBusy(false);
  };
  const remove = async () => {
    if (!(await st.confirm({ title: t("delete_provider"), message: t("confirm_delete_provider"), confirmLabel: t("delete"), danger: true }))) return;
    await st.persist(() => api.del(`/api/providers/${id}`));
    await st.refreshSettings(); st.refreshProvider(id);
    st.notify(t("deleted", { name: cfg.name || id }), "ok");
  };
  const ready = cfg.local || hasKey;
  const err = test && !test.ok ? errorText(t, test.code, test.error) : null;
  const needsTerms = test?.terms && !test.terms.accepted;
  const live = info && !info.loading && !info.error;
  const dot = test ? (test.ok && !needsTerms ? "bg-ok" : needsTerms ? "bg-warn" : "bg-danger")
    : info?.error ? "bg-danger" : live ? "bg-ok" : ready && cfg.enabled ? "bg-warn" : "bg-active";
  return (
    <div className="px-4 py-3 sm:px-5">
      <div className="flex items-center gap-3">
        <span className={`h-2 w-2 shrink-0 rounded-full ${dot}`} />
        <button onClick={() => setOpen(!open)} className="flex min-w-0 flex-1 items-center gap-2 text-left">
          <span className="truncate text-[13px] font-semibold">{cfg.name || id}</span>
          <span className="hidden rounded-md bg-hover px-1.5 py-px font-mono text-[10px] text-muted sm:inline">{cfg.kind}</span>
          {!cfg.local && hasKey && <KeyRound size={12} className="shrink-0 text-ok" />}
          {info?.loading && <Loader2 size={12} className="shrink-0 animate-spin text-accent" />}
          {live && <span className="hidden shrink-0 rounded-md bg-ok/10 px-1.5 py-px text-[10px] text-ok sm:inline">{t("n_models", { n: info.models.length })}</span>}
          <ChevronDown size={14} className={`ml-auto shrink-0 text-subtle transition ${open ? "rotate-180" : ""}`} />
        </button>
        <Button onClick={runTest} disabled={busy} className="!px-2.5 !py-1">{busy ? <Loader2 size={13} className="animate-spin" /> : <Zap size={13} />}<span className="hidden sm:inline">{t("test")}</span></Button>
        <Toggle checked={!!cfg.enabled} onChange={(v) => save({ enabled: v })} />
      </div>
      {test && (
        <div className={`fade-in mt-2 rounded-xl px-3 py-2 text-xs ${test.ok && !needsTerms ? "bg-ok/10 text-ok" : needsTerms ? "bg-warn/10 text-warn" : "bg-danger/10 text-danger"}`}>
          {needsTerms ? (
            <div className="flex flex-wrap items-center gap-2">
              <span className="flex-1">{t("terms_needed")}</span>
              <Button className="!px-2.5 !py-1" onClick={() => setTerms(true)}><FileText size={13} /> {t("terms_read_accept")}</Button>
            </div>
          ) : test.ok ? <>✓ {t("test_ok", { n: test.models, ms: test.ms })}</> : (
            <><div className="font-medium">✕ {err.title}</div><div className="mt-0.5 break-words font-mono text-[11px] opacity-80">{err.detail}</div></>
          )}
          {test.quota && <div className="mt-1 text-muted">{t("quota_left", { cr: test.quota.remaining_cr ?? "?", lvl: test.quota.level ?? "" })}</div>}
        </div>
      )}
      {terms && <TermsModal id={id} onClose={() => setTerms(false)} onAccepted={() => { runTest(); st.refreshProvider(id); }} />}
      {open && (
        <div className="fade-in mt-3 grid gap-3 pl-5">
          <label className="text-xs text-muted">{t("base_url")}
            <div className="mt-1 flex gap-2">
              <input className={`${inputCls} font-mono ${urlDirty ? "!border-warn" : ""}`} value={url} onChange={(e) => setUrl(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && saveUrl()} />
              {urlDirty && <Button variant="primary" onClick={saveUrl}><Save size={14} /> {t("save")}</Button>}
            </div>
            {urlDirty && <span className="mt-1 block text-[11px] text-warn">{t("unsaved_change")}</span>}
          </label>
          {!cfg.local && (
            <label className="text-xs text-muted">{t("api_key")}
              <div className="mt-1 flex gap-2">
                <div className="relative flex-1">
                  <input className={`${inputCls} pr-16 font-mono ${key ? "!border-warn" : ""}`} type={show ? "text" : "password"} value={key} autoComplete="off"
                    placeholder={hasKey ? "••••••••••••  " + t("key_saved") : t("api_key_ph")} onChange={(e) => setKey(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && saveKey()} />
                  <div className="absolute right-1.5 top-1/2 flex -translate-y-1/2 gap-0.5">
                    <button onClick={() => setShow(!show)} className="rounded-md p-1 text-subtle hover:bg-hover">{show ? <EyeOff size={14} /> : <Eye size={14} />}</button>
                    {hasKey && !key && <button title={t("delete")} onClick={() => st.setSecret(`${id}_api_key`, null).then(() => st.notify(t("key_removed"), "ok"))} className="rounded-md p-1 text-subtle hover:bg-hover hover:text-danger"><X size={14} /></button>}
                  </div>
                </div>
                {key && <Button variant="primary" onClick={saveKey}><Save size={14} /> {t("save")}</Button>}
              </div>
              <span className={`mt-1 block text-[11px] ${key ? "text-warn" : hasKey ? "text-ok" : "text-subtle"}`}>
                {key ? t("unsaved_change") : hasKey ? "✓ " + t("key_stored") : t("key_missing")}
              </span>
            </label>
          )}
          <div className="rounded-xl border border-line bg-panel p-3"><ProviderModels id={id} /></div>
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-muted">
            <label className="flex items-center gap-2"><Toggle checked={cfg.streaming !== false} onChange={(v) => save({ streaming: v })} /> {t("streaming")}</label>
            <span className="font-mono">id: {id}</span>
            <button onClick={remove} className="ml-auto flex items-center gap-1 text-subtle hover:text-danger"><Trash2 size={13} /> {t("delete")}</button>
          </div>
        </div>
      )}
    </div>
  );
}

const PROTOCOLS = (t) => [
  { value: "openai", label: t("proto_openai"), hint: "OpenAI, OpenRouter, Groq, LM Studio, EVREN, vLLM…" },
  { value: "ollama", label: "Ollama", hint: t("proto_ollama_hint") },
  { value: "anthropic", label: "Anthropic", hint: "Claude Messages API" },
  { value: "gemini", label: "Gemini (native)", hint: "generativelanguage.googleapis.com" },
];

function AddProvider({ onClose }) {
  const t = useT();
  const [f, setF] = useState({ id: "", name: "", kind: "openai", base_url: "", local: false, streaming: true });
  const [err, setErr] = useState("");
  const set = (k) => (e) => setF({ ...f, [k]: e?.target ? e.target.value : e });
  const save = async () => {
    try {
      const { id, ...body } = f;
      const st = useStore.getState();
      await st.persist(() => api.put(`/api/providers/${id}`, body));
      await st.refreshSettings();
      st.notify(t("provider_added", { name: body.name || id }), "ok");
      st.refreshProvider(id);
      onClose();
    } catch (e) { setErr(e.message); }
  };
  return (
    <Modal title={t("add_provider")} onClose={onClose} footer={<><Button variant="ghost" onClick={onClose}>{t("cancel")}</Button><Button variant="primary" disabled={!f.id || !f.base_url} onClick={save}>{t("save")}</Button></>}>
      <div className="grid gap-3">
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="text-xs text-muted">ID<input className={`${inputCls} mt-1 font-mono`} value={f.id} placeholder="my-provider" onChange={(e) => setF({ ...f, id: e.target.value.toLowerCase().replace(/[^a-z0-9_-]/g, "") })} /></label>
          <label className="text-xs text-muted">{t("name")}<input className={`${inputCls} mt-1`} value={f.name} onChange={set("name")} /></label>
        </div>
        <div className="text-xs text-muted">{t("protocol")}<div className="mt-1"><Select value={f.kind} onChange={set("kind")} options={PROTOCOLS(t)} /></div></div>
        <label className="text-xs text-muted">{t("base_url")}<input className={`${inputCls} mt-1 font-mono`} value={f.base_url} placeholder="https://api.example.com/v1" onChange={set("base_url")} /></label>
        <div className="flex gap-6 text-[13px]">
          <label className="flex items-center gap-2"><Toggle checked={f.local} onChange={set("local")} /> {t("local")}</label>
          <label className="flex items-center gap-2"><Toggle checked={f.streaming} onChange={set("streaming")} /> {t("streaming")}</label>
        </div>
        {err && <div className="rounded-xl bg-danger/10 px-3 py-2 text-xs text-danger">{err}</div>}
      </div>
    </Modal>
  );
}

function Providers() {
  const t = useT();
  const s = useStore((x) => x.settings);
  const [q, setQ] = useState("");
  const [filter, setFilter] = useState("all");
  const [adding, setAdding] = useState(false);
  const entries = useMemo(() => Object.entries(s.providers).filter(([id, c]) => {
    const hasKey = !!s.secrets?.[`${id}_api_key`];
    if (filter === "active" && !(c.enabled && (c.local || hasKey))) return false;
    return !q || `${id} ${c.name}`.toLowerCase().includes(q.toLowerCase());
  }), [s.providers, s.secrets, q, filter]);
  const section = (local) => entries.filter(([, c]) => !!c.local === local);
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2">
        <div className="relative min-w-[200px] flex-1">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-subtle" />
          <input className={`${inputCls} pl-9`} value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("search_providers")} />
        </div>
        <Segmented value={filter} onChange={setFilter} options={[{ id: "all", label: t("all") }, { id: "active", label: t("active_only") }]} />
        <Button variant="primary" onClick={() => setAdding(true)}><Plus size={15} /><span className="hidden sm:inline">{t("add_provider")}</span></Button>
      </div>
      {[[true, Cpu, "local_providers", "local_providers_desc"], [false, Cloud, "cloud_providers", "cloud_providers_desc"]].map(([local, Icon, title, desc]) => section(local).length > 0 && (
        <Card key={title} title={<span className="flex items-center gap-2"><Icon size={15} />{t(title)} <span className="text-xs font-normal text-subtle">{section(local).length}</span></span>} desc={t(desc)}>
          {section(local).map(([id, cfg]) => <ProviderCard key={id} id={id} cfg={cfg} hasKey={!!s.secrets?.[`${id}_api_key`]} />)}
        </Card>
      ))}
      {entries.length === 0 && <div className="py-8 text-center text-[13px] text-subtle">{t("no_results")}</div>}
      {adding && <AddProvider onClose={() => setAdding(false)} />}
    </div>
  );
}

// ---------------------------------------------------------------- context
function Context() {
  const t = useT();
  const s = useStore((x) => x.settings);
  const ctx = useStore((x) => x.context);
  const st = useStore.getState();
  const save = (patch) => st.updateSettings({ context: patch }).then(() => st.loadContext());
  return (
    <div className="space-y-4">
      <Card title={t("context_compress")} desc={t("context_compress_desc")}>
        <SliderRow label={t("compress_threshold")} desc={t("compress_threshold_desc")} value={s.context.compress_threshold}
          min={0} max={100} unit="%" onCommit={(v) => save({ compress_threshold: v })} />
        <SliderRow label={t("keep_recent")} desc={t("keep_recent_desc")} value={s.context.keep_recent ?? 6}
          min={0} max={20} onCommit={(v) => save({ keep_recent: v })} />
      </Card>
      {ctx && (
        <Card title={t("context_window")} desc={ctx.model}>
          <Row label={t("model_max")} desc={ctx.local ? t("context_local_desc") : t("context_cloud_desc")}><span className="font-mono text-[13px]">{formatTokens(ctx.max)} token</span></Row>
          {ctx.adjustable
            ? <SliderRow label={t("context_size")} desc={t("context_size_hint")} value={ctx.current} min={2048} max={ctx.max} step={1024}
              format={formatTokens} onCommit={(v) => st.setModelContext(ctx.model, v)} />
            : <Row label={t("context_size")}><span className="font-mono text-[13px]">{formatTokens(ctx.current)}</span></Row>}
        </Card>
      )}
    </div>
  );
}

// ---------------------------------------------------------------- web research
function SecretField({ name, label, desc, placeholder }) {
  const t = useT();
  const has = useStore((s) => !!s.settings?.secrets?.[name]);
  const [v, setV] = useState("");
  const st = useStore.getState();
  const save = async () => { if (!v) return; await st.setSecret(name, v); setV(""); st.notify(t("saved"), "ok"); };
  return (
    <Row label={label} desc={desc}>
      <div className="flex gap-2">
        <input type="password" autoComplete="off" value={v} onChange={(e) => setV(e.target.value)} onKeyDown={(e) => e.key === "Enter" && save()}
          placeholder={has ? "•••••••• " + t("key_saved") : placeholder} className={`${inputCls} font-mono ${v ? "!border-warn" : ""}`} />
        {v ? <Button variant="primary" onClick={save}><Save size={14} /></Button>
          : has && <Button onClick={() => st.setSecret(name, null).then(() => st.notify(t("key_removed"), "ok"))}><X size={14} /></Button>}
      </div>
    </Row>
  );
}

function Web() {
  const t = useT();
  const s = useStore((x) => x.settings);
  const [url, setUrl] = useState(s.search?.searxng_url || "");
  const [q, setQ] = useState("Audi 2026 modelleri");
  const [res, setRes] = useState(null);
  const [busy, setBusy] = useState(false);
  const st = useStore.getState();
  const dirty = url !== (s.search?.searxng_url || "");
  const test = async () => {
    setBusy(true);
    try { setRes(await api.get(`/api/web/search?q=${encodeURIComponent(q)}`)); } catch (e) { setRes({ error: e.message }); }
    setBusy(false);
  };
  return (
    <div className="space-y-4">
      <Card title={t("web_engines")} desc={t("web_engines_desc")}>
        <SecretField name="brave_api_key" label="Brave Search API" desc={t("brave_desc")} placeholder="BSA…" />
        <SecretField name="tavily_api_key" label="Tavily API" desc={t("tavily_desc")} placeholder="tvly-…" />
        <Row label="SearXNG" desc={t("searxng_desc")}>
          <div className="flex gap-2">
            <input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="http://127.0.0.1:8888" className={`${inputCls} font-mono ${dirty ? "!border-warn" : ""}`}
              onKeyDown={(e) => e.key === "Enter" && dirty && st.updateSettings({ search: { searxng_url: url } })} />
            {dirty && <Button variant="primary" onClick={() => st.updateSettings({ search: { searxng_url: url } })}><Save size={14} /></Button>}
          </div>
        </Row>
      </Card>
      <Card title={t("web_test")} desc={t("web_policy")}>
        <div className="flex gap-2 px-5 py-4">
          <input value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => e.key === "Enter" && test()} className={inputCls} />
          <Button variant="primary" onClick={test} disabled={busy}>{busy ? <Loader2 size={14} className="animate-spin" /> : <Search size={14} />} {t("test")}</Button>
        </div>
        {res && (
          <div className="px-5 pb-4 text-xs">
            {res.error ? <div className="text-danger">{res.error}</div> : (
              <>
                <div className="mb-2 text-ok">✓ {t("web_test_ok", { n: res.count, ms: res.ms, e: res.engines.join(", ") || "-" })}</div>
                {res.results.map((r) => <div key={r.url} className="truncate py-0.5"><a href={r.url} target="_blank" rel="noreferrer" className="text-accent hover:underline">{r.title || r.url}</a> <span className="text-subtle">· {r.engine}</span></div>)}
              </>
            )}
          </div>
        )}
      </Card>
    </div>
  );
}

// ---------------------------------------------------------------- security
function Security() {
  const t = useT();
  const s = useStore((x) => x.settings);
  const st = useStore.getState();
  const agent = (k) => (v) => st.updateSettings({ agent: { [k]: v } });
  return (
    <div className="space-y-4">
      <Card title={t("default_permission")} desc={t("default_permission_desc")}>
        {["ask", "auto", "full"].map((m) => (
          <button key={m} onClick={() => st.updateSettings({ permission_mode: m })} className="flex w-full items-start gap-3 px-5 py-3.5 text-left hover:bg-hover">
            <div className="flex-1"><div className="text-[13px] font-medium">{t(`perm_${m}`)}</div><div className="mt-0.5 text-xs text-muted">{t(`perm_${m}_desc`)}</div></div>
            {s.permission_mode === m && <Check size={16} className="mt-0.5 text-accent" />}
          </button>
        ))}
      </Card>
      <Card title={t("agent_limits")} desc={t("agent_limits_desc")}>
        <SliderRow label={t("max_iterations")} value={s.agent.max_iterations} min={1} max={100} onCommit={agent("max_iterations")} />
        <SliderRow label={t("max_debug")} value={s.agent.max_debug_attempts} min={0} max={20} onCommit={agent("max_debug_attempts")} />
        <SliderRow label={t("command_timeout")} value={s.agent.command_timeout} min={10} max={3600} step={10} unit="s" onCommit={agent("command_timeout")} />
      </Card>
      <p className="px-1 text-xs leading-relaxed text-muted">{t("security_note")}</p>
    </div>
  );
}

// ---------------------------------------------------------------- languages
function LanguagesTab() {
  const t = useT();
  const [langs, setLangs] = useState([]);
  const [f, setF] = useState({ code: "", name: "" });
  const [busy, setBusy] = useState(false);
  const load = () => api.get("/api/languages").then(setLangs);
  useEffect(() => { load(); }, []);
  const st = useStore.getState();
  const add = async (e) => {
    e.preventDefault();
    setBusy(true);
    try { await api.post("/api/languages", f); await load(); st.notify(t("lang_added", { name: f.name }), "ok"); setF({ code: "", name: "" }); }
    catch (x) { st.notify(t("translate_failed"), "error", x.message); }
    setBusy(false);
  };
  const del = async (l) => {
    if (!(await st.confirm({ title: t("delete"), message: t("confirm_delete_item", { name: l.name }), confirmLabel: t("delete"), danger: true }))) return;
    await api.del(`/api/languages/${l.code}`); load(); st.notify(t("deleted", { name: l.name }), "ok");
  };
  return (
    <div className="space-y-4">
      <Card title={t("installed_languages")}>
        {langs.map((l) => (
          <div key={l.code} className="flex items-center gap-3 px-5 py-3">
            <Globe size={15} className="text-subtle" />
            <span className="flex-1 text-[13px] font-medium">{l.name}</span>
            <span className="font-mono text-xs text-subtle">{l.code}</span>
            {!["tr", "en"].includes(l.code) && <button onClick={() => del(l)} className="rounded-md p-1 text-subtle hover:text-danger"><Trash2 size={14} /></button>}
          </div>
        ))}
      </Card>
      <Card title={t("add_language")} desc={t("add_language_desc")}>
        <form onSubmit={add} className="grid gap-3 p-5 sm:grid-cols-[140px_1fr_auto]">
          <input lang="en" className={`${inputCls} font-mono`} placeholder="de, fr, ar…" value={f.code} required pattern="[a-z]{2,3}(-[A-Za-z]{2,4})?"
            onChange={(e) => setF({ ...f, code: e.target.value.replace(/[^a-zA-Z-]/g, "").slice(0, 8) })} />
          <input lang="en" className={inputCls} placeholder={t("lang_name_ph")} value={f.name} required
            onChange={(e) => setF({ ...f, name: e.target.value.replace(/[^A-Za-z ()-]/g, "") })} />
          <Button variant="primary" disabled={busy}>{busy ? <Loader2 size={14} className="animate-spin" /> : <Languages size={14} />} {t("translate_add")}</Button>
        </form>
      </Card>
    </div>
  );
}

// ---------------------------------------------------------------- shell
function SaveIndicator() {
  const t = useT();
  const { state, at, error } = useStore((s) => s.saveState);
  const time = at ? new Date(at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }) : null;
  const cls = "flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium";
  if (state === "saving") return <span className={`${cls} bg-accent-soft text-accent`}><Loader2 size={13} className="animate-spin" /> {t("saving")}</span>;
  if (state === "error") return <span title={error} className={`${cls} bg-danger/10 text-danger`}><AlertCircle size={13} /> {t("save_failed")}</span>;
  if (state === "saved") return <span className={`${cls} bg-ok/10 text-ok`}><CheckCircle2 size={13} /> {t("all_saved")} · {time}</span>;
  return <span className={`${cls} bg-hover text-muted`}><Save size={13} /> {t("autosave_hint")}</span>;
}

const PANES = { general: General, models: Models, providers: Providers, context: Context, web: Web, security: Security, languages: LanguagesTab };

export default function SettingsView() {
  const t = useT();
  const settings = useStore((s) => s.settings);
  const tab = useStore((s) => (PANES[s.settingsTab] ? s.settingsTab : "general"));
  useEffect(() => { useStore.getState().loadContext(); }, []);
  if (!settings) return null;
  const Pane = PANES[tab];
  const cur = TABS.find((x) => x.id === tab);
  return (
    <div className="flex min-h-0 flex-1 flex-col md:flex-row">
      <nav className="flex shrink-0 gap-1 overflow-x-auto border-b border-line px-3 py-2 md:w-56 md:flex-col md:border-b-0 md:border-r md:px-3 md:py-5">
        <h1 className="hidden px-3 pb-3 text-lg font-semibold md:block">{t("settings")}</h1>
        {TABS.map((x) => (
          <button key={x.id} onClick={() => useStore.setState({ settingsTab: x.id })}
            className={`flex shrink-0 items-center gap-2.5 rounded-xl px-3 py-2 text-[13px] transition ${tab === x.id ? "bg-active font-medium" : "text-muted hover:bg-hover hover:text-fg"}`}>
            <x.icon size={16} /> {t(x.key)}
          </button>
        ))}
        <button onClick={() => useStore.getState().setView("about")}
          className="flex shrink-0 items-center gap-2.5 rounded-xl px-3 py-2 text-[13px] text-muted hover:bg-hover hover:text-fg md:mt-auto">
          <Info size={16} /> {t("set_about")}
        </button>
      </nav>
      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto max-w-3xl px-4 py-5 sm:px-6 sm:py-8">
          <div className="sticky top-0 z-10 -mx-1 mb-5 flex flex-wrap items-center justify-between gap-2 bg-bg/90 px-1 py-2 backdrop-blur">
            <h2 className="text-xl font-semibold tracking-tight">{t(cur.key)}</h2>
            <SaveIndicator />
          </div>
          <Pane />
        </div>
      </div>
    </div>
  );
}
