import { useEffect, useMemo, useState } from "react";
import {
  AlertCircle, AlertTriangle, Bot, Check, CheckCircle2, ChevronDown, Cloud, Cpu, Eye, EyeOff, FileText, Gauge, Globe,
  Info, KeyRound, Languages, Loader2, Monitor, Moon, Palette, Plus, RefreshCw, Save, Search, Server, ShieldCheck, Sun,
  Trash2, X, Zap, Network, Plug, Volume2, Pencil, HardDrive, Power, LogIn, LogOut, Film, AudioLines, MessageSquarePlus, Play,
} from "lucide-react";
import VoicesPane from "./VoicesPane";
import { GenderIcon } from "./VoiceLibrary";
import { edgeVoices, speak, speechOpts, speechSupported, voicesFor } from "../lib/speech";
import { useStore, useT } from "../lib/store";
import { api } from "../lib/api";
import { formatTokens } from "../lib/fileTypes";
import { errorText, serviceError } from "../lib/errors";
import { Button, Modal, Toggle, inputCls } from "./ui";
import Select from "./Select";
import Markdown from "./Markdown";
import { CapBadges, CapIcons, capsHint } from "./Caps";
import RangeField from "./RangeField";
import { McpArgFields, argsFromVals, missingArgs } from "./McpArgs";

const TABS = [
  { id: "general", icon: Palette, key: "set_general" },
  { id: "models", icon: Bot, key: "set_models" },
  { id: "multi", icon: Network, key: "set_multi" },
  { id: "providers", icon: Server, key: "providers" },
  { id: "context", icon: Gauge, key: "context" },
  { id: "web", icon: Globe, key: "set_web" },
  { id: "voices", icon: AudioLines, key: "set_voices" },
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

function SliderRow({ label, desc, onCommit, ...range }) {
  return (
    <Row label={label} desc={desc}>
      <RangeField {...range} onCommit={(v) => v != null && onCommit(v)} />
    </Row>
  );
}

// Free AI video engines (Hugging Face ZeroGPU Spaces): image-to-video and text-to-video, with their live state.
// Nothing to install or pay; a free Hugging Face token (Image generation > Hugging Face) raises the daily quota.
function VideoEnginesCard() {
  const t = useT();
  const [d, setD] = useState(null);
  const [busy, setBusy] = useState(false);
  const load = () => { setBusy(true); api.get("/api/video/engines").then(setD).catch(() => setD({ engines: [], error: true })).finally(() => setBusy(false)); };
  useEffect(load, []);
  const ok = (s) => /RUNNING/.test(s || "");
  const sleeping = (s) => /SLEEP|PAUSED|BUILD|STOPPED/.test(s || "");
  return (
    <Card title={<span className="flex items-center gap-2"><Film size={15} />{t("video_engines")} <span className="text-xs font-normal text-subtle">{d?.engines?.length || ""}</span></span>}
      desc={t("video_engines_desc")}>
      <div className="divide-y divide-line">
        {(d?.engines || []).map((e, i) => (
          <div key={e.id} className="flex flex-wrap items-center gap-2 px-5 py-3 text-[13px]">
            <span className={`h-2 w-2 shrink-0 rounded-full ${ok(e.stage) ? "bg-ok" : sleeping(e.stage) ? "bg-warn" : "bg-danger"}`} />
            <span className="font-medium">{e.kind === "svd" ? "AnimateLCM-SVD" : `Wan 2.2${i ? " (2)" : ""}`}</span>
            <span className="rounded-md bg-hover px-1.5 py-0.5 text-[11px] text-muted">{t(e.kind === "svd" ? "ve_kind_svd" : "ve_kind_wan")}</span>
            <span className="text-[11.5px] text-subtle">{ok(e.stage) ? t("ve_running") : sleeping(e.stage) ? t("ve_sleeping") : e.stage}</span>
            <a href={e.url} target="_blank" rel="noreferrer" className="ml-auto truncate font-mono text-[11px] text-accent hover:underline">{e.id}</a>
          </div>
        ))}
        {!d && <div className="px-5 py-3 text-[12.5px] text-muted"><Loader2 size={13} className="mr-1 inline animate-spin" />{t("loading")}</div>}
        <div className="flex flex-wrap items-center gap-2 px-5 py-3 text-[12px] text-muted">
          <span>{d?.token ? t("ve_token_on") : t("ve_token_off")}</span>
          <Button className="ml-auto" onClick={load} disabled={busy}>{busy ? <Loader2 size={13} className="animate-spin" /> : <RefreshCw size={13} />}{t("ve_refresh")}</Button>
        </div>
      </div>
    </Card>
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
      icons: <CapIcons m={m} />, keywords: capsHint(t, m),
      hint: [vision && m.vision === false && `⚠ ${t("cap_no_vision")}`, m.size && `${(m.size / 1e9).toFixed(1)} GB`].filter(Boolean).join(" · ") || undefined,
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
  const local = (neural || []).filter((v) => v.engine && v.engine !== "edge" && v.installed !== false && (gender === "all" || v.gender === gender));
  const online = (neural || []).filter((v) => (!v.engine || v.engine === "edge") && (gender === "all" || v.gender === gender));
  const options = [
    { value: "", label: t("voice_default"), hint: t("voice_default_hint") },
    ...local.map((v) => ({ value: v.id, label: many ? `${v.name} · ${v.locale}` : v.name, group: t("voice_group_local"),
      hint: `${v.engine.replace(/^./, (c) => c.toUpperCase())} · ${t(`vl_q_${v.quality || "standard"}`)}`,
      icon: <GenderIcon g={v.gender} />, badge: t("voice_offline") })),
    ...online.map((v) => ({
      value: `edge:${v.id}`, label: many ? `${v.name} · ${v.locale}` : v.name, group: t("voice_group_neural"),
      icon: <GenderIcon g={v.gender} />, badge: t(v.gender === "female" ? "voice_female" : "voice_male") })),
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
          options={options} searchable ariaLabel={t("voice_voice")} />
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
        <Row stack label={t("fallback_model")} desc={t("fallback_model_desc")}>
          <div className="space-y-3">
            <ModelSelect value={s.fallback_model} allowEmpty onChange={(v) => st.updateSettings({ fallback_model: v })} />
            {s.fallback_model && <ModelSummary id={s.fallback_model} />}
          </div>
        </Row>
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
  const profiles = useStore((x) => x.settings?.model_profiles) || NO_CONF;
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
        {model && <ModelSummary id={model} />}
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
          <Row label={t("prof_temperature")} desc={t("prof_temperature_desc")}>
            <RangeField value={p.temperature} min={0} max={2} step={0.05} auto={t("prof_auto")} autoAt={0.7} format={(v) => v.toFixed(2)}
              onCommit={(v) => set({ temperature: v })} />
          </Row>
          <Row label={t("prof_max_tokens")} desc={t("prof_max_tokens_desc")}>
            <RangeField value={p.max_tokens} min={256} max={Math.max(8192, Math.min(1000000, caps?.context || 131072))} log auto={t("prof_auto")}
              autoAt={4096} format={formatTokens} onCommit={(v) => set({ max_tokens: v })} />
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
            {m.id}<CapIcons m={m} />{m.context && <span className="text-subtle">· {formatTokens(m.context)}</span>}
          </button>
        ))}
      </div>
    </div>
  );
}

// Local server tuning. Ollama: server environment variables (OLLAMA_VULKAN, OLLAMA_FLASH_ATTENTION, KV cache...),
// stored where Ollama reads them and applied with a restart. LM Studio: load options sent with every model load.
// Every option starts on "Auto" (the server's own default).
const RT_ROW = "flex flex-col gap-2 py-2.5 @2xl:flex-row @2xl:items-center @2xl:justify-between";

function RtRow({ label, desc, children }) {
  return (
    <div className={RT_ROW}>
      <div className="min-w-0 @2xl:max-w-[46%]"><div className="text-[12.5px] font-medium">{label}</div>{desc && <div className="mt-0.5 text-[11px] leading-snug text-subtle">{desc}</div>}</div>
      <div className="min-w-0 @2xl:w-[340px] @2xl:shrink-0">{children}</div>
    </div>
  );
}

function LocalRuntime({ id, cfg }) {
  const t = useT();
  const st = useStore.getState();
  const [rt, setRt] = useState(null);
  const [busy, setBusy] = useState("");
  const load = () => api.get(`/api/local/${id}/runtime`).then(setRt).catch(() => setRt({ error: true }));
  useEffect(() => { load(); }, [id]);
  useEffect(() => {
    if (rt?.kind !== "ollama") return;
    const i = setInterval(load, 6000);
    return () => clearInterval(i);
  }, [rt?.kind]);
  if (!rt) return <div className="flex items-center gap-2 text-xs text-muted"><Loader2 size={13} className="animate-spin" />{t("loading")}</div>;
  if (rt.error) return null;
  const put = async (values) => {
    setBusy("save");
    try { setRt(await api.put(`/api/local/${id}/runtime`, { values })); st.notify(t("saved"), "ok"); }
    catch (e) { st.notify(t("save_failed"), "error", e.message); }
    setBusy("");
  };
  const auto = { id: "", label: t("prof_auto") };

  if (rt.kind === "lmstudio") {
    const r = rt.runtime || {};
    const set = (k) => (v) => put({ ...r, [k]: v ?? "" });
    return (
      <div className="rounded-xl border border-line p-3">
        <div className="flex items-center gap-2 text-[13px] font-semibold"><Gauge size={14} className="text-accent" />{t("rt_title")}</div>
        <p className="mt-0.5 text-[11px] leading-snug text-subtle">{t("rt_lms_desc")}</p>
        <div className="mt-1 divide-y divide-line">
          <RtRow label={t("rt_gpu_offload")} desc={t("rt_gpu_offload_desc")}>
            <Segmented value={r.gpu || ""} onChange={set("gpu")} options={[auto, { id: "max", label: t("rt_full") }, { id: "0.75", label: "75%" }, { id: "0.5", label: "50%" }, { id: "0.25", label: "25%" }, { id: "off", label: t("prof_off") }]} />
          </RtRow>
          <RtRow label={t("rt_flash")} desc={t("rt_flash_desc")}>
            <Segmented value={r.flash_attention || ""} onChange={set("flash_attention")} options={[auto, { id: "on", label: t("prof_on") }, { id: "off", label: t("prof_off") }]} />
          </RtRow>
          <RtRow label={t("rt_kv_gpu")} desc={t("rt_kv_gpu_desc")}>
            <Segmented value={r.offload_kv || ""} onChange={set("offload_kv")} options={[auto, { id: "on", label: "GPU" }, { id: "off", label: "RAM" }]} />
          </RtRow>
          <RtRow label={t("rt_batch")} desc={t("rt_batch_desc")}>
            <RangeField value={r.eval_batch} min={32} max={8192} log auto={t("prof_auto")} autoAt={512} onCommit={set("eval_batch")} />
          </RtRow>
          <RtRow label={t("rt_ttl")} desc={t("rt_ttl_desc")}>
            <RangeField value={r.ttl} min={60} max={86400} log auto={t("prof_auto")} autoAt={3600} unit="s" onCommit={set("ttl")} />
          </RtRow>
        </div>
        {!rt.lms && (r.gpu || r.ttl) && <div className="mt-2 flex items-center gap-1.5 text-[11px] text-warn"><AlertTriangle size={12} />{t("rt_lms_missing")}</div>}
      </div>
    );
  }

  const v = rt.vars || {};
  const set = (k) => (val) => put({ [k]: val ?? "" });
  const loaded = rt.loaded || [];
  const win = rt.platform === "win32";
  const cmds = Object.entries(v).filter(([k]) => k !== "OLLAMA_CONTEXT_LENGTH")
    .map(([k, val]) => (val ? (win ? `setx ${k} ${val}` : `export ${k}=${val}`) : null)).filter(Boolean);
  const restart = async () => {
    setBusy("restart");
    const r = await api.post(`/api/local/${id}/restart`).catch((e) => ({ ok: false, error: e.message }));
    setBusy("");
    if (r.ok) { st.notify(t("rt_restarted", { v: r.version || "" }), "ok"); st.loadProviderModels(id, true); }
    else st.notify(t("rt_restart_failed"), "error", t(`rt_${r.error}`) !== `rt_${r.error}` ? t(`rt_${r.error}`) : r.error);
    load();
  };
  return (
    <div className="rounded-xl border border-line p-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="flex items-center gap-2 text-[13px] font-semibold"><Gauge size={14} className="text-accent" />{t("rt_title")}</span>
        <span className={`rounded-md px-1.5 py-px text-[10px] ${rt.running ? "bg-ok/10 text-ok" : "bg-danger/10 text-danger"}`}>
          {rt.running ? t("rt_running", { v: rt.version || "?" }) : rt.installed ? t("rt_stopped") : t("rt_not_installed")}</span>
        {rt.installed && (
          <Button className="ml-auto !px-2.5 !py-1 text-xs" variant={rt.pending?.length ? "primary" : undefined} disabled={!!busy} onClick={restart}>
            {busy === "restart" ? <Loader2 size={13} className="animate-spin" /> : <Power size={13} />}{t(rt.running ? "rt_restart" : "rt_start")}
          </Button>
        )}
      </div>
      <p className="mt-0.5 text-[11px] leading-snug text-subtle">{t("rt_ollama_desc")}</p>
      {rt.pending?.length > 0 && (
        <div className="mt-2 flex items-start gap-1.5 rounded-lg bg-warn/10 px-2.5 py-1.5 text-[11px] text-warn"><AlertTriangle size={12} className="mt-px shrink-0" />{t("rt_pending", { n: rt.pending.length })}</div>
      )}
      {loaded.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {loaded.map((m) => {
            const gpu = m.size ? Math.round((m.vram / m.size) * 100) : 0;
            return (
              <span key={m.name} className="flex items-center gap-1.5 rounded-lg bg-hover px-2 py-0.5 font-mono text-[11px]" title={t("rt_vram_hint")}>
                {m.name}<span className={gpu >= 90 ? "text-ok" : gpu > 0 ? "text-warn" : "text-subtle"}>{gpu ? `GPU ${gpu}%` : "CPU"}</span>
              </span>
            );
          })}
        </div>
      )}
      <div className="mt-1 divide-y divide-line">
        <RtRow label={t("rt_vulkan")} desc={t("rt_vulkan_desc")}>
          <Segmented value={v.OLLAMA_VULKAN || ""} onChange={set("OLLAMA_VULKAN")} options={[auto, { id: "1", label: t("prof_on") }, { id: "0", label: t("prof_off") }]} />
        </RtRow>
        <RtRow label={t("rt_vk_f16")} desc={t("rt_vk_f16_desc")}>
          <Segmented value={v.GGML_VK_DISABLE_F16 || ""} onChange={set("GGML_VK_DISABLE_F16")} options={[auto, { id: "1", label: t("rt_f16_off") }]} />
        </RtRow>
        <RtRow label={t("rt_flash")} desc={t("rt_flash_desc")}>
          <Segmented value={v.OLLAMA_FLASH_ATTENTION || ""} onChange={set("OLLAMA_FLASH_ATTENTION")} options={[auto, { id: "1", label: t("prof_on") }, { id: "0", label: t("prof_off") }]} />
        </RtRow>
        <RtRow label={t("rt_kv")} desc={t("rt_kv_desc")}>
          <Segmented value={v.OLLAMA_KV_CACHE_TYPE || ""} onChange={set("OLLAMA_KV_CACHE_TYPE")}
            options={[auto, { id: "f16", label: t("rt_kv_f16") }, { id: "q8_0", label: t("rt_kv_q8") }, { id: "q4_0", label: t("rt_kv_q4") }]} />
          {v.OLLAMA_KV_CACHE_TYPE && v.OLLAMA_KV_CACHE_TYPE !== "f16" && v.OLLAMA_FLASH_ATTENTION === "0" && (
            <div className="mt-1.5 flex items-center gap-1.5 text-[11px] text-warn"><AlertTriangle size={12} />{t("rt_kv_needs_fa")}</div>
          )}
        </RtRow>
        <RtRow label={t("rt_parallel")} desc={t("rt_parallel_desc")}>
          <RangeField value={v.OLLAMA_NUM_PARALLEL ? +v.OLLAMA_NUM_PARALLEL : null} min={1} max={16} auto={t("rt_parallel_default")} autoAt={1}
            onCommit={(n) => {
              // Every slot has its own context memory: a higher value is confirmed with what it costs.
              if (n && n > 1 && n > (+v.OLLAMA_NUM_PARALLEL || 1) && !window.confirm(t("rt_parallel_confirm", { n }))) return;
              set("OLLAMA_NUM_PARALLEL")(n);
            }} />
          {+v.OLLAMA_NUM_PARALLEL > 1 && (
            <div className="mt-1.5 flex items-start gap-1.5 text-[11px] text-warn"><AlertTriangle size={12} className="mt-px shrink-0" />{t("rt_parallel_warn", { n: v.OLLAMA_NUM_PARALLEL })}</div>
          )}
        </RtRow>
        <RtRow label={t("rt_max_loaded")} desc={t("rt_max_loaded_desc")}>
          <RangeField value={v.OLLAMA_MAX_LOADED_MODELS ? +v.OLLAMA_MAX_LOADED_MODELS : null} min={1} max={8} auto={t("prof_auto")} autoAt={3} onCommit={set("OLLAMA_MAX_LOADED_MODELS")} />
        </RtRow>
      </div>
      {cmds.length > 0 && (
        <details className="mt-2 text-[11px] text-subtle">
          <summary className="cursor-pointer select-none hover:text-fg">{t("rt_commands")}</summary>
          <pre className="mt-1 overflow-x-auto rounded-lg bg-panel p-2 font-mono text-[11px] text-muted">{cmds.join("\n")}</pre>
        </details>
      )}
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
      const r = await api.post(`/api/providers/${id}/test`);
      setTest(r);
      if (r.ok) st.loadProviderModels(id, true).then(() => st.ensureModel()); // the card's old error goes away at once
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
        <Toggle checked={!!cfg.enabled && !!ready} disabled={!ready} onChange={(v) => save({ enabled: v })} />
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
          {!cfg.local && (
            <div className="grid gap-3 rounded-xl border border-line p-3 @2xl:grid-cols-2">
              <div className="min-w-0"><div className="text-xs font-medium">{t("rpm_limit")}</div><div className="mb-2 text-[11px] leading-snug text-subtle">{t("rpm_limit_desc")}</div>
                <RangeField value={cfg.rpm || 0} min={0} max={1000} log zeroLabel="∞" unit={t("unit_per_min")} onCommit={(v) => save({ rpm: v || 0 })} /></div>
              <div className="min-w-0"><div className="text-xs font-medium">{t("concurrency_limit")}</div><div className="mb-2 text-[11px] leading-snug text-subtle">{t("concurrency_limit_desc")}</div>
                <RangeField value={cfg.concurrency || null} min={1} max={32} auto="3" autoAt={3} onCommit={(v) => save({ concurrency: v || 0 })} /></div>
            </div>
          )}
          {cfg.local && <LocalRuntime id={id} cfg={cfg} />}
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-muted">
            {["anthropic", "gemini"].includes(cfg.kind)  /* these APIs are always used streaming */
              ? <span className="flex items-center gap-1.5 text-subtle" title={t("streaming_always_desc")}><Check size={13} className="text-ok" /> {t("streaming_always")}</span>
              : <label className="flex items-center gap-2"><Toggle checked={cfg.streaming !== false} onChange={(v) => save({ streaming: v })} /> {t("streaming")}</label>}
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
          min={40} max={95} unit="%" onCommit={(v) => save({ compress_threshold: v })} />
        <SliderRow label={t("keep_recent")} desc={t("keep_recent_desc")} value={s.context.keep_recent ?? 6}
          min={0} max={20} onCommit={(v) => save({ keep_recent: v })} />
      </Card>
      {ctx && (
        <Card title={t("context_window")} desc={ctx.model}>
          <Row label={t("model_max")} desc={ctx.local ? t("context_local_desc") : t("context_cloud_desc")}><span className="font-mono text-[13px]">{formatTokens(ctx.max)} token</span></Row>
          {ctx.adjustable
            ? <SliderRow label={t("context_size")} desc={t("context_size_hint")} value={ctx.current} min={2048} max={ctx.max} log
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

function BrowserAgentCard() {
  const t = useT();
  const s = useStore((x) => x.settings);
  const st = useStore.getState();
  const [status, setStatus] = useState(null);
  const [busy, setBusy] = useState("");
  const cfg = s.browser || { visible: true, channel: "" };
  const load = () => api.get("/api/browser/status").then(setStatus).catch(() => setStatus(null));
  useEffect(() => { load(); const i = setInterval(load, 4000); return () => clearInterval(i); }, []);
  const act = async (name, fn) => {
    setBusy(name);
    try { await fn(); await load(); st.notify(t(name === "reset" ? "browser_reset_done" : "browser_closed"), "ok"); }
    catch (e) { st.notify(e.message, "error"); }
    setBusy("");
  };
  const mb = status?.profile_bytes || 0;
  return (
    <Card title={t("browser_agent")} desc={t("browser_agent_desc")}>
      <Row tight label={t("browser_visible")} desc={t("browser_visible_desc")}>
        <Toggle checked={cfg.visible !== false} onChange={(v) => st.updateSettings({ browser: { visible: v } })} />
      </Row>
      <Row tight label={t("browser_dismiss")} desc={t("browser_dismiss_desc")}>
        <Toggle checked={cfg.dismiss_popups !== false} onChange={(v) => st.updateSettings({ browser: { dismiss_popups: v } })} />
      </Row>
      <Row label={t("browser_channel")} desc={t("browser_channel_desc")}>
        <Select value={cfg.channel || ""} onChange={(v) => st.updateSettings({ browser: { channel: v } })}
          options={[{ value: "", label: t("browser_channel_bundled") }, { value: "fast", label: t("browser_channel_fast") },
            { value: "chrome", label: "Google Chrome" }, { value: "msedge", label: "Microsoft Edge" }]} />
        {cfg.channel === "fast" && <p className="mt-1.5 text-[11px] leading-snug text-subtle">{t("browser_channel_fast_hint")}</p>}
      </Row>
      <Row tight label={t("browser_status")}>
        {status?.running ? (
          <span className="flex items-center gap-1.5 text-[13px] font-medium text-ok">
            <span className="h-1.5 w-1.5 rounded-full bg-ok" /> {t("browser_running", { n: status.tabs?.length || 0 })}
          </span>
        ) : <span className="text-[13px] text-subtle">{t("browser_not_running")}</span>}
      </Row>
      <Row stack label={t("browser_profile")} desc={t("browser_profile_desc")}>
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2 rounded-xl border border-line bg-bg px-3 py-2.5">
          <div className="flex min-w-0 items-center gap-2">
            <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-hover text-muted"><HardDrive size={15} /></span>
            <div className="min-w-0 leading-tight">
              <div className="text-[13px] font-medium">{mb > 0 ? `${(mb / 1e6).toFixed(1)} MB` : t("browser_profile_empty")}</div>
              <div className="text-[11px] text-subtle">{t("browser_profile_size")}</div>
            </div>
          </div>
          <div className="ml-auto flex flex-wrap items-center gap-2">
            {status?.running && (
              <Button className="whitespace-nowrap" onClick={() => act("close", () => api.post("/api/browser/close"))} disabled={!!busy}>
                {busy === "close" ? <Loader2 size={13} className="animate-spin" /> : <Power size={13} />} {t("browser_close")}
              </Button>
            )}
            <Button variant="danger" className="whitespace-nowrap" onClick={() => act("reset", () => api.post("/api/browser/reset"))} disabled={!!busy || mb === 0}>
              {busy === "reset" ? <Loader2 size={13} className="animate-spin" /> : <Trash2 size={13} />} {t("browser_forget_signins")}
            </Button>
          </div>
        </div>
      </Row>
      <p className="px-4 pb-3.5 text-xs leading-relaxed text-muted @md:px-5">{t("browser_agent_note")}</p>
    </Card>
  );
}

// One search engine / place provider, laid out like a provider card: status dot, key badge, accordion with its key
// and IDs, its own test (only that service, with its real error) and an on/off switch.
const SEARCH_SERVICES = [
  { id: "google", name: "Google Programmable Search", secret: "google_search_key", ph: "AIza…", desc: "google_search_desc",
    fields: [{ field: "google_cx", label: "google_cx", desc: "google_cx_desc", ph: "0123456789abcdef0" }], doc: "https://developers.google.com/custom-search/v1/overview" },
  { id: "yandex", name: "Yandex Search API", secret: "yandex_search_key", ph: "AQVN…", desc: "yandex_search_desc",
    fields: [{ field: "yandex_folder", label: "yandex_folder", desc: "yandex_folder_desc", ph: "b1g…" }], doc: "https://yandex.cloud/en/docs/search-api/" },
  { id: "bing-api", name: "Bing Web Search API", secret: "bing_search_key", ph: "Ocp-Apim-Subscription-Key", desc: "bing_search_desc", doc: "https://learn.microsoft.com/bing/search-apis/" },
  { id: "brave", name: "Brave Search API", secret: "brave_api_key", ph: "BSA…", desc: "brave_desc", doc: "https://api-dashboard.search.brave.com/app/documentation" },
  { id: "tavily", name: "Tavily API", secret: "tavily_api_key", ph: "tvly-…", desc: "tavily_desc", doc: "https://docs.tavily.com" },
  { id: "searxng", name: "SearXNG", desc: "searxng_desc", fields: [{ field: "searxng_url", label: "searxng_url", ph: "http://127.0.0.1:8888" }], doc: "https://docs.searxng.org" },
  { id: "ddgs", test: "ddgs-google", name: "DDGS (Google · Yahoo · Bing · Yandex · Brave)", desc: "ddgs_desc", free: true },
  { id: "duckduckgo", name: "DuckDuckGo", desc: "ddg_desc", free: true },
  { id: "wikipedia", name: "Wikipedia / Wikidata", desc: "wiki_desc", free: true },
];
// Image generation: works without a key (the free tier keeps its small logo); the free token of a registered
// Pollinations account makes pictures logo-free.
// Image services in priority order: a keyed service that is out of quota is skipped; Pollinations is the system's own
// free service and always the last resort.
const MEDIA_SERVICES = [
  { id: "gemini", name: "Google Gemini (Imagen / Flash Image)", secret: "gemini_api_key", ph: "AIza…", desc: "gemini_img_desc",
    doc: "https://ai.google.dev/gemini-api/docs/image-generation" },
  { id: "cloudflare", name: "Cloudflare Workers AI (FLUX)", secret: "cloudflare_api_key", ph: "cfut_…", desc: "cloudflare_img_desc",
    fields: [{ field: "cloudflare_account", label: "cloudflare_account", desc: "cloudflare_account_desc", ph: "ab03a8b1…" }],
    doc: "https://developers.cloudflare.com/workers-ai/models/flux-1-schnell/" },
  { id: "huggingface", name: "Hugging Face (FLUX)", secret: "huggingface_api_key", ph: "hf_…", desc: "hf_img_desc",
    doc: "https://huggingface.co/docs/inference-providers" },
  { id: "together", name: "Together AI (FLUX)", secret: "together_api_key", ph: "…", desc: "together_img_desc", doc: "https://docs.together.ai" },
  { id: "openai", name: "OpenAI (gpt-image-1)", secret: "openai_api_key", ph: "sk-…", desc: "openai_img_desc",
    doc: "https://platform.openai.com/docs/guides/image-generation" },
  { id: "stability", name: "Stability AI", secret: "stability_api_key", ph: "sk-…", desc: "stability_img_desc", doc: "https://platform.stability.ai" },
  { id: "pollinations", name: "Pollinations (FLUX)", secret: "pollinations_token", ph: "token…", desc: "pollinations_desc",
    doc: "https://auth.pollinations.ai", free: true, system: true },
];
// AI video (image-to-video) services in the order they are tried: paid ones with a key first, then the free Hugging
// Face Spaces. Each can be switched off; one at a time is used (the next only when it fails), so they never race.
const VIDEO_SERVICES = [
  { id: "veo", name: "Google Veo (Gemini API)", secret: "gemini_api_key", ph: "AIza…", desc: "veo_desc", doc: "https://ai.google.dev/gemini-api/docs/video" },
  { id: "fal", name: "fal.ai (Wan · Kling · Hailuo · Seedance · Veo)", secret: "fal_api_key", ph: "key_id:secret", desc: "fal_desc", doc: "https://fal.ai/models" },
  { id: "replicate", name: "Replicate (Wan · Kling · Hailuo · Seedance)", secret: "replicate_api_key", ph: "r8_…", desc: "replicate_desc", doc: "https://replicate.com/collections/image-to-video" },
  { id: "runway", name: "Runway (Gen-4 Turbo)", secret: "runway_api_key", ph: "key_…", desc: "runway_desc", doc: "https://docs.dev.runwayml.com" },
  { id: "hf_wan", name: "Wan 2.2 · Hugging Face", desc: "ve_free_desc", free: true, doc: "https://huggingface.co/spaces/zerogpu-aoti/wan2-2-fp8da-aoti-faster" },
  { id: "hf_wan2", name: "Wan 2.2 Lightning · Hugging Face", desc: "ve_free_desc", free: true, doc: "https://huggingface.co/spaces/Saravutw/WAN2.2_I2V_LIGHTNING_4-8step_custom" },
  { id: "hf_svd", name: "AnimateLCM-SVD · Hugging Face", desc: "ve_free_svd_desc", free: true, doc: "https://huggingface.co/spaces/wangfuyun/AnimateLCM-SVD" },
];
// Services whose model the user may pick (only models of that kind: image models for images, video models for video)
const PICKS_MODEL = { media: new Set(["gemini", "cloudflare", "huggingface", "together", "openai", "stability"]), video: new Set(["veo", "fal", "replicate", "runway"]) };

function ModelPick({ kind, section, sid }) {
  const t = useT();
  const [d, setD] = useState(null);
  const chosen = useStore((x) => x.settings?.[section]?.models?.[sid]) || "";
  useEffect(() => { api.get(`/api/media/models/${kind}/${sid}`).then(setD).catch(() => setD({ choices: [] })); }, [kind, sid, chosen]);
  if (!d) return null;
  const list = d.choices || [];
  const cur = chosen || d.current || d.default;
  const opts = list.includes(cur) || !cur ? list : [cur, ...list];
  return (
    <div className="text-xs text-muted">{t(kind === "video" ? "media_model_video" : "media_model_image")}
      <span className="text-subtle"> · {t("media_model_desc", { d: d.default || "-" })}</span>
      <div className="mt-1">
        <Select value={cur || ""} mono searchable={opts.length > 6} ariaLabel={t(kind === "video" ? "media_model_video" : "media_model_image")}
          onChange={(v) => useStore.getState().updateSettings({ [section]: { models: { [sid]: v === d.default ? "" : v } } })}
          options={opts.map((m) => {
            const preview = /preview|exp|beta/i.test(m);
            return { value: m, label: m, group: m === d.default ? t("default") : preview ? t("mp_preview") : t("mp_stable"),
              badge: m === d.default ? t("default") : preview ? "preview" : undefined,
              dot: m === d.default ? "var(--ok)" : preview ? "var(--warn)" : "var(--accent)" };
          }).sort((a, b) => (a.value === d.default ? -1 : b.value === d.default ? 1 : (a.badge === "preview") - (b.badge === "preview")))} />
      </div>
    </div>
  );
}

// Stock photo services: searched first when keyed and switched on; then the free Openverse / Wikimedia Commons.
const STOCK_SERVICES = [
  { id: "pexels", name: "Pexels", secret: "pexels_api_key", ph: "API key", desc: "pexels_desc", doc: "https://www.pexels.com/api/" },
  { id: "pixabay", name: "Pixabay", secret: "pixabay_api_key", ph: "12345678-…", desc: "pixabay_desc", doc: "https://pixabay.com/api/docs/" },
  { id: "unsplash", name: "Unsplash", secret: "unsplash_api_key", ph: "Access Key", desc: "unsplash_desc",
    fields: [{ field: "unsplash_app_id", label: "unsplash_app_id", ph: "1126212", optional: true }], doc: "https://unsplash.com/developers" },
];
const MAP_SERVICES = [
  { id: "google", name: "Google Places API", secret: "google_maps_key", ph: "AIza…", desc: "google_maps_desc", doc: "https://developers.google.com/maps/documentation/places/web-service" },
  { id: "yandex", name: "Yandex Places API", secret: "yandex_maps_key", ph: "…", desc: "yandex_maps_desc", doc: "https://yandex.com/dev/maps/geosearch/" },
  { id: "osm", name: "OpenStreetMap (Nominatim + Overpass)", desc: "osm_desc", free: true },
];

const NO_CONF = {};
function ServiceCard({ svc, section, kind, status, onTested }) {
  const t = useT();
  const st = useStore.getState();
  const has = useStore((x) => (svc.secret ? !!x.settings?.secrets?.[svc.secret] : true));
  const conf = useStore((x) => x.settings?.[section]) || NO_CONF; // a missing section must not be a new {} on every render (endless re-render)
  const off = (conf.disabled || []).includes(svc.id);
  const [open, setOpen] = useState(false);
  const [key, setKey] = useState("");
  const [show, setShow] = useState(false);
  const [vals, setVals] = useState({});
  const [test, setTest] = useState(null);
  const [busy, setBusy] = useState(false);
  const fieldsSet = (svc.fields || []).filter((f) => !f.optional).every((f) => conf[f.field]);
  const ready = svc.free || (has && fieldsSet && (svc.secret || (svc.fields || []).length));
  const dirty = Object.entries(vals).some(([k, v]) => v !== (conf[k] || ""));
  // after saving, the field shows the stored value again (it may later change from the provider card)
  const saveFields = async () => { if (dirty) { await st.updateSettings({ [section]: Object.fromEntries(Object.entries(vals).map(([k, v]) => [k, v.trim()])) }); setVals({}); } };
  const saveKey = async () => { if (!key) return; await st.setSecret(svc.secret, key); setKey(""); onTested?.(); };
  const toggle = (v) => st.updateSettings({ [section]: { disabled: v ? (conf.disabled || []).filter((x) => x !== svc.id) : [...(conf.disabled || []), svc.id] } });
  const runTest = async (real = false) => {
    setBusy(true); setTest(null); setOpen(true);
    try {
      await saveKey(); await saveFields();
      const path = kind === "maps" ? "maps" : kind === "media" ? "media" : kind === "stock" ? "stock" : kind === "video" ? "video" : "web";
      setTest(await api.post(`/api/${path}/test/${svc.test || svc.id}${real === true ? "?real=true" : ""}`, { q: "" }));
    } catch (e) { setTest({ ok: false, error: e.message }); }
    setBusy(false);
    onTested?.();
  };
  const blocked = !!status?.blocked;
  const dot = test ? (test.ok ? "bg-ok" : "bg-danger") : blocked ? "bg-warn" : svc.system ? "bg-ok" : off || !ready ? "bg-active" : "bg-ok";
  return (
    <div className="px-4 py-3 sm:px-5">
      <div className="flex items-center gap-3">
        <span className={`h-2 w-2 shrink-0 rounded-full ${dot}`} />
        <button onClick={() => setOpen(!open)} className="flex min-w-0 flex-1 items-center gap-2 text-left">
          <span className="truncate text-[13px] font-semibold">{svc.name}</span>
          {svc.free ? <span className="hidden shrink-0 rounded-md bg-ok/10 px-1.5 py-px text-[10px] text-ok sm:inline">{t("free_no_key")}</span>
            : has && svc.secret ? <KeyRound size={12} className="shrink-0 text-ok" />
              : !svc.secret ? null : <span className="hidden shrink-0 rounded-md bg-hover px-1.5 py-px text-[10px] text-muted sm:inline">{t("key_missing_short")}</span>}
          <ChevronDown size={14} className={`ml-auto shrink-0 text-subtle transition ${open ? "rotate-180" : ""}`} />
        </button>
        <Button onClick={runTest} disabled={busy || (!ready && !key)} className="!px-2.5 !py-1">{busy ? <Loader2 size={13} className="animate-spin" /> : <Zap size={13} />}<span className="hidden sm:inline">{t("test")}</span></Button>
        <Toggle checked={!!ready && !off} disabled={!ready || svc.system} onChange={toggle} />
      </div>
      {open && (
        <div className="fade-in mt-3 grid gap-3 pl-5">
          <p className="text-xs leading-snug text-muted">{t(svc.desc)}{svc.doc && <> · <a href={svc.doc} target="_blank" rel="noreferrer" className="text-accent hover:underline">{t("docs_link")}</a></>}</p>
          {status && (
            <div className="flex flex-wrap gap-1.5 text-[11px]">
              {svc.system ? <span className="rounded-md bg-hover px-1.5 py-0.5 text-muted">{t("svc_system")}</span>
                : status.active ? <span className="rounded-md bg-ok/10 px-1.5 py-0.5 text-ok">{t("svc_active")}</span>
                  : <span className="rounded-md bg-hover px-1.5 py-0.5 text-muted">{!status.keyed ? t("svc_no_key") : status.blocked ? t("svc_out") : t("svc_off")}</span>}
              {blocked && <span className="rounded-md bg-warn/10 px-1.5 py-0.5 text-warn">{t("svc_until", { time: status.blocked_until })}</span>}
              {status.today > 0 && <span className="rounded-md bg-hover px-1.5 py-0.5 text-muted">{t("svc_today", { n: status.today })}</span>}
              {status.month > 0 && <span className="rounded-md bg-hover px-1.5 py-0.5 text-muted">{t("svc_month", { n: status.month })}</span>}
              {status.window_max && <span className="rounded-md bg-hover px-1.5 py-0.5 text-muted">{t("svc_window", { n: status.window_used, max: status.window_max })}</span>}
              {status.remaining != null && <span className="rounded-md bg-hover px-1.5 py-0.5 text-muted">{t("svc_remaining", { n: status.remaining, max: status.limit ?? "?" })}</span>}
              {status.last_error && !blocked && <span className="max-w-full truncate rounded-md bg-danger/10 px-1.5 py-0.5 text-danger" title={status.last_error}>{serviceError(t, status.last_error).title}</span>}
              {blocked && status.reason && <span className="max-w-full truncate rounded-md bg-warn/10 px-1.5 py-0.5 text-warn" title={status.reason}>{serviceError(t, status.reason).title}</span>}
            </div>
          )}
          {svc.secret && (
            <label className="text-xs text-muted">{t("api_key")}
              <div className="mt-1 flex gap-2">
                <div className="relative flex-1">
                  <input className={`${inputCls} pr-16 font-mono ${key ? "!border-warn" : ""}`} type={show ? "text" : "password"} value={key} autoComplete="off"
                    placeholder={has ? "••••••••••••  " + t("key_saved") : svc.ph} onChange={(e) => setKey(e.target.value)} onKeyDown={(e) => e.key === "Enter" && saveKey()} />
                  <div className="absolute right-1.5 top-1/2 flex -translate-y-1/2 gap-0.5">
                    <button onClick={() => setShow(!show)} className="rounded-md p-1 text-subtle hover:bg-hover">{show ? <EyeOff size={14} /> : <Eye size={14} />}</button>
                    {has && !key && <button title={t("delete")} onClick={() => st.setSecret(svc.secret, null).then(() => st.notify(t("key_removed"), "ok"))} className="rounded-md p-1 text-subtle hover:bg-hover hover:text-danger"><X size={14} /></button>}
                  </div>
                </div>
                {key && <Button variant="primary" onClick={saveKey}><Save size={14} /> {t("save")}</Button>}
              </div>
            </label>
          )}
          {PICKS_MODEL[section]?.has(svc.id) && has && <ModelPick kind={section === "video" ? "video" : "image"} section={section} sid={svc.id} />}
          {kind === "video" && ready && (
            <div className="flex flex-wrap items-center gap-2 text-[11.5px] text-subtle">
              <Button onClick={() => runTest(true)} disabled={busy} className="!px-2.5 !py-1"><Film size={13} />{t("video_real_test")}</Button>
              <span>{t(svc.free ? "video_real_test_free" : "video_real_test_paid")}</span>
            </div>
          )}
          {(svc.fields || []).map((f) => (
            <label key={f.field} className="text-xs text-muted">{t(f.label)}{f.desc && <span className="text-subtle"> · {t(f.desc)}</span>}
              <div className="mt-1 flex gap-2">
                <input className={`${inputCls} font-mono ${(vals[f.field] ?? conf[f.field] ?? "") !== (conf[f.field] || "") ? "!border-warn" : ""}`}
                  value={vals[f.field] ?? conf[f.field] ?? ""} placeholder={f.ph} onChange={(e) => setVals({ ...vals, [f.field]: e.target.value })}
                  onKeyDown={(e) => e.key === "Enter" && saveFields()} />
                {(vals[f.field] ?? conf[f.field] ?? "") !== (conf[f.field] || "") && <Button variant="primary" onClick={saveFields}><Save size={14} /></Button>}
              </div>
            </label>
          ))}
          {test && (
            <div className={`fade-in rounded-xl px-3 py-2 text-xs ${test.ok ? "bg-ok/10 text-ok" : "bg-danger/10 text-danger"}`}>
              {test.ok ? <>✓ {t("service_test_ok", { n: test.count, ms: test.ms })}</> : <><div className="font-medium">✕ {serviceError(t, test.error).title}</div>
                <details className="mt-0.5"><summary className="cursor-pointer text-[11px] opacity-70">{t("svc_details")}</summary><div className="mt-0.5 break-words font-mono text-[11px] opacity-80">{test.error}</div></details></>}
              {test.results?.length > 0 && (
                <div className="mt-1.5 space-y-0.5 text-muted">
                  {test.results.map((r, i) => <div key={i} className="truncate">{r.url ? <a href={r.url} target="_blank" rel="noreferrer" className="hover:underline">{r.title || r.url}</a> : r.title}</div>)}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function Web() {
  const t = useT();
  const [q, setQ] = useState("Audi 2026 modelleri");
  const [res, setRes] = useState(null);
  const [busy, setBusy] = useState(false);
  const [svcs, setSvcs] = useState([]);
  const loadSvcs = () => api.get("/api/services").then((r) => setSvcs(r.services || [])).catch(() => {});
  // keys and switches can change elsewhere (a provider card shares the Cloudflare/Gemini/HF key): the badges follow
  const sig = useStore((x) => JSON.stringify([x.settings?.secrets, x.settings?.media, x.settings?.video, x.settings?.stock,
    x.settings?.providers?.cloudflare?.account_id]));
  useEffect(() => { loadSvcs(); }, [sig]);
  const statusOf = (id) => svcs.find((s) => s.id === id);
  const test = async () => {
    setBusy(true);
    try { setRes(await api.get(`/api/web/search?q=${encodeURIComponent(q)}`)); } catch (e) { setRes({ error: e.message }); }
    setBusy(false);
  };
  return (
    <div className="space-y-4">
      <Card title={<span className="flex items-center gap-2"><Search size={15} />{t("web_engines")} <span className="text-xs font-normal text-subtle">{SEARCH_SERVICES.length}</span></span>} desc={t("web_engines_desc")}>
        {SEARCH_SERVICES.map((svc) => <ServiceCard key={svc.id} svc={svc} section="search" kind="web" />)}
      </Card>
      <Card title={<span className="flex items-center gap-2"><Globe size={15} />{t("maps_services")} <span className="text-xs font-normal text-subtle">{MAP_SERVICES.length}</span></span>} desc={t("maps_services_desc")}>
        {MAP_SERVICES.map((svc) => <ServiceCard key={svc.id} svc={svc} section="maps" kind="maps" />)}
      </Card>
      <Card title={<span className="flex items-center gap-2"><Globe size={15} />{t("image_services")} <span className="text-xs font-normal text-subtle">{MEDIA_SERVICES.length}</span></span>} desc={t("image_services_desc")}>
        {MEDIA_SERVICES.map((svc) => <ServiceCard key={svc.id} svc={svc} section="media" kind="media" status={statusOf(svc.id)} onTested={loadSvcs} />)}
      </Card>
      <Card title={<span className="flex items-center gap-2"><Globe size={15} />{t("stock_services")} <span className="text-xs font-normal text-subtle">{STOCK_SERVICES.length}</span></span>} desc={t("stock_services_desc")}>
        {STOCK_SERVICES.map((svc) => <ServiceCard key={svc.id} svc={svc} section="stock" kind="stock" status={statusOf(svc.id)} onTested={loadSvcs} />)}
      </Card>
      <Card title={<span className="flex items-center gap-2"><Film size={15} />{t("video_services")} <span className="text-xs font-normal text-subtle">{VIDEO_SERVICES.length}</span></span>} desc={t("video_services_desc")}>
        {VIDEO_SERVICES.map((svc) => <ServiceCard key={svc.id} svc={svc} section="video" kind="video" status={statusOf(svc.id)} onTested={loadSvcs} />)}
      </Card>
      <BrowserAgentCard />
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
        <Row tight label={t("parallel_tools")} desc={t("parallel_tools_desc")}>
          <Toggle checked={s.agent.parallel_tools !== false} onChange={agent("parallel_tools")} />
        </Row>
        <Row tight label={t("unlimited_iterations")} desc={t("unlimited_iterations_desc")}>
          <Toggle checked={!!s.agent.unlimited_iterations} onChange={agent("unlimited_iterations")} />
        </Row>
        {!s.agent.unlimited_iterations && <SliderRow label={t("max_iterations")} value={s.agent.max_iterations} min={1} max={300} onCommit={agent("max_iterations")} />}
        <Row tight label={t("unlimited_debug")} desc={t("unlimited_debug_desc")}>
          <Toggle checked={!!s.agent.unlimited_debug} onChange={agent("unlimited_debug")} />
        </Row>
        {!s.agent.unlimited_debug && <SliderRow label={t("max_debug")} value={s.agent.max_debug_attempts} min={0} max={50} onCommit={agent("max_debug_attempts")} />}
        <SliderRow label={t("command_timeout")} value={s.agent.command_timeout} min={10} max={3600} step={10} unit="s" onCommit={agent("command_timeout")} />
        <SliderRow label={t("server_ttl")} desc={t("server_ttl_desc")} value={s.agent.server_ttl_minutes ?? 10} min={0} max={120} unit={t("unit_m")} zeroLabel={t("vs_off")}
          onCommit={agent("server_ttl_minutes")} />
        <Row label={t("split_write")} desc={t("split_write_desc")}>
          <RangeField value={s.agent.split_write_chars ? +s.agent.split_write_chars : null} min={10000} max={500000} step={5000}
            auto={t("split_write_off")} autoAt={0} onCommit={(v) => agent("split_write_chars")(v || 0)} />
        </Row>
      </Card>
      <Card title={t("model_connection")} desc={t("model_connection_desc")}>
        <SliderRow label={t("stream_timeout")} desc={t("stream_timeout_desc")} value={s.agent.stream_timeout ?? 300} min={30} max={1800} step={10} unit="s"
          onCommit={agent("stream_timeout")} />
        <SliderRow label={t("first_token_timeout")} desc={t("first_token_timeout_desc")} value={s.agent.first_token_timeout ?? 300} min={30} max={3600} step={10} unit="s"
          onCommit={agent("first_token_timeout")} />
        <SliderRow label={t("local_stream_timeout")} desc={t("local_stream_timeout_desc")} value={s.agent.local_stream_timeout ?? 0} min={0} max={3600} step={30}
          zeroLabel="∞" unit="s" onCommit={agent("local_stream_timeout")} />
        <SliderRow label={t("provider_retries")} desc={t("provider_retries_desc")} value={s.agent.provider_retries ?? 5} min={1} max={10}
          onCommit={agent("provider_retries")} />
      </Card>
      <Card title={t("prompt_mode")} desc={t("prompt_mode_desc")}>
        <div className="px-5 py-3.5">
          <Segmented value={s.agent.prompt_mode || "auto"} onChange={agent("prompt_mode")}
            options={[{ id: "auto", label: t("prompt_auto") }, { id: "lean", label: t("prompt_lean") }, { id: "full", label: t("prompt_full") }]} />
        </div>
      </Card>
      <Card title={t("guard_card")} desc={t("guard_card_desc")}>
        <Row tight label={t("guard_enabled")} desc={t("guard_enabled_desc")}>
          <Toggle checked={s.local_guard?.enabled !== false} onChange={(v) => st.updateSettings({ local_guard: { enabled: v } })} />
        </Row>
        <Row tight label={t("guard_emergency")} desc={t("guard_emergency_desc")}>
          <Toggle checked={!!s.local_guard?.emergency_unload} onChange={(v) => st.updateSettings({ local_guard: { emergency_unload: v } })} />
        </Row>
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
            <span className="whitespace-nowrap font-mono tabular-nums">{kind === "tokens" ? formatTokens(used) : used}{lim ? ` / ${kind === "tokens" ? formatTokens(lim) : lim}` : ""}</span>
          </div>
          <UsageBar used={used} limit={lim} />
          <RangeField value={lim || null} log min={kind === "tokens" ? 10000 : 10} max={kind === "tokens" ? 1e9 : 100000} auto={t("quota_limit")}
            format={kind === "tokens" ? formatTokens : undefined} onCommit={(n) => onLimit(`${kind}_${name}`, n)} />
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
        {Object.keys(p.models || {}).length > 0 && (
          <div className="overflow-x-auto rounded-xl border border-line">
            <table className="w-full text-[11.5px]">
              <thead><tr className="bg-panel text-left text-subtle">
                <th className="px-2.5 py-1.5 font-medium">{t("model")}</th>
                <th className="px-2.5 py-1.5 text-right font-medium">5 {t("unit_h")} · {t("quota_requests")}</th>
                <th className="px-2.5 py-1.5 text-right font-medium">5 {t("unit_h")} · {t("quota_tokens")}</th>
                <th className="px-2.5 py-1.5 text-right font-medium">{t("quota_week")} · {t("quota_requests")}</th>
                <th className="px-2.5 py-1.5 text-right font-medium">{t("quota_week")} · {t("quota_tokens")}</th>
              </tr></thead>
              <tbody>
                {Object.entries(p.models).sort((a, b) => (b[1].week?.tokens || 0) - (a[1].week?.tokens || 0)).map(([mid, w]) => (
                  <tr key={mid} className="border-t border-line">
                    <td className="max-w-[260px] truncate px-2.5 py-1.5 font-mono" title={mid}>{mid.split(":").slice(1).join(":")}</td>
                    <td className="px-2.5 py-1.5 text-right tabular-nums">{w["5h"]?.requests || 0}</td>
                    <td className="px-2.5 py-1.5 text-right tabular-nums">{formatTokens(w["5h"]?.tokens || 0)}</td>
                    <td className="px-2.5 py-1.5 text-right tabular-nums">{w.week?.requests || 0}</td>
                    <td className="px-2.5 py-1.5 text-right tabular-nums">{formatTokens(w.week?.tokens || 0)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {p.account && (
          <div className="flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-muted">
            <span className="font-medium">{t("quota_account")}:</span>
            {p.account.balance != null && <span>{t("quota_balance")}: {p.account.balance}</span>}
            {p.account.credits_left != null && <span>{t("quota_credits_left")}: {Number(p.account.credits_left).toFixed(2)}</span>}
            {p.account.credits_used != null && <span>{t("quota_credits_used")}: {Number(p.account.credits_used).toFixed(4)}</span>}
            {p.account.free_tier != null && <span>{p.account.free_tier ? t("quota_free_tier") : t("quota_paid_tier")}</span>}
            {p.account.rate?.requests && <span>{t("quota_rate")}: {p.account.rate.requests}/{p.account.rate.interval}</span>}
            {p.account.remaining_cr != null && <span>{t("quota_credits_left")}: {p.account.remaining_cr}</span>}
            {p.account.level != null && <span>{t("quota_level")}: {p.account.level}</span>}
            {p.account.available === false && <span className="text-danger">{t("quota_no_balance")}</span>}
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
  // Try again now: clears the wait and sends a one-token test request; the answer says if it works again.
  const clear = async (key) => {
    const st = useStore.getState();
    const id = st.notify(t("quota_probing"), "busy");
    try {
      const r = await api.post(`/api/usage/clear?model=${encodeURIComponent(key)}`);
      st.dismiss(id);
      if (r.ok) st.notify(t("quota_probe_ok", { model: r.model || key, ms: r.ms ?? "" }), "ok");
      else st.notify(t("quota_probe_failed", { model: r.model || key }), "error", r.error);
    } catch (e) { st.dismiss(id); st.notify(e.message, "error"); }
    load();
  };
  const localIds = new Set(Object.entries(s.providers || {}).filter(([, c]) => c.local).map(([id]) => id));
  return (
    <div className="space-y-4">
      <Card title={t("mm_title")} desc={t("mm_desc")}>
        <Row tight label={t("enabled")}><Toggle checked={!!mm.enabled} onChange={(v) => save({ enabled: v })} /></Row>
        <Row tight label={t("mm_auto_switch")} desc={t("mm_auto_switch_desc")}><Toggle checked={mm.auto_switch !== false} onChange={(v) => save({ auto_switch: v })} /></Row>
        <Row tight label={t("mm_delegate")} desc={t("mm_delegate_desc")}><Toggle checked={mm.delegate !== false} onChange={(v) => save({ delegate: v })} /></Row>
        <Row tight label={t("mm_prefer_fast")} desc={t("mm_prefer_fast_desc")}><Toggle checked={mm.prefer_fast !== false} onChange={(v) => save({ prefer_fast: v })} /></Row>
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

      <ModelStats />
    </div>
  );
}

// Measured per-model record (tasks, failures, first-token wait, turn time, prompt reading speed).
const fmtMs = (v) => (v == null ? "–" : v >= 10000 ? `${Math.round(v / 1000)} s` : v >= 1000 ? `${(v / 1000).toFixed(1)} s` : `${Math.round(v)} ms`);
function ModelStats() {
  const t = useT();
  const [data, setData] = useState(null);
  const load = () => api.get("/api/models/stats").then((r) => setData(r.models || {})).catch(() => setData({}));
  useEffect(() => { load(); }, []);
  const rows = Object.entries(data || {}).sort((a, b) => (b[1].tasks || 0) - (a[1].tasks || 0));
  const reset = async () => { await api.del("/api/models/stats"); load(); };
  return (
    <Card title={t("ms_title")} desc={t("ms_desc")}
      action={<div className="flex gap-1">
        <button onClick={load} title={t("refresh")} className="rounded-lg p-1.5 text-muted hover:bg-hover"><RefreshCw size={15} /></button>
        {rows.length > 0 && <button onClick={reset} title={t("ms_reset")} className="rounded-lg p-1.5 text-muted hover:bg-hover hover:text-danger"><Trash2 size={15} /></button>}
      </div>}>
      {rows.length === 0 ? <div className="px-5 py-6 text-center text-[13px] text-muted">{t("ms_empty")}</div> : (
        <div className="overflow-x-auto px-5 py-3">
          <table className="w-full text-[12.5px]">
            <thead><tr className="text-left text-subtle">
              <th className="py-1.5 pr-3 font-medium">{t("ms_model")}</th><th className="px-2 font-medium">{t("ms_tasks")}</th>
              <th className="px-2 font-medium">{t("ms_fail")}</th><th className="px-2 font-medium">{t("ms_first")}</th>
              <th className="px-2 font-medium">{t("ms_turn")}</th><th className="px-2 font-medium">{t("ms_read")}</th>
            </tr></thead>
            <tbody>{rows.map(([m, v]) => (
              <tr key={m} className="border-t border-line" title={v.last_error ? `${t("ms_last_error")}: ${v.last_error}` : ""}>
                <td className="max-w-[260px] truncate py-1.5 pr-3 font-mono text-[12px]">{m}</td>
                <td className="px-2 tabular-nums">{v.tasks || 0}</td>
                <td className={`px-2 tabular-nums ${v.fail_pct >= 40 ? "text-danger" : v.fail_pct >= 15 ? "text-warn" : "text-ok"}`}>{v.tasks ? t("ms_pct", { n: v.fail_pct }) : "–"}</td>
                <td className="px-2 tabular-nums">{fmtMs(v.first_ms)}</td>
                <td className="px-2 tabular-nums">{fmtMs(v.turn_ms)}</td>
                <td className="px-2 tabular-nums">{fmtMs(v.read_ms_per_1k)}</td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      )}
    </Card>
  );
}

// MCP servers: external tool servers (GitHub, databases, files...) the model can call through the mcp tool.
const MCP_EMPTY = { id: "", name: "", transport: "stdio", command: "", args: "", url: "", env: "", headers: "", enabled: true };
const lines = (obj) => Object.entries(obj || {}).map(([k, v]) => `${k}=${v}`).join("\n");
const parseLines = (text) => Object.fromEntries(text.split("\n").map((l) => l.trim()).filter((l) => l.includes("="))
  .map((l) => [l.slice(0, l.indexOf("=")).trim(), l.slice(l.indexOf("=") + 1).trim()]));
const splitArgs = (s) => (s.match(/"[^"]*"|\S+/g) || []).map((a) => a.replace(/^"|"$/g, ""));
// Ready-made servers come from the backend catalog (/api/mcp-catalog): public ones work at once, "oauth" ones show
// their sign-in button after they are added, "header" ones open the form with the token line to fill in.

// a JSON result indented (most MCP tools answer with one JSON line), other text as it is
const pretty = (text) => {
  const s = String(text || "").trim();
  if (!/^[[{]/.test(s) || s.length > 400000) return s;
  try { return JSON.stringify(JSON.parse(s), null, 2); } catch { return s; }
};

// Run an MCP tool by hand: a field per argument of its input schema (objects / arrays as JSON), the raw result below.
// The same call the model makes with the mcp tool; "Use in chat" puts the tool as a chip into the composer.
function McpTry({ sid, server, init, onClose }) {
  const t = useT();
  const tools = server.tools || [];
  const [name, setName] = useState(init || tools[0]?.name || "");
  const tool = tools.find((x) => x.name === name) || {};
  const schema = tool.input_schema || {};
  const [vals, setVals] = useState({});
  const [res, setRes] = useState(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => { setVals({}); setRes(null); }, [name]);
  const run = async () => {
    setBusy(true); setRes(null);
    try { setRes(await api.post(`/api/mcp/${sid}/call`, { tool: name, arguments: argsFromVals(schema, vals) })); }
    catch (e) { setRes({ ok: false, text: e.message }); }
    finally { setBusy(false); }
  };
  const toChat = () => { // the composer takes it as an MCP tool chip, with the values filled in here
    useStore.setState({ mcpTool: { tool: `${sid}/${name}`, vals } });
    useStore.getState().setView("chat");
    onClose();
  };
  const missing = missingArgs(schema, vals).length > 0;
  return (
    <Modal title={t("mcp_try_title", { name: server.name || sid })} onClose={onClose} width="max-w-2xl"
      footer={<>
        <Button onClick={toChat}><MessageSquarePlus size={14} /> {t("mcp_use_in_chat")}</Button>
        <Button variant="primary" disabled={busy || !name || missing} onClick={run}>
          {busy ? <Loader2 size={14} className="animate-spin" /> : <Play size={14} />} {t("mcp_run")}</Button></>}>
      <div className="space-y-3 text-[13px]">
        <Select value={name} onChange={setName} options={tools.map((x) => ({ id: x.name, label: x.name }))} />
        {tool.description && <p className="text-xs leading-snug text-muted">{tool.description}</p>}
        <McpArgFields schema={schema} vals={vals} onChange={setVals} />
        {res && (
          <div className={`rounded-xl border px-3 py-2 ${res.ok ? "border-line" : "border-danger/40 bg-danger/5"}`}>
            <div className={`mb-1 text-[11.5px] ${res.ok ? "text-ok" : "text-danger"}`}>{res.ok ? t("mcp_result_ok") : t("mcp_result_err")}{res.ms != null ? ` · ${(res.ms / 1000).toFixed(1)} ${t("unit_s")}` : ""}</div>
            <pre className="max-h-80 overflow-auto whitespace-pre-wrap break-words font-mono text-[12px] leading-relaxed">{pretty(res.text)}</pre>
          </div>
        )}
      </div>
    </Modal>
  );
}

// Find a server in the official MCP registry (+ npm, GitHub): the same search the model's mcp_search tool makes.
function McpFind({ installed, onInstall }) {
  const t = useT();
  const [q, setQ] = useState("");
  const [rows, setRows] = useState(null);
  const [busy, setBusy] = useState(false);
  const search = async (e) => {
    e?.preventDefault();
    if (!q.trim()) return;
    setBusy(true);
    try { setRows((await api.get(`/api/mcp-registry?q=${encodeURIComponent(q.trim())}`)).results || []); }
    catch (err) { setRows([]); useStore.getState().notify(t("mcp_find_failed"), "error", err.message); }
    finally { setBusy(false); }
  };
  return (
    <Card title={t("mcp_find")} desc={t("mcp_find_desc")}>
      <form onSubmit={search} className="flex gap-2 px-4 py-3.5 @md:px-5">
        <div className="relative flex-1">
          <Search size={14} className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-subtle" />
          <input className={`${inputCls} pl-8`} value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("mcp_find_ph")} />
        </div>
        <Button variant="primary" disabled={busy || !q.trim()}>{busy ? <Loader2 size={14} className="animate-spin" /> : <Search size={14} />} {t("mcp_find_btn")}</Button>
      </form>
      {rows && <div className="space-y-2 px-4 py-3.5 @md:px-5">
        {rows.length === 0 && <div className="py-4 text-center text-[13px] text-muted">{t("mcp_find_none")}</div>}
        {(rows || []).map((r, i) => {
          const runnable = !!(r.command || r.url);
          return (
            <div key={i} className="flex items-start gap-2.5 rounded-xl border border-line px-3 py-2.5">
              <Plug size={15} className="mt-0.5 shrink-0 text-muted" />
              <span className="min-w-0 flex-1">
                <span className="flex flex-wrap items-center gap-1.5 text-[13px] font-medium"><span className="break-all">{r.name}</span>
                  <span className="rounded bg-hover px-1 font-mono text-[10px] font-normal text-muted">{r.source}</span>
                  {r.stars ? <span className="text-[10.5px] font-normal text-subtle">★ {r.stars}</span> : null}</span>
                {r.description && <span className="mt-0.5 block text-xs leading-snug text-muted">{r.description}</span>}
                <span className="mt-0.5 block truncate font-mono text-[11px] text-subtle">{r.url || [r.command, ...(r.args || [])].join(" ") || r.homepage}</span>
                {(r.env?.length > 0 || r.auth) && <span className="mt-0.5 block text-[11px] text-warn">{[r.env?.length ? `env: ${r.env.join(", ")}` : "", r.auth].filter(Boolean).join(" · ")}</span>}
              </span>
              {runnable ? (
                <button title={t("add")} disabled={installed.has(r.name)} onClick={() => onInstall(r)} className="rounded-lg p-1 text-subtle hover:bg-hover hover:text-accent disabled:opacity-40"><Plus size={14} /></button>
              ) : r.homepage ? (
                <a href={r.homepage} target="_blank" rel="noreferrer" className="rounded-lg p-1 text-subtle hover:bg-hover hover:text-accent"><Globe size={14} /></a>
              ) : null}
            </div>
          );
        })}
      </div>}
    </Card>
  );
}

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
        <p className="text-xs leading-snug text-muted">{t(f.transport === "stdio" ? "mcp_cmd_note" : "mcp_http_note")}</p>
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
    try { await api.del(`/api/mcp/${id}`); } catch (e) { useStore.getState().notify(t("mcp_save_failed"), "error", e.message); }
    load();
  };
  // Sign-in: the service's own page opens in a new tab; this list refreshes until the server runs (3 minutes at most).
  const signIn = async (id) => {
    setBusy(id);
    try {
      const { url } = await api.post(`/api/mcp/${id}/oauth`);
      window.open(url, "_blank", "noopener");
      for (let i = 0; i < 60; i++) {
        await new Promise((r) => setTimeout(r, 3000));
        const all = await api.get("/api/mcp");
        setServers(all);
        if (all?.[id]?.running) break;
      }
    } catch (e) { useStore.getState().notify(t("mcp_signin_failed"), "error", e.message); }
    finally { setBusy(""); }
  };
  const signOut = async (id) => { setBusy(id); try { await api.del(`/api/mcp/${id}/oauth`); } finally { setBusy(""); load(); } };
  // One click adds a ready-made server switched on (public ones need nothing else; sign-in ones show their button)
  const [cat, setCat] = useState({ categories: [], servers: [] });
  useEffect(() => { api.get("/api/mcp-catalog").then(setCat).catch(() => {}); }, []);
  const [catQ, setCatQ] = useState("");
  const [catSel, setCatSel] = useState("");
  const [trying, setTrying] = useState(null); // {sid, tool}
  // a ready-made server: added at once, or (token header) the form opens with the line to fill in
  const addPreset = async (p) => {
    if (p.auth === "header") {
      setForm({ ...MCP_EMPTY, name: p.id, transport: p.transport, url: p.url || "", command: p.command || "", args: p.args || "", headers: p.hint || "" });
      return;
    }
    setBusy(p.id);
    try {
      await api.put(`/api/mcp/${p.id}`, { name: p.label, transport: p.transport, command: p.command || "", url: p.url || "",
        args: splitArgs(p.args || ""), env: {}, headers: {}, enabled: true });
    } catch (e) { useStore.getState().notify(t("mcp_save_failed"), "error", e.message); }
    finally { setBusy(""); load(); }
  };
  // a registry / npm result: added at once when it needs no keys, else the form opens with its env names to fill in
  const addFound = async (r) => {
    const id = r.name.toLowerCase().split("/").pop().replace(/[^a-z0-9_-]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 32) || "mcp";
    const env = (r.env || []).map((e) => `${e.split(" ")[0]}=`).join("\n");
    const init = { ...MCP_EMPTY, name: id, transport: r.url ? "http" : "stdio", url: r.url || "", command: r.command || "", args: (r.args || []).join(" "), env };
    if (env || (r.auth && !/^sign-in|none/.test(r.auth) && r.url)) { setForm(init); return; }
    setBusy(id);
    try {
      await api.put(`/api/mcp/${id}`, { name: r.name.slice(0, 60), transport: init.transport, command: init.command, url: init.url,
        args: r.args || [], env: {}, headers: {}, enabled: true });
      setView("mine");
    } catch (e) { useStore.getState().notify(t("mcp_save_failed"), "error", e.message); }
    finally { setBusy(""); load(); }
  };
  const presetIds = new Set(cat.servers.map((p) => p.id));
  const [view, setView] = useState("presets");
  const all = Object.entries(servers || {});
  const mine = all.filter(([id]) => !presetIds.has(id));
  const list = view === "presets" ? all.filter(([id]) => presetIds.has(id)) : view === "mine" ? mine : [];
  const ql = catQ.trim().toLowerCase();
  const shown = cat.servers.filter((p) => (!catSel || p.category === catSel)
    && (!ql || `${p.label} ${p.id} ${t(p.note)}`.toLowerCase().includes(ql)));
  return (
    <div className="space-y-4">
      <Segmented value={view} onChange={setView}
        options={[{ id: "presets", label: `${t("mcp_presets")} · ${cat.servers.length}` }, { id: "mine", label: `${t("mcp_mine")} · ${mine.length}` },
          { id: "find", label: t("mcp_find") }]} />
      {view === "find" && <McpFind installed={new Set(all.map(([id, s]) => s.name || id))} onInstall={addFound} />}
      {view === "presets" && (
        <Card title={t("mcp_presets")} desc={t("mcp_presets_desc")}>
          <div className="flex flex-wrap items-center gap-1.5 px-4 py-3.5 @md:px-5">
            <div className="relative w-full @md:w-56">
              <Search size={14} className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-subtle" />
              <input className={`${inputCls} !py-1.5 pl-8`} value={catQ} onChange={(e) => setCatQ(e.target.value)} placeholder={t("mcp_cat_search")} />
            </div>
            {["", ...cat.categories].map((c) => (
              <button key={c || "all"} onClick={() => setCatSel(c)}
                className={`rounded-lg px-2 py-1 text-xs ${catSel === c ? "bg-accent-soft font-medium text-accent" : "text-muted hover:bg-hover"}`}>
                {t(c ? `mcp_cat_${c}` : "mcp_cat_all")}</button>
            ))}
          </div>
          <div className="grid gap-2 px-4 py-3.5 @md:grid-cols-2 @md:px-5">
            {shown.length === 0 && <div className="py-3 text-center text-[13px] text-muted @md:col-span-2">{t("mcp_find_none")}</div>}
            {shown.map((p) => {
              const s = servers?.[p.id];
              return (
                <div key={p.id} className="flex items-start gap-2.5 rounded-xl border border-line px-3 py-2.5">
                  <Plug size={15} className={`mt-0.5 shrink-0 ${s?.running ? "text-ok" : s?.error ? "text-danger" : "text-muted"}`} />
                  <span className="min-w-0 flex-1">
                    <span className="flex items-center gap-1.5 text-[13px] font-medium">{p.label}
                      <span className="rounded bg-hover px-1 font-mono text-[10px] font-normal text-muted">{p.transport}</span>
                      {p.auth ? <span className="rounded bg-warn/10 px-1 text-[10px] font-normal text-warn">{t(p.auth === "header" ? "mcp_p_token" : "mcp_p_auth")}</span>
                        : <span className="rounded bg-ok/10 px-1 text-[10px] font-normal text-ok">{t("mcp_p_public")}</span>}</span>
                    <span className="mt-0.5 block text-xs leading-snug text-muted">{t(p.note)}</span>
                    {s && <span className={`mt-0.5 block text-[11px] ${s.running ? "text-ok" : s.error ? "text-danger" : "text-subtle"}`}>
                      {busy === p.id ? t("mcp_starting") : s.running ? t("mcp_running", { n: s.tools.length }) : s.enabled === false ? t("mcp_disabled") : s.error ? t("mcp_failed") : t("mcp_stopped")}</span>}
                  </span>
                  {s ? (
                    <span className="flex shrink-0 items-center gap-1">
                      <Toggle checked={s.enabled !== false} onChange={(v) => toggle(p.id, s, v)} />
                      <button title={t("mcp_remove")} onClick={() => remove(p.id)} className="rounded-lg p-1 text-muted hover:bg-hover hover:text-danger"><Trash2 size={13} /></button>
                    </span>
                  ) : (
                    <button title={t("add")} disabled={busy === p.id} onClick={() => addPreset(p)} className="rounded-lg p-1 text-subtle hover:bg-hover hover:text-accent">
                      {busy === p.id ? <Loader2 size={14} className="animate-spin" /> : <Plus size={14} />}</button>
                  )}
                </div>
              );
            })}
          </div>
        </Card>
      )}
      {(view === "mine" || list.length > 0) && <Card title={view === "presets" ? t("mcp_title") : t("mcp_mine")} desc={view === "presets" ? t("mcp_desc") : t("mcp_mine_desc")}
        action={view === "mine" && <Button className="text-xs" onClick={() => setForm({ ...MCP_EMPTY })}><Plus size={14} /> {t("add")}</Button>}>
        {servers == null && <div className="grid h-20 place-items-center"><Loader2 size={16} className="animate-spin text-accent" /></div>}
        {servers && list.length === 0 && <div className="px-5 py-6 text-center text-[13px] text-muted">{t(view === "presets" ? "mcp_empty" : "mcp_mine_empty")}</div>}
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
            {s.transport === "http" && (s.needs_auth || s.signed_in) && (
              <div className="flex flex-wrap items-center gap-2">
                {s.needs_auth && <Button variant="primary" className="!py-1 text-xs" disabled={busy === id} onClick={() => signIn(id)}>
                  {busy === id ? <Loader2 size={13} className="animate-spin" /> : <LogIn size={13} />} {t("mcp_signin")}</Button>}
                {s.signed_in && <span className="rounded-md bg-ok/10 px-1.5 py-0.5 text-[11px] text-ok">{t("mcp_signed_in")}</span>}
                {s.signed_in && <button onClick={() => signOut(id)} className="flex items-center gap-1 rounded-lg px-1.5 py-0.5 text-[11px] text-muted hover:bg-hover"><LogOut size={12} /> {t("mcp_signout")}</button>}
                {s.needs_auth && <span className="text-[11px] text-muted">{t("mcp_signin_hint")}</span>}
              </div>
            )}
            {s.error && !s.needs_auth && <div className="rounded-lg bg-danger/10 px-2.5 py-1.5 text-xs text-danger">{s.error}</div>}
            {s.tools?.length > 0 && (
              <div className="flex flex-wrap gap-1">
                {s.tools.map((tl) => <button key={tl.name} title={`${tl.description || tl.name}\n\n${t("mcp_try_hint")}`} onClick={() => setTrying({ sid: id, tool: tl.name })}
                  className={`rounded-md px-1.5 py-0.5 font-mono text-[11px] hover:ring-1 hover:ring-accent ${tl.read_only ? "bg-ok/10 text-ok" : "bg-hover text-muted"}`}>{tl.name}</button>)}
                <button onClick={() => setTrying({ sid: id, tool: s.tools[0].name })} className="inline-flex items-center gap-1 rounded-md bg-accent-soft px-1.5 py-0.5 text-[11px] font-medium text-accent hover:opacity-90"><Play size={11} /> {t("mcp_try")}</button>
              </div>
            )}
          </div>
        ))}
      </Card>}
      <div className="flex gap-2 px-1 text-xs leading-snug text-muted"><Info size={14} className="mt-0.5 shrink-0" />{t("mcp_safety")}</div>
      {form && <McpForm init={form} onClose={() => setForm(null)} onSaved={() => { setForm(null); load(); }} />}
      {trying && servers?.[trying.sid] && <McpTry sid={trying.sid} server={servers[trying.sid]} init={trying.tool} onClose={() => setTrying(null)} />}
    </div>
  );
}



const PANES = { general: General, models: Models, multi: MultiModel, providers: Providers, context: Context, web: Web, voices: VoicesPane, mcp: McpServers, security: Security, languages: LanguagesTab };

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
