import { useEffect, useMemo, useState } from "react";
import {
  AlertCircle, AlertTriangle, Bot, Check, CheckCircle2, ChevronDown, Cloud, Cpu, Eye, EyeOff, FileText, Gauge, Globe,
  Info, KeyRound, Languages, Loader2, Monitor, Moon, Palette, Plus, RefreshCw, Save, Search, Server, ShieldCheck, Sun,
  Trash2, X, Zap, Network, Plug, Volume2, Pencil,
} from "lucide-react";
import { edgeVoices, speak, speechOpts, speechSupported, voicesFor } from "../lib/speech";
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
  { id: "multi", icon: Network, key: "set_multi" },
  { id: "providers", icon: Server, key: "providers" },
  { id: "context", icon: Gauge, key: "context" },
  { id: "web", icon: Globe, key: "set_web" },
  { id: "mcp", icon: Plug, key: "set_mcp" },
  { id: "security", icon: ShieldCheck, key: "set_security" },
  { id: "languages", icon: Languages, key: "set_languages" },
];

// ---------------------------------------------------------------- building blocks
const Card = ({ title, desc, children, action }) => (
  <section className="rounded-2xl border border-line bg-elev">
    {(title || action) && (
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-line px-4 py-3.5 @md:px-5">
        <div className="min-w-0"><h3 className="text-[14px] font-semibold">{title}</h3>{desc && <p className="mt-0.5 text-xs text-muted">{desc}</p>}</div>
        {action}
      </div>
    )}
    <div className="divide-y divide-line">{children}</div>
  </section>
);

// tight: a small control (switch) on the right, the text takes the rest of the row at every width.
// Layout follows the width of the settings column (container query), not the window: a narrow app window
// with the sidebar open stacks label and control instead of squeezing the text into a thin column.
const Row = ({ label, desc, children, stack, tight }) => (
  <div className={`flex gap-3 px-4 py-3.5 @md:px-5 ${stack ? "flex-col" : tight ? "items-center justify-between" : "flex-col @2xl:flex-row @2xl:items-center @2xl:justify-between"}`}>
    <div className={`min-w-0 ${tight ? "flex-1" : stack ? "" : "@2xl:max-w-[48%]"}`}><div className="text-[13px] font-medium">{label}</div>{desc && <div className="mt-0.5 text-xs leading-snug text-muted">{desc}</div>}</div>
    <div className={stack ? "min-w-0" : tight ? "shrink-0" : "min-w-0 @2xl:w-[320px] @2xl:shrink-0"}>{children}</div>
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
function useModelOptions(vision = false, cloudOnly = false) {
  const models = useStore((s) => s.models);
  const t = useT();
  return useMemo(() => Object.entries(models).filter(([, p]) => !cloudOnly || !p.local).sort(([, a], [, b]) => b.local - a.local).flatMap(([pid, p]) => {
    const list = p.models.map((m) => ({
      value: `${pid}:${m.id}`, label: m.id, group: `${p.name} · ${p.local ? t("local") : t("cloud")}`,
      badge: m.context ? formatTokens(m.context) : undefined,
      hint: (vision && m.vision === false ? `⚠ ${t("cap_no_vision")} · ` : "") + (capsHint(t, m) || ""),
      rank: vision ? (m.vision ? 0 : m.vision == null ? 1 : 2) : 0,
    }));
    return vision ? list.sort((a, b) => a.rank - b.rank) : list;
  }), [models, vision, cloudOnly]);
}

function ModelSelect({ value, onChange, allowEmpty, vision, cloudOnly, emptyLabel }) {
  const t = useT();
  const options = useModelOptions(vision, cloudOnly);
  const opts = allowEmpty ? [{ value: "", label: `— ${emptyLabel || t("none")} —` }, ...options] : options;
  return <Select value={value || ""} onChange={onChange} options={opts} searchable placeholder={t("select_model")} />;
}

// ---------------------------------------------------------------- general
// Global rules: added to every chat (project rules live in each project's AIIQ.md).
function GlobalRules() {
  const t = useT();
  const saved = useStore((s) => s.settings?.rules || "");
  const [text, setText] = useState(saved);
  useEffect(() => setText(saved), [saved]);
  return (
    <Card title={t("global_rules")} desc={t("global_rules_desc")}>
      <div className="px-5 py-4">
        <textarea value={text} onChange={(e) => setText(e.target.value)} onBlur={() => text !== saved && useStore.getState().updateSettings({ rules: text.slice(0, 6000) })}
          spellCheck={false} placeholder={t("rules_placeholder")}
          className="h-40 w-full resize-y rounded-2xl border border-line bg-bg p-3 font-mono text-[13px] leading-relaxed outline-none focus:border-accent" />
        <div className="mt-1 flex justify-between gap-3 text-[11px] text-subtle"><span>{t("global_rules_hint")}</span><span className="tabular-nums">{text.length} / 6000</span></div>
      </div>
    </Card>
  );
}

// Spoken replies: the browser's own voices (offline); the setting is kept per browser.
function VoiceCard() {
  const t = useT();
  const prefs = useStore((s) => s.prefs);
  const [voices, setVoices] = useState([]); // browser (offline) voices
  const [neural, setNeural] = useState(null); // online neural voices; null while loading
  const [gender, setGender] = useState("all");
  const lang = prefs.lang || "tr";
  useEffect(() => {
    if (!window.speechSynthesis) return;
    const load = () => setVoices(voicesFor(lang));
    load();
    window.speechSynthesis.addEventListener?.("voiceschanged", load);
    return () => window.speechSynthesis.removeEventListener?.("voiceschanged", load);
  }, [lang]);
  useEffect(() => { setNeural(null); edgeVoices(lang).then(setNeural); }, [lang]);
  const st = useStore.getState();
  if (!speechSupported()) return <Card title={t("voice_title")} desc={t("voice_unsupported")} />;
  const many = new Set((neural || []).map((v) => v.locale)).size > 1;
  const options = [
    { value: "", label: t("voice_default"), hint: t("voice_default_hint") },
    ...(neural || []).filter((v) => gender === "all" || v.gender === gender).map((v) => ({
      value: `edge:${v.id}`, label: many ? `${v.name} · ${v.locale}` : v.name, group: t("voice_group_neural"),
      badge: t(v.gender === "female" ? "voice_female" : "voice_male") })),
    ...(gender === "all" ? voices.map((v) => ({ value: v.voiceURI, label: v.name, group: t("voice_group_browser"), badge: t("voice_offline") })) : []),
  ];
  const offline = neural && !neural.length;
  return (
    <Card title={t("voice_title")} desc={t("voice_desc")}
      action={<Button className="text-xs" onClick={() => speak("test", t("voice_sample"), speechOpts(prefs))}><Volume2 size={14} /> {t("voice_test")}</Button>}>
      <Row tight label={t("voice_auto")} desc={t("voice_auto_desc")}><Toggle checked={!!prefs.voiceReply} onChange={(v) => st.setPref("voiceReply", v)} /></Row>
      <Row label={t("voice_gender")} desc={offline ? t("voice_neural_offline") : null}>
        <Segmented value={gender} onChange={setGender}
          options={[{ id: "all", label: t("voice_all") }, { id: "female", label: t("voice_female") }, { id: "male", label: t("voice_male") }]} />
      </Row>
      <Row label={t("voice_voice")} desc={neural === null ? t("voice_loading") : !neural.length && !voices.length ? t("voice_none") : t("voice_per_lang", { lang: lang.toUpperCase() })}>
        <Select value={prefs.voiceBy?.[lang] || ""} onChange={(v) => { st.setPref("voiceBy", { ...prefs.voiceBy, [lang]: v }); speak("test", t("voice_sample"), { ...speechOpts(prefs), voice: v }); }}
          options={options} />
      </Row>
      <SliderRow label={t("voice_rate")} value={prefs.voiceRate || 1} min={0.6} max={1.6} step={0.1} format={(v) => v.toFixed(1)} unit="×"
        onCommit={(v) => st.setPref("voiceRate", v)} />
      <p className="px-4 py-3.5 text-xs leading-relaxed text-subtle @md:px-5">{t("voice_privacy")}</p>
    </Card>
  );
}

function General() {
  const t = useT();
  const theme = useStore((s) => s.prefs.theme);
  const lang = useStore((s) => s.prefs.lang);
  const [langs, setLangs] = useState([]);
  useEffect(() => { api.get("/api/languages").then(setLangs); }, []);
  return (
    <div className="space-y-4">
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
    <GlobalRules />
    <VoiceCard />
    </div>
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
        <Row tight label={t("enabled")}><Toggle checked={!!s.cloud_fallback} onChange={(v) => st.updateSettings({ cloud_fallback: v })} /></Row>
        <Row label={t("fallback_model")}><ModelSelect value={s.fallback_model} allowEmpty onChange={(v) => st.updateSettings({ fallback_model: v })} /></Row>
      </Card>
      <ModelProfiles />
      <ProviderStatusList />
    </div>
  );
}

// Model profiles: per-model overrides of what the provider reports (thinking, vision, streaming, tool calls)
// plus temperature and output limit. "Auto" keeps the provider's own behaviour.
const PROFILE_KEYS = ["thinking", "vision", "streaming", "tools"];

function ModelProfiles() {
  const t = useT();
  const profiles = useStore((x) => x.settings?.model_profiles || {});
  const active = useStore((x) => x.prefs.model || x.settings?.active_model || "");
  const [model, setModel] = useState(active);
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (!model && active) setModel(active); }, [active]);
  const p = profiles[model] || {};
  const caps = useStore((x) => x.modelCaps(model));
  const save = async (next) => {
    const st = useStore.getState();
    setBusy(true);
    try {
      await api.put("/api/models/profile", { model, ...Object.fromEntries(PROFILE_KEYS.map((k) => [k, next[k] || "auto"])),
        temperature: next.temperature ?? null, max_tokens: next.max_tokens ?? null, effort: next.effort || null });
      await st.refreshSettings();
      await st.loadProviderModels(model.split(":")[0]);
      if (model === st.currentModel()) st.loadContext();
    } catch (e) {
      st.notify(t("profile_save_failed"), "error", e.message);
    } finally { setBusy(false); }
  };
  const set = (patch) => save({ ...p, ...patch });
  const onOff = [{ id: "auto", label: t("prof_auto") }, { id: "on", label: t("prof_on") }, { id: "off", label: t("prof_off") }];
  const others = Object.keys(profiles).filter((m) => m !== model);
  return (
    <Card title={t("model_profiles")} desc={t("model_profiles_desc")}
      action={busy ? <Loader2 size={15} className="animate-spin text-accent" /> : null}>
      <div className="space-y-2.5 px-5 py-4">
        <ModelSelect value={model} onChange={setModel} />
        {others.length > 0 && (
          <div className="flex flex-wrap items-center gap-1.5 text-xs text-muted">
            <span>{t("prof_saved")}:</span>
            {others.map((m) => <button key={m} onClick={() => setModel(m)} className="rounded-lg bg-hover px-2 py-0.5 font-mono hover:text-fg">{m}</button>)}
          </div>
        )}
      </div>
      {model && (
        <>
          <Row stack label={t("prof_thinking")} desc={t("prof_thinking_desc")}><Segmented value={p.thinking || "auto"} options={onOff} onChange={(v) => set({ thinking: v })} /></Row>
          {caps?.efforts?.length > 0 && (
            <Row stack label={t("effort")} desc={t(caps.effort_via === "prompt" ? "effort_desc_prompt" : "effort_desc_api")}>
              <Segmented value={p.effort || ""} onChange={(v) => set({ effort: v || null })}
                options={["", ...caps.efforts].map((l) => ({ id: l, label: t(l ? `effort_${l}` : "effort_auto") }))} />
            </Row>
          )}
          <Row stack label={t("prof_vision")} desc={t("prof_vision_desc")}><Segmented value={p.vision || "auto"} options={onOff} onChange={(v) => set({ vision: v })} /></Row>
          <Row stack label={t("prof_streaming")} desc={t("prof_streaming_desc")}><Segmented value={p.streaming || "auto"} options={onOff} onChange={(v) => set({ streaming: v })} /></Row>
          <Row stack label={t("prof_tools")} desc={t("prof_tools_desc")}>
            <Segmented value={p.tools || "auto"} onChange={(v) => set({ tools: v })}
              options={[{ id: "auto", label: t("prof_auto") }, { id: "native", label: t("prof_native") }, { id: "tags", label: t("prof_tags") }]} />
          </Row>
          <Row tight label={t("prof_temperature")} desc={t("prof_temperature_desc")}>
            <NumberInput value={p.temperature} decimal max={2} placeholder={t("prof_auto")} onCommit={(v) => set({ temperature: v })} />
          </Row>
          <Row tight label={t("prof_max_tokens")} desc={t("prof_max_tokens_desc")}>
            <NumberInput value={p.max_tokens} max={1000000} placeholder={t("prof_auto")} onCommit={(v) => set({ max_tokens: v })} />
          </Row>
          {Object.keys(p).length > 0 && (
            <div className="flex justify-end px-5 pb-4">
              <Button variant="ghost" onClick={() => save({})}><RefreshCw size={13} />{t("prof_reset")}</Button>
            </div>
          )}
        </>
      )}
    </Card>
  );
}

function NumberInput({ value, onCommit, placeholder, decimal, max }) {
  const [v, setV] = useState(value ?? "");
  useEffect(() => setV(value ?? ""), [value]);
  const commit = () => {
    if (String(value ?? "") === String(v)) return;
    const n = v === "" ? null : Math.min(max, decimal ? Math.round(parseFloat(v) * 100) / 100 : parseInt(v, 10));
    onCommit(n == null || Number.isNaN(n) ? null : n);
  };
  return (
    <input value={v} inputMode={decimal ? "decimal" : "numeric"} placeholder={placeholder}
      onChange={(e) => setV(e.target.value.replace(",", ".").replace(decimal ? /[^\d.]/g : /[^\d]/g, ""))}
      onBlur={commit} onKeyDown={(e) => e.key === "Enter" && e.currentTarget.blur()}
      className={`${inputCls} h-8 w-28 px-2.5 text-right text-[13px]`} />
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
  // Cloudflare Workers AI is addressed by its Account ID (the URL is built from it), every other provider by URL.
  const field = cfg.kind === "cloudflare" ? "account_id" : "base_url";
  useEffect(() => setUrl(cfg[field] || ""), [cfg[field]]);
  const urlDirty = url !== (cfg[field] || "");
  const save = (p) => st.updateSettings({ providers: { [id]: p } }).then(() => st.refreshProvider(id));
  const saveUrl = () => urlDirty && save({ [field]: url.trim() });
  const saveKey = async () => {
    if (!key) return;
    await st.setSecret(`${id}_api_key`, key); // also re-queries this provider's models at once
    setKey("");
  };
  const runTest = async () => {
    setBusy(true); setTest(null);
    try {
      if (key) await saveKey();
      if (urlDirty) await save({ [field]: url.trim() });
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
          <label className="text-xs text-muted">{t(field === "account_id" ? "cf_account_id" : "base_url")}
            <div className="mt-1 flex gap-2">
              <input className={`${inputCls} font-mono ${urlDirty ? "!border-warn" : ""}`} value={url} onChange={(e) => setUrl(e.target.value)}
                placeholder={field === "account_id" ? "0123456789abcdef0123456789abcdef" : undefined}
                onKeyDown={(e) => e.key === "Enter" && saveUrl()} />
              {urlDirty && <Button variant="primary" onClick={saveUrl}><Save size={14} /> {t("save")}</Button>}
            </div>
            {urlDirty ? <span className="mt-1 block text-[11px] text-warn">{t("unsaved_change")}</span>
              : field === "account_id" && <span className="mt-1 block text-[11px] text-subtle">{t("cf_account_hint")}</span>}
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

function TextSetting({ section, field, label, desc, placeholder }) {
  const saved = useStore((x) => x.settings?.[section]?.[field] || "");
  const [v, setV] = useState(saved);
  const st = useStore.getState();
  const dirty = v !== saved;
  const save = () => st.updateSettings({ [section]: { [field]: v.trim() } });
  return (
    <Row label={label} desc={desc}>
      <div className="flex gap-2">
        <input value={v} onChange={(e) => setV(e.target.value)} placeholder={placeholder} className={`${inputCls} font-mono ${dirty ? "!border-warn" : ""}`}
          onKeyDown={(e) => e.key === "Enter" && dirty && save()} />
        {dirty && <Button variant="primary" onClick={save}><Save size={14} /></Button>}
      </div>
    </Row>
  );
}

const ENGINE_STATE = { ok: "text-ok", resting: "text-subtle", empty: "text-subtle", blocked: "text-warn", "off-topic": "text-warn", error: "text-danger" };

function Web() {
  const t = useT();
  const [q, setQ] = useState("Audi 2026 modelleri");
  const [res, setRes] = useState(null);
  const [busy, setBusy] = useState(false);
  const test = async () => {
    setBusy(true);
    try { setRes(await api.get(`/api/web/search?q=${encodeURIComponent(q)}`)); } catch (e) { setRes({ error: e.message }); }
    setBusy(false);
  };
  return (
    <div className="space-y-4">
      <Card title={t("web_engines")} desc={t("web_engines_desc")}>
        <SecretField name="google_search_key" label="Google Programmable Search" desc={t("google_search_desc")} placeholder="AIza…" />
        <TextSetting section="search" field="google_cx" label={t("google_cx")} desc={t("google_cx_desc")} placeholder="0123456789abcdef0" />
        <SecretField name="yandex_search_key" label="Yandex Search API" desc={t("yandex_search_desc")} placeholder="AQVN…" />
        <TextSetting section="search" field="yandex_folder" label={t("yandex_folder")} desc={t("yandex_folder_desc")} placeholder="b1g…" />
        <SecretField name="bing_search_key" label="Bing Web Search API" desc={t("bing_search_desc")} placeholder="Ocp-Apim-Subscription-Key" />
        <SecretField name="brave_api_key" label="Brave Search API" desc={t("brave_desc")} placeholder="BSA…" />
        <SecretField name="tavily_api_key" label="Tavily API" desc={t("tavily_desc")} placeholder="tvly-…" />
        <TextSetting section="search" field="searxng_url" label="SearXNG" desc={t("searxng_desc")} placeholder="http://127.0.0.1:8888" />
      </Card>
      <Card title={t("maps_services")} desc={t("maps_services_desc")}>
        <SecretField name="google_maps_key" label="Google Places API" desc={t("google_maps_desc")} placeholder="AIza…" />
        <SecretField name="yandex_maps_key" label="Yandex Places API" desc={t("yandex_maps_desc")} placeholder="…" />
        <Row label="OpenStreetMap" desc={t("osm_desc")}><span className="text-[13px] font-medium text-ok">{t("always_on")}</span></Row>
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
                {res.report && (
                  <div className="mb-2 flex flex-wrap gap-1.5">
                    {Object.entries(res.report).filter(([k]) => k !== "cache").map(([k, v]) => (
                      <span key={k} title={v} className={`rounded-md bg-hover px-1.5 py-0.5 ${ENGINE_STATE[v.split(/[ :]/)[0]] || "text-muted"}`}>
                        {k}: {t("engine_" + v.split(/[ :]/)[0]) || v}{v.startsWith("ok") ? " " + v.slice(2) : ""}
                      </span>
                    ))}
                  </div>
                )}
                {res.results.map((r) => <div key={r.url} className="truncate py-0.5"><a href={r.url} target="_blank" rel="noreferrer" className="text-accent hover:underline">{r.title || r.url}</a> <span className="text-subtle">· {(r.engines || [r.engine]).join(", ")}</span></div>)}
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

// ---------------------------------------------------------------- multi-model + quotas
const CAPS = ["code", "reasoning", "fast", "vision", "long_context", "writing"];
const ROLES = ["planner", "coder", "debugger", "tester"];

// "in 2 h 14 min" / "14:05" style reset times.
function useClock(ms = 30000) {
  const [now, setNow] = useState(Date.now() / 1000);
  useEffect(() => { const id = setInterval(() => setNow(Date.now() / 1000), ms); return () => clearInterval(id); }, [ms]);
  return now;
}
function fmtIn(t, ts, now) {
  if (!ts) return "";
  const s = Math.max(0, ts - now);
  const d = Math.floor(s / 86400), h = Math.floor((s % 86400) / 3600), m = Math.max(1, Math.round((s % 3600) / 60));
  const rel = d ? `${d} ${t("unit_d")} ${h} ${t("unit_h")}` : h ? `${h} ${t("unit_h")} ${m} ${t("unit_min")}` : `${m} ${t("unit_min")}`;
  const at = new Date(ts * 1000).toLocaleString(undefined, d ? { weekday: "short", hour: "2-digit", minute: "2-digit" } : { hour: "2-digit", minute: "2-digit" });
  return t("quota_in", { rel, at });
}

function UsageBar({ used, limit }) {
  const pct = limit ? Math.min(100, (used / limit) * 100) : 0;
  return (
    <div className="h-1.5 overflow-hidden rounded-full bg-hover">
      {limit > 0 && <div className={`h-full rounded-full ${pct >= 90 ? "bg-danger" : pct >= 70 ? "bg-warn" : "bg-accent"}`} style={{ width: `${pct}%` }} />}
    </div>
  );
}

function LimitInput({ value, onCommit, placeholder }) {
  const [v, setV] = useState(value ?? "");
  useEffect(() => setV(value ?? ""), [value]);
  return (
    <input value={v} inputMode="numeric" placeholder={placeholder} onChange={(e) => setV(e.target.value.replace(/[^\d]/g, ""))}
      onBlur={() => String(value ?? "") !== v && onCommit(v ? Number(v) : null)}
      className={`${inputCls} h-7 w-24 px-2 text-right text-xs`} />
  );
}

function QuotaWindow({ t, name, w, limits, onLimit, now }) {
  const reqLimit = limits[`requests_${name}`], tokLimit = limits[`tokens_${name}`];
  return (
    <div className="min-w-0 flex-1 space-y-2 rounded-xl border border-line p-3">
      <div className="flex items-center justify-between gap-2">
        <span className="text-[12px] font-semibold">{t(`quota_${name}`)}</span>
        <span className="truncate text-[11px] text-subtle">{w.reset_at ? fmtIn(t, w.reset_at, now) : t("quota_unused")}</span>
      </div>
      {[["requests", w.requests, reqLimit], ["tokens", w.tokens, tokLimit]].map(([kind, used, lim]) => (
        <div key={kind} className="space-y-1">
          <div className="flex items-center justify-between gap-2 text-[11px]">
            <span className="text-muted">{t(`quota_${kind}`)}</span>
            <span className="flex items-center gap-1.5">
              <span className="whitespace-nowrap font-mono tabular-nums">{kind === "tokens" ? formatTokens(used) : used}{lim ? ` / ${kind === "tokens" ? formatTokens(lim) : lim}` : ""}</span>
              <LimitInput value={lim} placeholder={t("quota_limit")} onCommit={(n) => onLimit(`${kind}_${name}`, n)} />
            </span>
          </div>
          <UsageBar used={used} limit={lim} />
        </div>
      ))}
    </div>
  );
}

function QuotaPanel({ data, limits, onLimit, onClear }) {
  const t = useT();
  const now = useClock();
  const providers = Object.entries(data?.providers || {});
  if (!data) return <div className="grid h-24 place-items-center"><Loader2 size={18} className="animate-spin text-accent" /></div>;
  if (!providers.length) return <div className="px-5 py-6 text-center text-[13px] text-muted">{t("quota_empty")}</div>;
  return providers.map(([pid, p]) => {
    const hdr = p.headers || {};
    return (
      <div key={pid} className="space-y-2.5 px-5 py-4">
        <div className="flex flex-wrap items-center gap-2">
          {p.local ? <Cpu size={14} className="text-muted" /> : <Cloud size={14} className="text-muted" />}
          <span className="text-[13px] font-semibold">{p.name}</span>
          <span className="rounded-md bg-hover px-1.5 py-0.5 text-[10px] text-muted">{t(p.local ? "local" : "cloud")}</span>
          {Object.entries(p.cooldowns || {}).map(([key, c]) => (
            <span key={key} className="flex items-center gap-1 rounded-md bg-danger/10 px-1.5 py-0.5 text-[11px] text-danger" title={c.message}>
              <AlertTriangle size={11} /> {key.endsWith(":*") ? t("quota_all_models") : key.split(":").slice(1).join(":")} · {t(`cd_${c.code}`)} · {fmtIn(t, c.until, now)}
              <button onClick={() => onClear(key.endsWith(":*") ? `${pid}:` : key)} className="ml-1 underline">{t("quota_retry_now")}</button>
            </span>
          ))}
        </div>
        <div className="flex flex-col gap-2 sm:flex-row">
          {["5h", "week"].map((n) => (
            <QuotaWindow key={n} t={t} name={n} w={p.windows[n]} limits={p.limits || {}} now={now}
              onLimit={(k, v) => onLimit(pid, k, v)} />
          ))}
        </div>
        {(hdr.requests || hdr.tokens) && (
          <div className="flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-muted">
            <span className="font-medium">{t("quota_reported")}:</span>
            {["requests", "tokens"].filter((k) => hdr[k]).map((k) => (
              <span key={k}>{t(`quota_${k}`)}: {hdr[k].remaining ?? "?"}/{hdr[k].limit ?? "?"}{hdr[k].reset_at ? ` · ${fmtIn(t, hdr[k].reset_at, now)}` : ""}</span>
            ))}
          </div>
        )}
      </div>
    );
  });
}

function MultiModel() {
  const t = useT();
  const s = useStore((x) => x.settings);
  const st = useStore.getState();
  const mm = s.multi_model || {};
  const [usage, setUsage] = useState(null);
  const load = () => api.get("/api/usage").then(setUsage).catch(() => setUsage({ providers: {}, pool: [] }));
  useEffect(() => { load(); const id = setInterval(load, 15000); return () => clearInterval(id); }, []);
  const save = (patch) => st.updateSettings({ multi_model: patch }).then(load);
  const pool = (mm.pool || []).map((e) => (typeof e === "string" ? { model: e, tags: [] } : e));
  const setPool = (next) => save({ pool: next });
  const status = (id) => usage?.pool?.find((p) => p.model === id);
  const clear = (key) => api.post(`/api/usage/clear?model=${encodeURIComponent(key)}`).then(load);
  const localIds = new Set(Object.entries(s.providers || {}).filter(([, c]) => c.local).map(([id]) => id));
  return (
    <div className="space-y-4">
      <Card title={t("mm_title")} desc={t("mm_desc")}>
        <Row tight label={t("enabled")}><Toggle checked={!!mm.enabled} onChange={(v) => save({ enabled: v })} /></Row>
        <Row tight label={t("mm_auto_switch")} desc={t("mm_auto_switch_desc")}><Toggle checked={mm.auto_switch !== false} onChange={(v) => save({ auto_switch: v })} /></Row>
        <Row tight label={t("mm_delegate")} desc={t("mm_delegate_desc")}><Toggle checked={mm.delegate !== false} onChange={(v) => save({ delegate: v })} /></Row>
        <div className="flex gap-2 px-5 py-3 text-xs leading-snug text-muted"><Cpu size={14} className="mt-0.5 shrink-0" />{t("mm_local_note")}</div>
      </Card>

      <Card title={t("mm_pool")} desc={t("mm_pool_desc")}
        action={<Button className="text-xs" onClick={() => setPool([...pool, { model: "", tags: [] }])}><Plus size={14} /> {t("add")}</Button>}>
        {pool.length === 0 && <div className="px-5 py-6 text-center text-[13px] text-muted">{t("mm_empty_pool")}</div>}
        {pool.map((e, i) => {
          const stt = status(e.model);
          return (
            <div key={i} className="space-y-2 px-5 py-3.5">
              <div className="flex items-center gap-2">
                <div className="min-w-0 flex-1"><ModelSelect cloudOnly value={e.model} onChange={(v) => setPool(pool.map((x, j) => (j === i ? { ...x, model: v } : x)))} /></div>
                {e.model && mm.enabled && stt && (
                  <span className={`shrink-0 rounded-md px-1.5 py-0.5 text-[11px] ${stt.available ? "bg-ok/10 text-ok" : "bg-danger/10 text-danger"}`} title={stt.cooldown?.message || ""}>
                    {stt.available ? t("mm_available") : stt.cooldown ? `${t(`cd_${stt.cooldown.code}`)} · ${fmtIn(t, stt.cooldown.until, Date.now() / 1000)}`
                      : t("mm_limit_reached", { w: t(`quota_${stt.limit}`) })}
                  </span>
                )}
                <button onClick={() => setPool(pool.filter((_, j) => j !== i))} title={t("delete")} className="rounded-lg p-1.5 text-subtle hover:bg-hover hover:text-danger"><Trash2 size={15} /></button>
              </div>
              <div className="flex flex-wrap gap-1.5">
                {CAPS.map((c) => {
                  const on = (e.tags || []).includes(c);
                  return (
                    <button key={c} onClick={() => setPool(pool.map((x, j) => (j === i ? { ...x, tags: on ? x.tags.filter((y) => y !== c) : [...(x.tags || []), c] } : x)))}
                      className={`rounded-full border px-2.5 py-0.5 text-[11px] transition ${on ? "border-accent bg-accent-soft text-accent" : "border-line text-muted hover:bg-hover"}`}>
                      {t(`mm_tag_${c}`)}
                    </button>
                  );
                })}
              </div>
            </div>
          );
        })}
      </Card>

      <Card title={t("mm_agents")} desc={t("mm_agents_desc")}>
        {ROLES.map((r) => (
          <Row key={r} label={t(`mm_role_${r}`)}>
            <ModelSelect cloudOnly allowEmpty emptyLabel={t("mm_main_model")} value={(mm.agents || {})[r] || ""} onChange={(v) => save({ agents: { [r]: v } })} />
            {(mm.agents || {})[r] && localIds.has((mm.agents || {})[r].split(":")[0]) && (
              <div className="mt-1.5 flex items-center gap-1.5 text-xs text-warn"><AlertTriangle size={13} />{t("mm_local_ignored")}</div>
            )}
          </Row>
        ))}
      </Card>

      <Card title={t("quota_title")} desc={t("quota_desc")}
        action={<button onClick={load} title={t("refresh")} className="rounded-lg p-1.5 text-muted hover:bg-hover"><RefreshCw size={15} /></button>}>
        <QuotaPanel data={usage} limits={mm.limits || {}} onClear={clear}
          onLimit={(pid, k, v) => save({ limits: { [pid]: { ...((mm.limits || {})[pid] || {}), [k]: v } } })} />
      </Card>
    </div>
  );
}

// MCP servers: external tool servers (GitHub, databases, files...) the model can call through the mcp tool.
const MCP_EMPTY = { id: "", name: "", transport: "stdio", command: "", args: "", url: "", env: "", headers: "", enabled: true };
const lines = (obj) => Object.entries(obj || {}).map(([k, v]) => `${k}=${v}`).join("\n");
const parseLines = (text) => Object.fromEntries(text.split("\n").map((l) => l.trim()).filter((l) => l.includes("="))
  .map((l) => [l.slice(0, l.indexOf("=")).trim(), l.slice(l.indexOf("=") + 1).trim()]));
const splitArgs = (s) => (s.match(/"[^"]*"|\S+/g) || []).map((a) => a.replace(/^"|"$/g, ""));

function McpForm({ init, onClose, onSaved }) {
  const t = useT();
  const [f, setF] = useState(init);
  const [busy, setBusy] = useState(false);
  const isNew = !init.id;
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const save = async () => {
    const id = (f.id || f.name).toLowerCase().replace(/[^a-z0-9_-]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 32);
    if (!id) return;
    setBusy(true);
    try {
      const body = { name: f.name || id, transport: f.transport, command: f.command, args: splitArgs(f.args), url: f.url, enabled: f.enabled };
      if (f.env.trim() || isNew || f.envTouched) body.env = parseLines(f.env);
      if (f.headers.trim() || isNew || f.headersTouched) body.headers = parseLines(f.headers);
      const r = await api.put(`/api/mcp/${id}`, body);
      onSaved(r);
    } catch (e) {
      useStore.getState().notify(t("mcp_save_failed"), "error", e.message);
    } finally { setBusy(false); }
  };
  return (
    <Modal title={t(isNew ? "mcp_add" : "mcp_edit")} onClose={onClose} width="max-w-xl"
      footer={<><Button variant="ghost" onClick={onClose}>{t("cancel")}</Button>
        <Button variant="primary" disabled={busy || !(f.id || f.name) || (f.transport === "stdio" ? !f.command : !f.url)} onClick={save}>
          {busy ? <Loader2 size={14} className="animate-spin" /> : t(isNew ? "mcp_connect" : "save")}</Button></>}>
      <div className="space-y-3 text-[13px]">
        <label className="block"><span className="mb-1 block font-medium">{t("name")}</span>
          <input className={inputCls} value={f.name} onChange={set("name")} placeholder="github" disabled={!isNew} /></label>
        <Segmented value={f.transport} onChange={(v) => setF({ ...f, transport: v })}
          options={[{ id: "stdio", label: t("mcp_stdio") }, { id: "http", label: t("mcp_http") }]} />
        {f.transport === "stdio" ? (
          <>
            <label className="block"><span className="mb-1 block font-medium">{t("mcp_command")}</span>
              <input className={`${inputCls} font-mono`} value={f.command} onChange={set("command")} placeholder="npx" /></label>
            <label className="block"><span className="mb-1 block font-medium">{t("mcp_args")}</span>
              <input className={`${inputCls} font-mono`} value={f.args} onChange={set("args")} placeholder="-y @modelcontextprotocol/server-github" /></label>
            <label className="block"><span className="mb-1 block font-medium">{t("mcp_env")}</span>
              <textarea className={`${inputCls} h-20 font-mono`} value={f.env} onChange={(e) => setF({ ...f, env: e.target.value, envTouched: true })}
                placeholder={isNew ? "GITHUB_PERSONAL_ACCESS_TOKEN=..." : t("mcp_secret_keep", { keys: (init.env_keys || []).join(", ") || "—" })} /></label>
          </>
        ) : (
          <>
            <label className="block"><span className="mb-1 block font-medium">URL</span>
              <input className={`${inputCls} font-mono`} value={f.url} onChange={set("url")} placeholder="https://example.com/mcp" /></label>
            <label className="block"><span className="mb-1 block font-medium">{t("mcp_headers")}</span>
              <textarea className={`${inputCls} h-20 font-mono`} value={f.headers} onChange={(e) => setF({ ...f, headers: e.target.value, headersTouched: true })}
                placeholder={isNew ? "Authorization=Bearer ..." : t("mcp_secret_keep", { keys: (init.header_keys || []).join(", ") || "—" })} /></label>
          </>
        )}
        <p className="text-xs leading-snug text-muted">{t("mcp_secret_note")}</p>
      </div>
    </Modal>
  );
}

function McpServers() {
  const t = useT();
  const [servers, setServers] = useState(null);
  const [form, setForm] = useState(null);
  const [busy, setBusy] = useState("");
  const load = () => api.get("/api/mcp").then(setServers).catch(() => setServers({}));
  useEffect(() => { load(); }, []);
  const restart = async (id) => { setBusy(id); try { await api.post(`/api/mcp/${id}/restart`); } finally { setBusy(""); load(); } };
  const toggle = async (id, s, enabled) => {
    setBusy(id);
    try { await api.put(`/api/mcp/${id}`, { name: s.name, transport: s.transport, command: s.command, args: s.args, url: s.url, cwd: s.cwd || "", enabled }); }
    finally { setBusy(""); load(); }
  };
  const remove = async (id) => {
    if (!(await useStore.getState().confirm({ title: t("mcp_remove"), message: t("mcp_remove_confirm", { name: id }), danger: true }))) return;
    await api.delete(`/api/mcp/${id}`);
    load();
  };
  const list = Object.entries(servers || {});
  return (
    <div className="space-y-4">
      <Card title={t("mcp_title")} desc={t("mcp_desc")}
        action={<Button className="text-xs" onClick={() => setForm({ ...MCP_EMPTY })}><Plus size={14} /> {t("add")}</Button>}>
        {servers == null && <div className="grid h-20 place-items-center"><Loader2 size={16} className="animate-spin text-accent" /></div>}
        {servers && list.length === 0 && <div className="px-5 py-6 text-center text-[13px] text-muted">{t("mcp_empty")}</div>}
        {list.map(([id, s]) => (
          <div key={id} className="space-y-2 px-4 py-3.5 @md:px-5">
            <div className="flex flex-wrap items-center gap-2">
              <Plug size={15} className={s.running ? "text-ok" : s.error ? "text-danger" : "text-subtle"} />
              <span className="font-medium">{s.name || id}</span>
              <span className="rounded-md bg-hover px-1.5 py-0.5 font-mono text-[11px] text-muted">{s.transport}</span>
              <span className={`text-xs ${s.running ? "text-ok" : s.error ? "text-danger" : "text-subtle"}`}>
                {busy === id ? t("mcp_starting") : s.running ? t("mcp_running", { n: s.tools.length }) : s.enabled === false ? t("mcp_disabled") : s.error ? t("mcp_failed") : t("mcp_stopped")}</span>
              <div className="ml-auto flex items-center gap-1">
                <Toggle checked={s.enabled !== false} onChange={(v) => toggle(id, s, v)} />
                <button title={t("mcp_restart")} onClick={() => restart(id)} className="rounded-lg p-1.5 text-muted hover:bg-hover"><RefreshCw size={14} className={busy === id ? "animate-spin" : ""} /></button>
                <button title={t("mcp_edit")} onClick={() => setForm({ ...MCP_EMPTY, ...s, id, args: (s.args || []).join(" "), env: "", headers: "" })} className="rounded-lg p-1.5 text-muted hover:bg-hover"><Pencil size={14} /></button>
                <button title={t("mcp_remove")} onClick={() => remove(id)} className="rounded-lg p-1.5 text-muted hover:bg-hover hover:text-danger"><Trash2 size={14} /></button>
              </div>
            </div>
            <div className="truncate font-mono text-[11px] text-subtle">{s.transport === "http" ? s.url : [s.command, ...(s.args || [])].join(" ")}</div>
            {s.error && <div className="rounded-lg bg-danger/10 px-2.5 py-1.5 text-xs text-danger">{s.error}</div>}
            {s.tools?.length > 0 && (
              <div className="flex flex-wrap gap-1">
                {s.tools.map((tl) => <span key={tl.name} title={tl.description} className={`rounded-md px-1.5 py-0.5 font-mono text-[11px] ${tl.read_only ? "bg-ok/10 text-ok" : "bg-hover text-muted"}`}>{tl.name}</span>)}
              </div>
            )}
          </div>
        ))}
      </Card>
      <div className="flex gap-2 px-1 text-xs leading-snug text-muted"><Info size={14} className="mt-0.5 shrink-0" />{t("mcp_safety")}</div>
      {form && <McpForm init={form} onClose={() => setForm(null)} onSaved={() => { setForm(null); load(); }} />}
    </div>
  );
}



const PANES = { general: General, models: Models, multi: MultiModel, providers: Providers, context: Context, web: Web, mcp: McpServers, security: Security, languages: LanguagesTab };

export default function SettingsView() {
  const t = useT();
  const settings = useStore((s) => s.settings);
  const tab = useStore((s) => (PANES[s.settingsTab] ? s.settingsTab : "general"));
  useEffect(() => { useStore.getState().loadContext(); }, []);
  if (!settings) return null;
  const Pane = PANES[tab];
  const cur = TABS.find((x) => x.id === tab);
  return (
    <div className="@container flex min-h-0 flex-1 flex-col">
      <div className="flex min-h-0 flex-1 flex-col @3xl:flex-row">
      <nav className="flex shrink-0 gap-1 overflow-x-auto border-b border-line px-3 py-2 @3xl:w-52 @3xl:flex-col @3xl:border-b-0 @3xl:border-r @3xl:px-3 @3xl:py-5">
        <h1 className="hidden px-3 pb-3 text-lg font-semibold @3xl:block">{t("settings")}</h1>
        {TABS.map((x) => (
          <button key={x.id} onClick={() => useStore.setState({ settingsTab: x.id })}
            className={`flex shrink-0 items-center gap-2.5 rounded-xl px-3 py-2 text-[13px] transition ${tab === x.id ? "bg-active font-medium" : "text-muted hover:bg-hover hover:text-fg"}`}>
            <x.icon size={16} /> {t(x.key)}
          </button>
        ))}
        <button onClick={() => useStore.getState().setView("about")}
          className="flex shrink-0 items-center gap-2.5 rounded-xl px-3 py-2 text-[13px] text-muted hover:bg-hover hover:text-fg @3xl:mt-auto">
          <Info size={16} /> {t("set_about")}
        </button>
      </nav>
      <div className="@container min-h-0 min-w-0 flex-1 overflow-y-auto">
        <div className="mx-auto max-w-5xl px-3 py-4 @xl:px-6 @xl:py-8">
          <div className="sticky top-0 z-10 -mx-1 mb-5 flex flex-wrap items-center justify-between gap-2 bg-bg/90 px-1 py-2 backdrop-blur">
            <h2 className="text-xl font-semibold tracking-tight">{t(cur.key)}</h2>
            <SaveIndicator />
          </div>
          <Pane />
        </div>
      </div>
      </div>
    </div>
  );
}
