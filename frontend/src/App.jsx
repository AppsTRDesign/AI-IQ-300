import { useEffect } from "react";
import * as monaco from "monaco-editor";
import { Menu, Moon, Sun, TerminalSquare, WifiOff } from "lucide-react";
import { useStore, useT } from "./lib/store";
import { connectEvents } from "./lib/socket";
import IconRail from "./components/IconRail";
import Sidebar from "./components/Sidebar";
import ChatView from "./components/ChatView";
import EditorPane from "./components/EditorPane";
import ProcessPanel from "./components/ProcessPanel";
import SettingsView from "./components/SettingsView";
import CatalogView from "./components/CatalogView";
import FilesView from "./components/FilesView";
import { AboutView, GuideView } from "./components/InfoPages";
import ProjectDialog from "./components/ProjectDialog";
import DocPreviewDialog from "./components/DocPreview";
import { ConfirmDialog, Toaster } from "./components/Feedback";

const VIEWS = { chat: ChatView, home: ChatView, settings: SettingsView, skills: CatalogView, agents: CatalogView, files: FilesView,
  guide: GuideView, about: AboutView };

function useTheme() {
  const theme = useStore((s) => s.prefs.theme);
  useEffect(() => {
    const mq = matchMedia("(prefers-color-scheme: dark)");
    const apply = () => {
      const dark = theme === "dark" || (theme === "system" && mq.matches);
      document.documentElement.classList.toggle("dark", dark);
      document.querySelector('meta[name="theme-color"]:not([media])')?.remove();
      monaco.editor.setTheme(dark ? "vs-dark" : "vs"); // also injects token colors for chat code blocks
      useStore.setState({ dark });
    };
    apply();
    mq.addEventListener("change", apply);
    return () => mq.removeEventListener("change", apply);
  }, [theme]);
}

export default function App() {
  const t = useT();
  const view = useStore((s) => s.view);
  const projectsOpen = useStore((s) => s.projectsOpen);
  const sidebarOpen = useStore((s) => s.sidebarOpen);
  const editorOpen = useStore((s) => s.editorOpen);
  const panel = useStore((s) => s.panel);
  const connected = useStore((s) => s.connected);
  const dialog = useStore((s) => s.dialog);
  const dark = useStore((s) => s.dark);
  const st = useStore.getState();
  useTheme();
  useEffect(() => {
    st.bootstrap().then(() => st.loadContext()).catch(() => {});
    return connectEvents();
  }, []);
  const View = VIEWS[view] || ChatView;

  return (
    <div className="flex h-full overflow-hidden bg-bg text-[14px] text-fg">
      <IconRail />
      {projectsOpen && <div className="hidden md:flex"><Sidebar /></div>}
      {sidebarOpen && (
        <div className="fixed inset-0 z-40 flex md:hidden">
          <div className="fade-in flex h-full shadow-2xl"><IconRail mobile /><Sidebar /></div>
          <button className="flex-1 bg-black/40" aria-label="close" onClick={() => st.toggle("sidebarOpen")} />
        </div>
      )}

      <main className="relative flex min-w-0 flex-1 flex-col">
        <header className="flex h-12 shrink-0 items-center gap-1 px-2 sm:px-3">
          <button className="rounded-lg p-2 text-muted hover:bg-hover md:hidden" onClick={() => st.toggle("sidebarOpen")}><Menu size={19} /></button>
          {!projectsOpen && <button className="hidden rounded-lg p-2 text-muted hover:bg-hover md:block" onClick={() => st.toggle("projectsOpen")}><Menu size={18} /></button>}
          <div className="flex-1" />
          {!connected && (
            <span className="flex items-center gap-1.5 rounded-full bg-warn/10 px-2.5 py-1 text-xs text-warn"><WifiOff size={12} /> {t("disconnected")}</span>
          )}
          <button title={t("theme")} onClick={() => st.setPref("theme", dark ? "light" : "dark")} className="rounded-lg p-2 text-muted hover:bg-hover">
            {dark ? <Sun size={17} /> : <Moon size={17} />}
          </button>
          <button title={t("processes")} onClick={() => st.toggle("panel")} className={`rounded-lg p-2 text-muted hover:bg-hover ${panel ? "bg-hover text-fg" : ""}`}>
            <TerminalSquare size={17} />
          </button>
        </header>
        <div className="flex min-h-0 flex-1">
          <div className={`min-w-0 flex-1 flex-col ${editorOpen ? "hidden lg:flex" : "flex"}`}><View /></div>
          {editorOpen && <EditorPane />}
        </div>
        {panel && <ProcessPanel />}
      </main>
      {dialog?.type === "project" && <ProjectDialog />}
      {dialog?.type === "preview" && <DocPreviewDialog />}
      <ConfirmDialog />
      <Toaster />
    </div>
  );
}
