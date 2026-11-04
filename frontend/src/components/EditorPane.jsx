import { useEffect } from "react";
import Editor from "@monaco-editor/react";
import { Globe, Save, X } from "lucide-react";
import { isWebPage } from "../lib/fileTypes";
import { useStore, useT } from "../lib/store";
import { languageForPath } from "../lib/languages";
import "../lib/monaco";

// Full Monaco editor with tabs. Ctrl+S saves files that belong to the session workspace.
export default function EditorPane() {
  const editor = useStore((s) => s.editor);
  const dark = useStore((s) => s.dark);
  const { editBuffer, closeBuffer, saveBuffer, toggle } = useStore.getState();
  const t = useT();
  const tab = editor.tabs.find((x) => x.id === editor.active);
  useEffect(() => {
    const h = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "s" && (tab?.path || tab?.onSave)) { e.preventDefault(); saveBuffer(tab.id); }
    };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [tab?.id, tab?.path]);

  return (
    <section className="flex min-w-0 flex-1 flex-col border-l border-line lg:max-w-[55%]">
      <div className="scroll-thin flex items-center overflow-x-auto border-b border-line bg-panel">
        {editor.tabs.map((x) => {
          const dirty = x.path && x.content !== x.saved;
          return (
            <div key={x.id} onClick={() => useStore.setState((s) => ({ editor: { ...s.editor, active: x.id } }))}
              className={`flex shrink-0 cursor-pointer items-center gap-1.5 border-r border-line px-3 py-1.5 text-xs ${x.id === editor.active ? "bg-bg" : "text-muted"}`}>
              <span className="font-mono">{(x.path || x.title || "").split("/").pop()}{dirty ? " •" : ""}</span>
              <button onClick={(e) => { e.stopPropagation(); closeBuffer(x.id); }} className="rounded hover:bg-active"><X size={12} /></button>
            </div>
          );
        })}
        <div className="flex-1" />
        {tab?.path && isWebPage(tab.path) && (
          <button onClick={async () => { if (tab.content !== tab.saved) await saveBuffer(tab.id); useStore.getState().browse({ path: tab.path }); }}
            title={t("open_browser")} className="px-2 text-muted hover:text-fg"><Globe size={15} /></button>
        )}
        {tab?.path && (
          <button onClick={() => saveBuffer(tab.id)} title={t("save")} className="px-2 text-muted hover:text-fg"><Save size={15} /></button>
        )}
        <button onClick={() => toggle("editorOpen")} className="px-2 text-muted hover:text-fg"><X size={15} /></button>
      </div>
      {tab ? (
        <Editor
          path={tab.id}
          language={tab.language || languageForPath(tab.path || tab.title)}
          value={tab.content}
          onChange={(v) => editBuffer(tab.id, v ?? "")}
          theme={dark ? "vs-dark" : "vs"}
          options={{ fontSize: 13, minimap: { enabled: true }, automaticLayout: true, wordWrap: "on", tabSize: 2 }}
        />
      ) : (
        <div className="grid flex-1 place-items-center text-subtle">{t("select_file")}</div>
      )}
    </section>
  );
}
