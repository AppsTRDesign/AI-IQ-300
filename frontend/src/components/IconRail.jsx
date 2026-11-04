import { BookOpen, Bot, FolderOpen, History, Home, Info, Settings, Sparkles } from "lucide-react";
import { useStore, useT } from "../lib/store";

const ITEMS = [
  { id: "home", icon: Home, key: "home" },
  { id: "skills", icon: Sparkles, key: "skills" },
  { id: "sessions", icon: History, key: "sessions" },
  { id: "files", icon: FolderOpen, key: "files" },
  { id: "agents", icon: Bot, key: "agents" },
];

export default function IconRail({ mobile }) {
  const view = useStore((s) => s.view);
  const t = useT();
  const st = useStore.getState();
  const go = (id) => {
    if (id === "home") return st.newChat();
    if (id === "sessions") { if (!mobile) st.toggle(innerWidth >= 1024 ? "projectsOpen" : "sidebarOpen"); return st.setView("chat"); }
    st.setView(id);
  };
  const btn = (active) => `grid h-9 w-9 place-items-center rounded-xl transition ${active ? "bg-active text-fg" : "text-muted hover:bg-hover hover:text-fg"}`;
  return (
    <nav className={`${mobile ? "flex" : "hidden md:flex"} w-14 shrink-0 flex-col items-center gap-1 border-r border-line bg-panel py-3`}>
      {ITEMS.map(({ id, icon: Icon, key }) => (
        <button key={id} title={t(key)} onClick={() => go(id)} className={btn(view === id || (id === "home" && view === "chat"))}><Icon size={19} /></button>
      ))}
      <div className="flex-1" />
      <button title={t("guide")} onClick={() => st.setView("guide")} className={btn(view === "guide")}><BookOpen size={19} /></button>
      <button title={t("set_about")} onClick={() => st.setView("about")} className={btn(view === "about")}><Info size={19} /></button>
      <button title={t("settings")} onClick={() => st.setView("settings")} className={btn(view === "settings")}><Settings size={19} /></button>
    </nav>
  );
}
