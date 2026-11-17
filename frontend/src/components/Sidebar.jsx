import { memo, useEffect, useRef, useState } from "react";
import {
  Archive, ChevronDown, ChevronRight, Folder, FolderOpen, FolderPlus, Loader2, MoreHorizontal, PanelLeftClose, Pencil,
  Pin, PinOff, SquarePen, Trash2, ChevronsDownUp, MessageSquarePlus, ExternalLink, BookMarked, Eye, EyeOff, FolderInput,
  GitFork, Share2, Copy, AppWindow, Check, FolderMinus, Settings2, Search, X,
} from "lucide-react";
import { useStore, useT } from "../lib/store";
import { api } from "../lib/api";
import { ContextMenu, MenuItem, MenuSep, SubMenu } from "./ui";
import { Logo } from "./Brand";

function InlineRename({ value, onDone }) {
  const [v, setV] = useState(value);
  const finish = (save) => onDone(save && v.trim() && v.trim() !== value ? v.trim() : null);
  return (
    <input autoFocus value={v} onChange={(e) => setV(e.target.value)} onBlur={() => finish(true)}
      onClick={(e) => e.stopPropagation()}
      onKeyDown={(e) => { if (e.key === "Enter") finish(true); if (e.key === "Escape") finish(false); }}
      className="w-full rounded-md border border-accent bg-bg px-1.5 py-0.5 text-[13px] outline-none" />
  );
}

// Titles are plain text (no **Markdown**); a long one scrolls right-to-left while the pointer is on the row.
const plain = (s) => (s || "").replace(/\[([^\]]*)\]\([^)]*\)/g, "$1").replace(/[*_`#>~]+/g, "").trim();

function Title({ text }) {
  const box = useRef(null);
  const [shift, setShift] = useState(0);
  const enter = () => { const el = box.current; if (el) setShift(Math.max(0, el.scrollWidth - el.clientWidth)); };
  return (
    <div ref={box} onMouseEnter={enter} onMouseLeave={() => setShift(0)} className={`overflow-hidden whitespace-nowrap ${shift ? "" : "text-ellipsis"}`} title={text}>
      <span className="inline-block" style={shift ? { animation: `titlescroll ${Math.max(2.5, shift / 28)}s linear 0.3s infinite alternate`, "--shift": `-${shift + 8}px` } : undefined}>{text}</span>
    </div>
  );
}

const copy = (text) => navigator.clipboard.writeText(text).then(() => useStore.getState().notify(useStore.getState().t("copied"), "ok"));

const ChatRow = memo(function ChatRow({ s, active, running, nested }) {
  const t = useT();
  const [menu, setMenu] = useState(null);
  const [editing, setEditing] = useState(false);
  const projects = useStore((x) => x.projects);
  const st = useStore.getState();
  const openMenu = (e) => { e.preventDefault(); e.stopPropagation(); setMenu({ x: e.clientX, y: e.clientY }); };
  const unread = !!s.unread && !active && !running;
  const sel = useStore((x) => x.chatSel);
  const picked = !!sel?.has(s.id);
  useEffect(() => {
    if (!active) return;
    const on = (e) => e.detail === s.id && setEditing(true);
    addEventListener("aiiq:rename", on);
    return () => removeEventListener("aiiq:rename", on);
  }, [active, s.id]);
  return (
    <>
      <div onClick={() => (sel ? st.toggleSel("chatSel", s.id) : !editing && st.openSession(s.id))} onContextMenu={openMenu}
        className={`group flex h-8 cursor-pointer items-center gap-2 rounded-lg pr-1 text-[13px] ${nested ? "pl-2" : "pl-2.5"} ${picked ? "bg-accent-soft text-fg" : active ? "bg-active font-medium text-fg" : unread ? "font-semibold text-fg hover:bg-hover" : "text-muted hover:bg-hover hover:text-fg"}`}>
        {sel && (
          <span className={`grid h-4 w-4 shrink-0 place-items-center rounded border ${picked ? "border-accent bg-accent text-accent-fg" : "border-line bg-elev"}`}>
            {picked && <Check size={11} strokeWidth={3} />}
          </span>
        )}
        {running ? <Loader2 size={13} className="shrink-0 animate-spin text-accent" /> : s.pinned ? <Pin size={12} className="shrink-0 text-subtle" /> : null}
        <div className="min-w-0 flex-1">
          {editing ? <InlineRename value={plain(s.title)} onDone={(v) => { setEditing(false); v && st.patchSession(s.id, { title: v }); }} /> : <Title text={plain(s.title) || t("new_chat")} />}
        </div>
        {unread && <span className="h-2 w-2 shrink-0 rounded-full bg-accent group-hover:hidden" title={t("unread")} />}
        <button onClick={openMenu} className="hidden rounded p-0.5 text-subtle hover:bg-active hover:text-fg group-hover:block"><MoreHorizontal size={15} /></button>
      </div>
      {menu && (
        <ContextMenu {...menu} onClose={() => setMenu(null)}>
          <MenuItem icon={Pencil} label={t("rename")} shortcut="Alt+Ctrl+R" onClick={() => setEditing(true)} />
          <MenuItem icon={s.pinned ? PinOff : Pin} label={t(s.pinned ? "unpin" : "pin")} shortcut="Alt+Ctrl+P" onClick={() => st.patchSession(s.id, { pinned: !s.pinned })} />
          <MenuItem icon={unread ? Eye : EyeOff} label={t(unread ? "mark_read" : "mark_unread")}
            onClick={() => st.patchSession(s.id, { unread: !unread })} />
          <SubMenu icon={FolderInput} label={t("move_to_project")}>
            {projects.map((p) => (
              <MenuItem key={p.id} icon={Folder} label={p.name} right={s.project_id === p.id && <Check size={14} className="mt-0.5 text-accent" />}
                onClick={() => s.project_id !== p.id && st.moveSession(s.id, p.id)} />
            ))}
            {projects.length > 0 && <MenuSep />}
            <MenuItem icon={FolderMinus} label={t("move_out_of_project")} right={!s.project_id && <Check size={14} className="mt-0.5 text-accent" />}
              onClick={() => s.project_id && st.moveSession(s.id, null)} />
            <MenuItem icon={FolderPlus} label={t("new_project")} onClick={() => useStore.setState({ dialog: { type: "project" } })} />
          </SubMenu>
          <MenuSep />
          <MenuItem icon={GitFork} label={t("fork_chat")} onClick={() => st.forkSession(s.id)} />
          <MenuItem icon={Share2} label={t("share_chat")} onClick={() => st.exportSession(s.id, "download")} />
          <SubMenu icon={Copy} label={t("copy")}>
            <MenuItem label={t("copy_title")} onClick={() => copy(s.title || "")} />
            <MenuItem label={t("copy_chat_id")} onClick={() => copy(s.id)} />
            <MenuItem label={t("copy_as_markdown")} onClick={() => st.exportSession(s.id, "copy")} />
          </SubMenu>
          <MenuItem icon={AppWindow} label={t("open_new_window")} onClick={() => window.open(`${location.pathname}?session=${s.id}`, "_blank")} />
          <MenuSep />
          <MenuItem icon={Archive} label={t("archive")} shortcut="Ctrl+Shift+A" onClick={() => st.patchSession(s.id, { archived: true })} />
          <MenuItem icon={Trash2} label={t("delete_permanently")} danger onClick={() => st.deleteSession(s.id)} />
        </ContextMenu>
      )}
    </>
  );
});

const ProjectRow = memo(function ProjectRow({ p, chats, expanded, selected, sessionId, runs }) {
  const t = useT();
  const [menu, setMenu] = useState(null);
  const [editing, setEditing] = useState(false);
  const st = useStore.getState();
  const toggle = (e) => { e.stopPropagation(); useStore.setState((s) => ({ expanded: { ...s.expanded, [p.id]: !expanded } })); };
  const openMenu = (e) => { e.preventDefault(); e.stopPropagation(); setMenu({ x: e.clientX, y: e.clientY }); };
  return (
    <div>
      <div onClick={() => !editing && st.selectProject(p.id)} onContextMenu={openMenu}
        className={`group flex h-8 cursor-pointer items-center gap-1.5 rounded-lg pl-1 pr-1 text-[13px] ${selected ? "text-fg" : "text-muted hover:text-fg"} hover:bg-hover`}>
        <button onClick={toggle} className="rounded p-0.5 text-subtle hover:text-fg">{expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}</button>
        {expanded ? <FolderOpen size={15} className="shrink-0 text-accent" /> : <Folder size={15} className="shrink-0 text-subtle" />}
        <div className={`min-w-0 flex-1 truncate ${selected ? "font-semibold" : "font-medium"}`}>
          {editing ? <InlineRename value={p.name} onDone={(v) => { setEditing(false); v && st.renameProject(p.id, v); }} /> : p.name}
        </div>
        {!!p.pinned && <Pin size={11} className="shrink-0 text-subtle group-hover:hidden" />}
        <button title={t("new_chat")} onClick={(e) => { e.stopPropagation(); st.newChat(p.id); }} className="hidden rounded p-0.5 text-subtle hover:bg-active hover:text-fg group-hover:block"><SquarePen size={14} /></button>
        <button onClick={openMenu} className="hidden rounded p-0.5 text-subtle hover:bg-active hover:text-fg group-hover:block"><MoreHorizontal size={15} /></button>
      </div>
      {expanded && chats.length > 0 && (
        <div className="relative mb-1 ml-[18px] space-y-px border-l border-line pl-2">
          {chats.map((s) => <ChatRow key={s.id} s={s} nested active={s.id === sessionId} running={!!runs[s.id]} />)}
        </div>
      )}
      {menu && (
        <ContextMenu {...menu} onClose={() => setMenu(null)}>
          <MenuItem icon={p.pinned ? PinOff : Pin} label={t(p.pinned ? "unpin" : "pin")} onClick={() => st.pinProject(p.id, !p.pinned)} />
          <MenuItem icon={MessageSquarePlus} label={t("new_chat")} onClick={() => st.newChat(p.id)} />
          <SubMenu icon={Settings2} label={t("edit")}>
            <MenuItem icon={Pencil} label={t("rename")} onClick={() => setEditing(true)} />
            <MenuItem icon={BookMarked} label={t("project_rules")} onClick={() => useStore.setState({ dialog: { type: "rules", projectId: p.id } })} />
          </SubMenu>
          <MenuItem icon={ExternalLink} label={t("open_in_explorer")} onClick={() => api.post(`/api/projects/${p.id}/reveal`).catch(() => {})} />
          <MenuItem icon={ChevronsDownUp} label={t("collapse_all")} onClick={() => useStore.setState({ expanded: {} })} />
          <MenuSep />
          <MenuItem icon={Archive} label={t("archive_chats")} onClick={() => st.archiveProjectChats(p.id)} />
          <MenuItem icon={Trash2} label={t("remove_project")} danger onClick={() => st.removeProject(p.id)} />
        </ContextMenu>
      )}
    </div>
  );
});

// Full-text search over every chat (SQLite FTS5 on the server); a hit opens its chat.
function ChatSearch({ q }) {
  const t = useT();
  const [res, setRes] = useState(null);
  useEffect(() => {
    if (!q.trim()) { setRes(null); return; }
    const id = setTimeout(() => api.get(`/api/search?q=${encodeURIComponent(q)}`).then((r) => setRes(r.results || [])).catch(() => setRes([])), 220);
    return () => clearTimeout(id);
  }, [q]);
  if (res === null) return <div className="px-2.5 py-3 text-[12px] text-subtle">{t("searching")}</div>;
  if (!res.length) return <div className="px-2.5 py-3 text-[12px] text-subtle">{t("search_no_hits")}</div>;
  const parts = (s) => (s || "").split(/(\[\[.*?\]\])/g).map((p, i) => (p.startsWith("[[") ? <mark key={i} className="rounded bg-accent-soft px-0.5 text-fg">{p.slice(2, -2)}</mark> : p));
  return (
    <div className="space-y-px">
      {res.map((r) => (
        <button key={r.id} onClick={() => useStore.getState().openSession(r.session_id)}
          className="block w-full rounded-lg px-2.5 py-1.5 text-left hover:bg-hover">
          <div className="truncate text-[12.5px] font-medium text-fg">{plain(r.title) || t("new_chat")}</div>
          <div className="line-clamp-2 text-[11.5px] leading-snug text-muted">{r.role === "user" ? "› " : ""}{parts(plain(r.snippet))}</div>
        </button>
      ))}
    </div>
  );
}

export default function Sidebar() {
  const [q, setQ] = useState("");
  const t = useT();
  const projects = useStore((s) => s.projects);
  const sessions = useStore((s) => s.sessions);
  const expanded = useStore((s) => s.expanded);
  const sessionId = useStore((s) => s.sessionId);
  const projectId = useStore((s) => s.projectId);
  const scope = useStore((s) => s.scope);
  const runKey = useStore((s) => Object.keys(s.runs).sort().join(","));
  const runs = Object.fromEntries(runKey.split(",").filter(Boolean).map((k) => [k, true]));
  const st = useStore.getState();
  const loose = sessions.filter((x) => !x.project_id && x.title);
  const chatSel = useStore((s) => s.chatSel);
  // Shortcuts on the open chat: Alt+Ctrl+R rename, Alt+Ctrl+P pin, Ctrl+Shift+A archive.
  useEffect(() => {
    const on = (e) => {
      const sid = useStore.getState().sessionId;
      const cur = sid && useStore.getState().sessions.find((x) => x.id === sid);
      if (!cur || e.target.closest?.("input,textarea,[contenteditable=true]")) return;
      const k = e.key.toLowerCase();
      if (e.ctrlKey && e.altKey && k === "r") { e.preventDefault(); dispatchEvent(new CustomEvent("aiiq:rename", { detail: sid })); }
      else if (e.ctrlKey && e.altKey && k === "p") { e.preventDefault(); useStore.getState().patchSession(sid, { pinned: !cur.pinned }); }
      else if (e.ctrlKey && e.shiftKey && k === "a") { e.preventDefault(); useStore.getState().patchSession(sid, { archived: true }); }
    };
    addEventListener("keydown", on);
    return () => removeEventListener("keydown", on);
  }, []);

  return (
    <aside className="flex h-full w-[264px] shrink-0 flex-col border-r border-line bg-panel">
      <div className="flex h-12 items-center gap-2 px-3">
        <Logo size={24} />
        <span className="flex-1 text-[14px] font-semibold tracking-tight">AI IQ 300</span>
        <button onClick={() => { st.toggle("projectsOpen"); useStore.setState({ sidebarOpen: false }); }} className="rounded-lg p-1.5 text-muted hover:bg-hover"><PanelLeftClose size={16} /></button>
      </div>
      <div className="px-2">
        <button onClick={() => st.newChat()} className="flex h-9 w-full items-center gap-2 rounded-xl px-2.5 text-[13px] font-medium hover:bg-hover">
          <SquarePen size={16} /> {t("new_chat")}
        </button>
        <div className="relative mt-1">
          <Search size={14} className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-subtle" />
          <input value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => e.key === "Escape" && setQ("")}
            placeholder={t("search_chats")}
            className="h-8 w-full rounded-lg border border-transparent bg-transparent pl-8 pr-7 text-[13px] outline-none placeholder:text-subtle hover:bg-hover focus:border-line focus:bg-bg" />
          {q && <button onClick={() => setQ("")} className="absolute right-1.5 top-1/2 -translate-y-1/2 rounded p-0.5 text-subtle hover:text-fg"><X size={13} /></button>}
        </div>
      </div>

      {q.trim() ? <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-3 pt-2"><ChatSearch q={q} /></div> : (
      <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-3">
        <div className="mt-4 flex items-center justify-between px-2.5 pb-1 text-[11px] font-semibold uppercase tracking-wider text-subtle">
          {t("projects")}
          <button title={t("new_project")} onClick={() => useStore.setState({ dialog: { type: "project" } })} className="rounded-md p-1 hover:bg-hover hover:text-fg"><FolderPlus size={14} /></button>
        </div>
        {projects.length === 0 && (
          <button onClick={() => useStore.setState({ dialog: { type: "project" } })} className="w-full rounded-lg px-2.5 py-2 text-left text-[13px] text-subtle hover:bg-hover">+ {t("new_project")}</button>
        )}
        <div className="space-y-px">
          {projects.map((p) => (
            <ProjectRow key={p.id} p={p} expanded={!!expanded[p.id]} selected={scope === "project" && projectId === p.id}
              chats={sessions.filter((x) => x.project_id === p.id && x.title)} sessionId={sessionId} runs={runs} runKey={runKey} />
          ))}
        </div>

        {loose.length > 0 && (
          <>
            <div className="mt-5 flex items-center justify-between px-2.5 pb-1 text-[11px] font-semibold uppercase tracking-wider text-subtle">
              {t("recent")}
              <button onClick={() => useStore.setState({ chatSel: chatSel ? null : new Set() })} title={t("select_chats")}
                className={`rounded-md px-1.5 py-0.5 text-[10.5px] normal-case tracking-normal hover:bg-hover hover:text-fg ${chatSel ? "text-accent" : ""}`}>
                {t(chatSel ? "cancel" : "select")}
              </button>
            </div>
            {chatSel && (
              <div className="sticky top-0 z-10 mb-1 flex flex-wrap items-center gap-1 rounded-lg border border-line bg-elev px-2 py-1.5 text-[11.5px] shadow-sm">
                <span className="mr-auto text-muted">{t("selected_n", { n: chatSel.size })}</span>
                <button onClick={() => useStore.setState({ chatSel: chatSel.size === sessions.filter((x) => x.title).length ? new Set() : new Set(sessions.filter((x) => x.title).map((x) => x.id)) })}
                  className="rounded-md px-1.5 py-0.5 hover:bg-hover">{t(chatSel.size === sessions.filter((x) => x.title).length ? "select_none" : "select_all")}</button>
                <button onClick={() => st.deleteChats([...chatSel])} disabled={!chatSel.size}
                  className="flex items-center gap-1 rounded-md bg-danger/10 px-1.5 py-0.5 font-medium text-danger hover:bg-danger/20 disabled:opacity-40"><Trash2 size={12} />{t("delete")}</button>
              </div>
            )}
            <div className="space-y-px">
              {loose.map((s) => <ChatRow key={s.id} s={s} active={s.id === sessionId} running={!!runs[s.id]} />)}
            </div>
          </>
        )}
      </div>
      )}
    </aside>
  );
}
