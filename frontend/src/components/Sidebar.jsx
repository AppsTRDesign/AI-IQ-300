import { memo, useState } from "react";
import {
  Archive, ChevronDown, ChevronRight, Folder, FolderOpen, FolderPlus, Loader2, MoreHorizontal, PanelLeftClose, Pencil,
  Pin, PinOff, SquarePen, Trash2, ChevronsDownUp, MessageSquarePlus, ExternalLink, BookMarked,
} from "lucide-react";
import { useStore, useT } from "../lib/store";
import { api } from "../lib/api";
import { ContextMenu, MenuItem, MenuSep } from "./ui";
import { Logo } from "./Brand";

function InlineRename({ value, onDone }) {
  const [v, setV] = useState(value);
  const finish = (save) => onDone(save && v.trim() && v.trim() !== value ? v.trim() : null);
  return (
    <input autoFocus value={v} onChange={(e) => setV(e.target.value)} onBlur={() => finish(true)}
      onKeyDown={(e) => { if (e.key === "Enter") finish(true); if (e.key === "Escape") finish(false); }}
      className="w-full rounded-md border border-accent bg-bg px-1.5 py-0.5 text-[13px] outline-none" />
  );
}

const ChatRow = memo(function ChatRow({ s, active, running, nested }) {
  const t = useT();
  const [menu, setMenu] = useState(null);
  const [editing, setEditing] = useState(false);
  const st = useStore.getState();
  const openMenu = (e) => { e.preventDefault(); e.stopPropagation(); setMenu({ x: e.clientX, y: e.clientY }); };
  return (
    <>
      <div onClick={() => !editing && st.openSession(s.id)} onContextMenu={openMenu}
        className={`group flex h-8 cursor-pointer items-center gap-2 rounded-lg pr-1 text-[13px] ${nested ? "pl-2" : "pl-2.5"} ${active ? "bg-active font-medium text-fg" : "text-muted hover:bg-hover hover:text-fg"}`}>
        {running ? <Loader2 size={13} className="shrink-0 animate-spin text-accent" /> : s.pinned ? <Pin size={12} className="shrink-0 text-subtle" /> : null}
        <div className="min-w-0 flex-1 truncate">
          {editing ? <InlineRename value={s.title} onDone={(v) => { setEditing(false); v && st.patchSession(s.id, { title: v }); }} /> : (s.title || t("new_chat"))}
        </div>
        <button onClick={openMenu} className="hidden rounded p-0.5 text-subtle hover:bg-active hover:text-fg group-hover:block"><MoreHorizontal size={15} /></button>
      </div>
      {menu && (
        <ContextMenu {...menu} onClose={() => setMenu(null)}>
          <MenuItem icon={s.pinned ? PinOff : Pin} label={t(s.pinned ? "unpin" : "pin")} shortcut="P" onClick={() => st.patchSession(s.id, { pinned: !s.pinned })} />
          <MenuItem icon={Pencil} label={t("rename")} shortcut="R" onClick={() => setEditing(true)} />
          <MenuSep />
          <MenuItem icon={Archive} label={t("archive")} shortcut="A" onClick={() => st.patchSession(s.id, { archived: true })} />
          <MenuItem icon={Trash2} label={t("delete")} shortcut="D" danger onClick={() => st.deleteSession(s.id)} />
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
          <MenuItem icon={MessageSquarePlus} label={t("new_chat")} shortcut="N" onClick={() => st.newChat(p.id)} />
          <MenuItem icon={Pencil} label={t("rename")} shortcut="R" onClick={() => setEditing(true)} />
          <MenuItem icon={BookMarked} label={t("project_rules")} onClick={() => useStore.setState({ dialog: { type: "rules", projectId: p.id } })} />
          <MenuItem icon={ExternalLink} label={t("open_folder")} onClick={() => api.post(`/api/projects/${p.id}/reveal`).catch(() => {})} />
          <MenuItem icon={ChevronsDownUp} label={t("collapse_all")} onClick={() => useStore.setState({ expanded: {} })} />
          <MenuSep />
          <MenuItem icon={Trash2} label={t("remove_project")} danger onClick={() => st.removeProject(p.id)} />
        </ContextMenu>
      )}
    </div>
  );
});

export default function Sidebar() {
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
      </div>

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
            <div className="mt-5 px-2.5 pb-1 text-[11px] font-semibold uppercase tracking-wider text-subtle">{t("recent")}</div>
            <div className="space-y-px">
              {loose.map((s) => <ChatRow key={s.id} s={s} active={s.id === sessionId} running={!!runs[s.id]} />)}
            </div>
          </>
        )}
      </div>
    </aside>
  );
}
