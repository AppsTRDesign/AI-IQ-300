import { memo, useEffect, useState } from "react";
import { Check, Copy, SquareArrowOutUpRight } from "lucide-react";
import { useStore, useT } from "../lib/store";
import { normalizeLanguage } from "../lib/languages";

// Chat code frame. Uses Monaco's tokenizer (colorize) instead of a full editor instance per block:
// no workers, no remounting while streaming, so the chat never flickers. The editor button opens real Monaco.
function CodeBlock({ code, language, path }) {
  const t = useT();
  const [html, setHtml] = useState(null);
  const [copied, setCopied] = useState(false);
  const lang = normalizeLanguage(language);

  useEffect(() => {
    let alive = true;
    const timer = setTimeout(() => {
      import("../lib/monaco").then(({ monaco }) => monaco.editor.colorize(code, lang, { tabSize: 2 }))
        .then((h) => alive && setHtml(h)).catch(() => {});
    }, 60); // coalesce streaming updates
    return () => { alive = false; clearTimeout(timer); };
  }, [code, lang]);

  const lines = code.split("\n").length;
  const copy = async () => {
    try { await navigator.clipboard.writeText(code); setCopied(true); setTimeout(() => setCopied(false), 1500); } catch {}
  };
  const open = () => useStore.getState().openBuffer(path
    ? { id: path, path, content: code, saved: code }
    : { id: `snippet-${Date.now()}`, title: `snippet.${language || "txt"}`, language: lang, content: code });

  return (
    <div className="my-3 overflow-hidden rounded-2xl border border-line bg-code">
      <div className="flex items-center justify-between border-b border-line px-3 py-1.5 text-xs text-muted">
        <span className="truncate font-mono">{path || language || "text"}</span>
        <div className="flex shrink-0 gap-0.5">
          <button onClick={copy} className="flex items-center gap-1 rounded-lg px-2 py-1 hover:bg-hover">
            {copied ? <Check size={13} className="text-ok" /> : <Copy size={13} />}
            <span className="hidden sm:inline">{copied ? t("copied") : t("copy")}</span>
          </button>
          <button onClick={open} className="flex items-center gap-1 rounded-lg px-2 py-1 hover:bg-hover">
            <SquareArrowOutUpRight size={13} /> <span className="hidden sm:inline">{t("open_editor")}</span>
          </button>
        </div>
      </div>
      <div className="flex max-h-[480px] overflow-auto">
        {lines > 1 && (
          <div aria-hidden className="code-colorized sticky left-0 shrink-0 select-none bg-code px-3 py-2.5 text-right text-subtle">
            {Array.from({ length: lines }, (_, i) => <div key={i}>{i + 1}</div>)}
          </div>
        )}
        {html
          ? <div className={`code-colorized py-2.5 pr-4 ${lines > 1 ? "" : "pl-4"}`} dangerouslySetInnerHTML={{ __html: html }} />
          : <div className={`code-colorized py-2.5 pr-4 ${lines > 1 ? "" : "pl-4"}`}>{code}</div>}
      </div>
    </div>
  );
}

export default memo(CodeBlock);
