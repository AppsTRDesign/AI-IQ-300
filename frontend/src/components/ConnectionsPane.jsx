import { useEffect, useRef, useState } from "react";
import {
  AlertTriangle, Check, CheckCircle2, ChevronDown, Copy, Download, ExternalLink, FolderGit2, GitBranch, KeyRound,
  Loader2, Lock, LogIn, LogOut, Mail, RefreshCw, Search, Server,
} from "lucide-react";
import { useStore, useT } from "../lib/store";
import { api } from "../lib/api";
import { Button, Toggle, inputCls } from "./ui";

// Settings > Connections: one click connects GitHub, Google and Microsoft 365. Each connection sets up its MCP
// server(s) by itself; GitHub also imports repositories as projects and keeps them up to date.

const Box = ({ icon: Icon, title, desc, status, children }) => (
  <section className="rounded-2xl border border-line bg-elev">
    <div className="flex flex-wrap items-start gap-3 border-b border-line px-4 py-3.5 @md:px-5">
      <span className="mt-0.5 grid h-8 w-8 shrink-0 place-items-center rounded-xl bg-hover"><Icon size={16} /></span>
      <div className="min-w-0 flex-1">
        <h3 className="text-[14px] font-semibold">{title}</h3>
        <p className="mt-0.5 text-xs leading-snug text-muted">{desc}</p>
      </div>
      {status}
    </div>
    <div className="space-y-3 px-4 py-3.5 @md:px-5">{children}</div>
  </section>
);

const Badge = ({ ok, children }) => (
  <span className={`flex shrink-0 items-center gap-1 rounded-lg px-2 py-1 text-[11.5px] ${ok ? "bg-ok/10 text-ok" : "bg-hover text-muted"}`}>
    {ok ? <CheckCircle2 size={12} /> : null}{children}
  </span>
);

const Err = ({ children }) => children ? (
  <div className="flex items-start gap-1.5 rounded-lg bg-danger/10 px-2.5 py-1.5 text-[12px] text-danger">
    <AlertTriangle size={13} className="mt-0.5 shrink-0" /><span className="min-w-0 break-words">{children}</span>
  </div>
) : null;

const openUrl = (u) => window.open(u, "_blank", "noopener");

// ---------------------------------------------------------------------------------------------------------- GitHub
function GitHubCard({ s, reload }) {
  const t = useT();
  const st = useStore.getState();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [manual, setManual] = useState(false);
  const [token, setToken] = useState("");
  const connect = async (tok) => {
    setBusy(true); setErr("");
    try {
      await api.post("/api/connections/github", tok ? { token: tok } : {});
      setToken(""); setManual(false); await reload();
      st.notify(t("conn_connected", { name: "GitHub" }), "ok");
    } catch (e) {
      setErr(e.message);
      if (!tok) { setManual(true); openUrl(s.token_page); }
    }
    setBusy(false);
  };
  const off = async () => {
    if (!(await st.confirm({ title: t("conn_disconnect"), message: t("conn_disconnect_q", { name: "GitHub" }), confirmLabel: t("conn_disconnect"), danger: true }))) return;
    await api.del("/api/connections/github"); reload();
  };
  return (
    <Box icon={GitBranch} title="GitHub" desc={t("conn_github_desc")}
      status={s.connected ? <Badge ok>{s.login}</Badge> : <Badge>{t("conn_not_connected")}</Badge>}>
      {!s.connected ? (
        <>
          <div className="flex flex-wrap items-center gap-2">
            <Button variant="primary" onClick={() => connect()} disabled={busy}>
              {busy ? <Loader2 size={14} className="animate-spin" /> : <LogIn size={14} />}{t("conn_github_connect")}
            </Button>
            <span className="text-[11.5px] text-subtle">{busy ? t("conn_github_waiting") : t("conn_github_how")}</span>
          </div>
          <Err>{err}</Err>
          {(manual || !s.git) && (
            <div className="space-y-2 rounded-xl border border-line p-3">
              <div className="text-[12.5px] font-medium">{t("conn_github_manual")}</div>
              <p className="text-[11.5px] text-muted">{t("conn_github_manual_desc")}</p>
              <div className="flex flex-wrap gap-2">
                <input type="password" className={`${inputCls} min-w-0 flex-1 font-mono`} placeholder="ghp_… / github_pat_…"
                  value={token} onChange={(e) => setToken(e.target.value)} />
                <Button onClick={() => connect(token)} disabled={!token.trim() || busy}><KeyRound size={14} />{t("conn_save_connect")}</Button>
                <Button variant="ghost" onClick={() => openUrl(s.token_page)}><ExternalLink size={14} />{t("conn_github_token_page")}</Button>
              </div>
            </div>
          )}
          {!s.git && <p className="text-[11.5px] text-warn">{t("conn_git_missing")}</p>}
        </>
      ) : (
        <>
          <div className="flex flex-wrap items-center gap-2 text-[12.5px]">
            {s.avatar && <img src={s.avatar} alt="" className="h-6 w-6 rounded-full" />}
            <span className="font-medium">{s.name || s.login}</span>
            <span className="text-subtle">@{s.login}</span>
            <span className="rounded-md bg-hover px-1.5 py-px text-[10.5px] text-muted">{t(`conn_method_${s.method}`)}</span>
            <span className="flex items-center gap-1 rounded-md bg-hover px-1.5 py-px text-[10.5px] text-muted"><Server size={11} />MCP: github</span>
            <Button variant="danger" className="ml-auto !px-2.5 !py-1" onClick={off}><LogOut size={13} />{t("conn_disconnect")}</Button>
          </div>
          <GitHubProjects />
          <GitHubRepos />
        </>
      )}
    </Box>
  );
}

function GitHubRepos() {
  const t = useT();
  const st = useStore.getState();
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [list, setList] = useState(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState("");
  const load = () => { setErr(""); setList(null); api.get(`/api/connections/github/repos?q=${encodeURIComponent(q)}`).then(setList).catch((e) => { setErr(e.message); setList([]); }); };
  useEffect(() => { if (open) load(); }, [open]);
  const importRepo = async (r) => {
    setBusy(r.full_name); setErr("");
    try {
      const p = await api.post("/api/connections/github/import", { full_name: r.full_name });
      useStore.setState({ projects: await api.get("/api/projects") });
      st.notify(t(p.existing ? "conn_repo_exists" : "conn_repo_imported", { name: r.full_name }), "ok");
      window.dispatchEvent(new Event("aiiq-git-projects"));
      load();
    } catch (e) { setErr(e.message); }
    setBusy("");
  };
  return (
    <div className="rounded-xl border border-line">
      <button onClick={() => setOpen(!open)} className="flex w-full items-center gap-2 px-3 py-2.5 text-left text-[13px] font-medium">
        <Download size={14} className="text-accent" />{t("conn_import_title")}
        <ChevronDown size={14} className={`ml-auto text-subtle transition ${open ? "rotate-180" : ""}`} />
      </button>
      {open && (
        <div className="space-y-2 border-t border-line p-3">
          <div className="flex gap-2">
            <div className="relative min-w-0 flex-1">
              <Search size={13} className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-subtle" />
              <input className={`${inputCls} !pl-8`} placeholder={t("conn_repo_search")} value={q}
                onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => e.key === "Enter" && load()} />
            </div>
            <Button onClick={load}><RefreshCw size={13} /></Button>
          </div>
          <Err>{err}</Err>
          {!list ? <div className="flex items-center gap-2 text-xs text-muted"><Loader2 size={13} className="animate-spin" />{t("loading")}</div> : (
            <div className="max-h-80 divide-y divide-line overflow-y-auto rounded-lg border border-line">
              {list.length === 0 && <div className="px-3 py-2 text-xs text-muted">{t("conn_repo_none")}</div>}
              {list.map((r) => (
                <div key={r.full_name} className="flex items-center gap-2 px-3 py-2">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-1.5 text-[12.5px] font-medium">
                      {r.private && <Lock size={11} className="shrink-0 text-subtle" />}<span className="truncate">{r.full_name}</span>
                      {r.language && <span className="shrink-0 text-[10.5px] font-normal text-subtle">{r.language}</span>}
                    </div>
                    {r.description && <div className="truncate text-[11px] text-subtle">{r.description}</div>}
                  </div>
                  {r.project_id ? <Badge ok>{t("conn_repo_in_app")}</Badge> : (
                    <Button className="!px-2.5 !py-1" onClick={() => importRepo(r)} disabled={!!busy}>
                      {busy === r.full_name ? <Loader2 size={13} className="animate-spin" /> : <Download size={13} />}{t("conn_repo_import")}
                    </Button>
                  )}
                </div>
              ))}
            </div>
          )}
          {busy && <p className="text-[11px] text-subtle">{t("conn_repo_cloning")}</p>}
        </div>
      )}
    </div>
  );
}

function GitHubProjects() {
  const t = useT();
  const st = useStore.getState();
  const [list, setList] = useState([]);
  const [info, setInfo] = useState({});
  const [busy, setBusy] = useState("");
  const check = async (p) => {
    setInfo((x) => ({ ...x, [p.id]: { ...(x[p.id] || {}), checking: true } }));
    try { const r = await api.get(`/api/projects/${p.id}/git`); setInfo((x) => ({ ...x, [p.id]: r })); }
    catch (e) { setInfo((x) => ({ ...x, [p.id]: { ok: false, error: e.message } })); }
  };
  const load = async () => {
    const l = await api.get("/api/connections/github/projects").catch(() => []);
    setList(l);
    for (const p of l) await check(p); // one after another: each is a git fetch
  };
  useEffect(() => {
    load();
    const h = () => load();
    window.addEventListener("aiiq-git-projects", h);
    return () => window.removeEventListener("aiiq-git-projects", h);
  }, []);
  const pull = async (p, stash = false) => {
    setBusy(p.id);
    try {
      const r = await api.post(`/api/projects/${p.id}/git/pull`, { stash });
      setInfo((x) => ({ ...x, [p.id]: r }));
      st.notify(r.updated ? t("conn_pulled", { n: r.updated, name: p.name }) : t("conn_up_to_date"), "ok", r.note || undefined);
    } catch (e) { setInfo((x) => ({ ...x, [p.id]: { ...(x[p.id] || {}), error: e.message } })); }
    setBusy("");
  };
  if (!list.length) return null;
  return (
    <div className="rounded-xl border border-line">
      <div className="flex items-center gap-2 px-3 py-2.5 text-[13px] font-medium">
        <FolderGit2 size={14} className="text-accent" />{t("conn_projects_title")}
        <Button variant="ghost" className="ml-auto !px-2 !py-1" onClick={load}><RefreshCw size={13} /></Button>
      </div>
      <div className="divide-y divide-line border-t border-line">
        {list.map((p) => {
          const g = info[p.id] || {};
          return (
            <div key={p.id} className="space-y-1 px-3 py-2">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-[12.5px] font-medium">{p.name}</span>
                {g.branch && <span className="rounded-md bg-hover px-1.5 py-px font-mono text-[10.5px] text-muted">{g.branch}</span>}
                <span className="text-[11.5px] text-subtle">
                  {g.checking ? <Loader2 size={12} className="inline animate-spin" />
                    : g.ok === false ? "" : g.behind ? t("conn_behind", { n: g.behind })
                      : g.ok ? t("conn_up_to_date") : ""}
                  {g.ahead ? " · " + t("conn_ahead", { n: g.ahead }) : ""}
                  {g.dirty ? " · " + t("conn_dirty", { n: g.dirty }) : ""}
                </span>
                <div className="ml-auto flex gap-1.5">
                  {g.behind > 0 && (
                    <Button variant="primary" className="!px-2.5 !py-1" disabled={busy === p.id} onClick={() => pull(p, false)}>
                      {busy === p.id ? <Loader2 size={13} className="animate-spin" /> : <Download size={13} />}{t("conn_pull")}
                    </Button>
                  )}
                  {g.behind > 0 && g.dirty > 0 && (
                    <Button className="!px-2.5 !py-1" disabled={busy === p.id} onClick={() => pull(p, true)}>{t("conn_pull_keep")}</Button>
                  )}
                  <Button variant="ghost" className="!px-2 !py-1" title={t("conn_check")} onClick={() => check(p)}><RefreshCw size={13} /></Button>
                </div>
              </div>
              {g.remote_last && <div className="truncate text-[11px] text-subtle">{g.remote_last}</div>}
              <Err>{g.error}</Err>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------------------------------------- Google
function GoogleCard({ s, reload }) {
  const t = useT();
  const st = useStore.getState();
  const [cid, setCid] = useState("");
  const [sec, setSec] = useState("");
  const [svc, setSvc] = useState(s.services);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [guide, setGuide] = useState(!s.client_set);
  const poll = useRef(null);
  useEffect(() => () => clearInterval(poll.current), []);
  // Which APIs are really still off (asked from Google, not assumed): the warning shows only for those.
  const [apis, setApis] = useState(null);
  const checkApis = (force = false) => api.get(`/api/connections/google/apis${force ? "?force=true" : ""}`).then(setApis).catch(() => setApis(null));
  useEffect(() => { if (s.connected) checkApis(); else setApis(null); }, [s.connected, s.at]);
  const redirect = `${location.origin}/api/connections/google/callback`;
  const saveClient = async () => {
    setErr("");
    try { await api.put("/api/connections/google/client", { client_id: cid, client_secret: sec }); setCid(""); setSec(""); await reload(); st.notify(t("saved"), "ok"); }
    catch (e) { setErr(e.message); }
  };
  const connect = async () => {
    setErr(""); setBusy(true);
    try {
      const { url } = await api.post("/api/connections/google", { services: svc });
      openUrl(url);
      const t0 = Date.now();
      clearInterval(poll.current);
      poll.current = setInterval(async () => {
        const r = await api.get("/api/connections").catch(() => null);
        if ((r?.google?.connected && r.google.at !== s.at) || Date.now() - t0 > 300000) {
          clearInterval(poll.current); setBusy(false); reload();
        }
      }, 2500);
    } catch (e) { setErr(e.message); setBusy(false); }
  };
  const off = async () => {
    if (!(await st.confirm({ title: t("conn_disconnect"), message: t("conn_disconnect_q", { name: "Google" }), confirmLabel: t("conn_disconnect"), danger: true }))) return;
    await api.del("/api/connections/google"); reload();
  };
  return (
    <Box icon={Mail} title="Google Workspace" desc={t("conn_google_desc")}
      status={s.connected ? <Badge ok>{s.email || t("conn_connected_short")}</Badge> : <Badge>{t("conn_not_connected")}</Badge>}>
      <div className="flex flex-wrap gap-1.5">
        {s.all_services.map((x) => {
          const on = svc.includes(x.id);
          return (
            <button key={x.id} onClick={() => setSvc(on ? svc.filter((y) => y !== x.id) : [...svc, x.id])}
              className={`flex items-center gap-1 rounded-lg border px-2 py-1 text-[11.5px] transition ${on ? "border-accent/50 bg-accent/10 text-fg" : "border-line text-muted hover:bg-hover"}`}>
              {on && <Check size={11} />}{x.name}
            </button>
          );
        })}
      </div>
      {s.client_set ? (
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="primary" onClick={connect} disabled={busy || !svc.length}>
            {busy ? <Loader2 size={14} className="animate-spin" /> : <LogIn size={14} />}{t(s.connected ? "conn_google_reconnect" : "conn_google_connect")}
          </Button>
          {busy && <span className="text-[11.5px] text-subtle">{t("conn_browser_waiting")}</span>}
          <span className="font-mono text-[10.5px] text-subtle">{s.client_id}</span>
          {s.connected && <Button variant="danger" className="ml-auto !px-2.5 !py-1" onClick={off}><LogOut size={13} />{t("conn_disconnect")}</Button>}
        </div>
      ) : null}
      {s.connected && apis?.disabled?.length > 0 && (
        <div className="flex flex-wrap items-center gap-2 rounded-xl border border-warn/30 bg-warn/5 px-3 py-2 text-[12px] text-muted">
          <AlertTriangle size={13} className="shrink-0 text-warn" />
          <span className="min-w-0 flex-1">
            {t("conn_google_apis_off", { names: apis.disabled.map((id) => s.all_services.find((x) => x.id === id)?.name || id).join(", ") })}
          </span>
          {apis.enable_url && <Button className="!px-2.5 !py-1" onClick={() => openUrl(apis.enable_url)}><ExternalLink size={13} />{t("conn_google_apis_btn")}</Button>}
          <Button className="!px-2.5 !py-1" onClick={() => checkApis(true)}><RefreshCw size={13} />{t("conn_check_again")}</Button>
        </div>
      )}
      {s.connected && apis && !apis.disabled?.length && (
        <p className="flex items-center gap-1.5 text-[11.5px] text-ok"><CheckCircle2 size={13} />{t("conn_google_ready")}</p>
      )}
      <Err>{err}</Err>
      <div className="rounded-xl border border-line">
        <button onClick={() => setGuide(!guide)} className="flex w-full items-center gap-2 px-3 py-2.5 text-left text-[12.5px] font-medium">
          <KeyRound size={13} className="text-accent" />{t(s.client_set ? "conn_google_client_change" : "conn_google_setup")}
          <ChevronDown size={14} className={`ml-auto text-subtle transition ${guide ? "rotate-180" : ""}`} />
        </button>
        {guide && (
          <div className="space-y-2 border-t border-line p-3 text-[12px] leading-relaxed">
            <ol className="list-decimal space-y-1 pl-5 text-muted">
              <li>{t("conn_google_step1")} <a className="text-accent hover:underline" href="https://console.cloud.google.com/projectcreate" target="_blank" rel="noreferrer">console.cloud.google.com</a></li>
              <li>{t("conn_google_step2")}</li>
              <li>{t("conn_google_step3")} <a className="text-accent hover:underline" href="https://console.cloud.google.com/auth/clients" target="_blank" rel="noreferrer">Google Auth Platform › Clients</a></li>
              <li>{t("conn_google_step4")} <code className="break-all rounded bg-hover px-1 font-mono text-[11px]">{redirect}</code></li>
              <li>{t("conn_google_step_testers")} <a className="text-accent hover:underline" href="https://console.cloud.google.com/auth/audience" target="_blank" rel="noreferrer">Google Auth Platform › Audience</a></li>
              <li>{t("conn_google_step5")}</li>
            </ol>
            <p className="text-[11.5px] text-warn">{t("conn_google_preview")} <a className="underline" href="https://developers.google.com/workspace/guides/configure-mcp-servers" target="_blank" rel="noreferrer">{t("conn_guide")}</a></p>
            <div className="grid gap-2 @lg:grid-cols-2">
              <input className={`${inputCls} font-mono`} placeholder="…apps.googleusercontent.com" value={cid} onChange={(e) => setCid(e.target.value)} />
              <input type="password" className={`${inputCls} font-mono`} placeholder="GOCSPX-…" value={sec} onChange={(e) => setSec(e.target.value)} />
            </div>
            <Button onClick={saveClient} disabled={!cid.trim() || !sec.trim()}><KeyRound size={14} />{t("save")}</Button>
          </div>
        )}
      </div>
    </Box>
  );
}

// ---------------------------------------------------------------------------------------------------------- Microsoft
function MicrosoftCard({ s, reload }) {
  const t = useT();
  const st = useStore.getState();
  const [org, setOrg] = useState(s.org);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [login, setLogin] = useState(s.login?.state === "waiting" ? s.login : null);
  const poll = useRef(null);
  useEffect(() => () => clearInterval(poll.current), []);
  const watch = () => {
    clearInterval(poll.current);
    poll.current = setInterval(async () => {
      const r = await api.get("/api/connections").catch(() => null);
      const l = r?.microsoft?.login;
      if (!l || l.state === "done" || l.state === "error") {
        clearInterval(poll.current); setLogin(null);
        if (l?.state === "error") setErr(l.error);
        else st.notify(t("conn_connected", { name: "Microsoft 365" }), "ok");
        reload();
      }
    }, 3000);
  };
  useEffect(() => { if (login) watch(); }, []);
  const connect = async () => {
    setErr(""); setBusy(true);
    try {
      const r = await api.post("/api/connections/microsoft", { org });
      if (r.login?.state === "waiting") { setLogin(r.login); openUrl(r.login.url); watch(); }
      else if (r.login?.state === "error") setErr(r.login.error);
      else reload();
    } catch (e) { setErr(e.message); }
    setBusy(false);
  };
  const off = async () => {
    if (!(await st.confirm({ title: t("conn_disconnect"), message: t("conn_disconnect_q", { name: "Microsoft 365" }), confirmLabel: t("conn_disconnect"), danger: true }))) return;
    await api.del("/api/connections/microsoft"); reload();
  };
  return (
    <Box icon={Server} title="Microsoft 365" desc={t("conn_ms_desc")}
      status={s.connected ? <Badge ok>{t(s.org ? "conn_ms_work" : "conn_ms_personal")}</Badge> : <Badge>{t("conn_not_connected")}</Badge>}>
      {!s.connected ? (
        <>
          <div className="flex items-center justify-between gap-3">
            <div className="min-w-0"><div className="text-[12.5px] font-medium">{t("conn_ms_org")}</div><div className="text-[11px] text-subtle">{t("conn_ms_org_desc")}</div></div>
            <Toggle checked={org} onChange={setOrg} />
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Button variant="primary" onClick={connect} disabled={busy || !!login || !s.node}>
              {busy ? <Loader2 size={14} className="animate-spin" /> : <LogIn size={14} />}{t("conn_ms_connect")}
            </Button>
            {busy && <span className="text-[11.5px] text-subtle">{t("conn_ms_preparing")}</span>}
          </div>
          {!s.node && <p className="text-[11.5px] text-warn">{t("conn_node_missing")}</p>}
          {login && (
            <div className="space-y-2 rounded-xl border border-accent/40 bg-accent/5 p-3">
              <div className="text-[12.5px]">{t("conn_ms_code")}</div>
              <div className="flex flex-wrap items-center gap-2">
                <span className="rounded-lg bg-elev px-3 py-1.5 font-mono text-lg font-semibold tracking-widest">{login.code}</span>
                <Button className="!px-2.5 !py-1" onClick={() => navigator.clipboard?.writeText(login.code)}><Copy size={13} />{t("copy")}</Button>
                <Button className="!px-2.5 !py-1" onClick={() => openUrl(login.url)}><ExternalLink size={13} />{t("conn_ms_open")}</Button>
              </div>
              <div className="flex items-center gap-1.5 text-[11px] text-subtle"><Loader2 size={12} className="animate-spin" />{t("conn_browser_waiting")}</div>
            </div>
          )}
        </>
      ) : (
        <div className="flex flex-wrap items-center gap-2 text-[12px] text-muted">
          <span className="flex items-center gap-1 rounded-md bg-hover px-1.5 py-px text-[10.5px]"><Server size={11} />MCP: microsoft-365</span>
          <span>{t("conn_ms_tools")}</span>
          <Button variant="danger" className="ml-auto !px-2.5 !py-1" onClick={off}><LogOut size={13} />{t("conn_disconnect")}</Button>
        </div>
      )}
      <Err>{err}</Err>
    </Box>
  );
}

export default function ConnectionsPane() {
  const t = useT();
  const [s, setS] = useState(null);
  const reload = () => api.get("/api/connections").then(setS).catch(() => setS(null));
  useEffect(() => { reload(); }, []);
  if (!s) return <div className="flex items-center gap-2 text-xs text-muted"><Loader2 size={13} className="animate-spin" />{t("loading")}</div>;
  return (
    <div className="space-y-4">
      <p className="text-[12.5px] leading-relaxed text-muted">{t("conn_intro")}</p>
      <GitHubCard s={s.github} reload={reload} />
      <GoogleCard s={s.google} reload={reload} />
      <MicrosoftCard s={s.microsoft} reload={reload} />
      <p className="text-[11.5px] text-subtle">{t("conn_footer")}</p>
    </div>
  );
}
