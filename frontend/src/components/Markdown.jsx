import { memo, useEffect, useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import "katex/dist/katex.min.css";
import { keepBreaks, prepareMath } from "../lib/mathText";
import { Bot, Plug, Sparkles } from "lucide-react";
import { useStore } from "../lib/store";
import { docKind, fileType, isImage, isWebPage } from "../lib/fileTypes";
import CodeBlock from "./CodeBlock";
import Diagram from "./Diagram";
import { isMermaid, mermaidLang } from "../lib/mermaidText";

// Heuristic: a user message pasted as raw code (no fences) is framed as code too.
export function looksLikeCode(text) {
  if (text.includes("```")) return false;
  const lines = text.split("\n");
  if (lines.length < 3) return false;
  const codey = lines.filter((l) => /[;{}]\s*$|^\s*(def |class |import |from |function |const |let |<\?php|<\/?\w+[^>]*>|#include)/.test(l));
  return codey.length / lines.length > 0.4;
}

export function MentionChip({ token }) {
  const isAgent = token.startsWith("@");
  const isMcp = token.startsWith("#");
  const Icon = isAgent ? Bot : isMcp ? Plug : Sparkles;
  return (
    <span className={`mx-0.5 inline-flex translate-y-[-1px] items-center gap-1 rounded-md px-1.5 py-px align-middle text-[0.86em] font-medium ${isAgent ? "bg-violet-500/12 text-violet-600 dark:text-violet-300" : isMcp ? "bg-fuchsia-500/12 font-mono text-fuchsia-700 dark:text-fuchsia-300" : "bg-accent-soft text-accent"}`}>
      <Icon size={12} />{token}
    </span>
  );
}

// A file path the model wrote (`docs/report.pdf`): a chip that opens the file, but only when the file really exists in
// the chat folder (a bare ".docx" or a file the model only promised gave a chip that opened "HTTP 404"). Checked once
// per path (fs/exists: a yes/no answer, not a 404 in the log for every name that is not a file); missing files stay
// plain code.
const EXISTS = new Map(); // fileApi url -> Promise<boolean>
function fileExists(url) {
  if (!EXISTS.has(url)) {
    EXISTS.set(url, fetch(url.replace("/fs/raw?", "/fs/exists?")).then((r) => (r.ok ? r.json() : { exists: false }))
      .then((d) => !!d.exists).catch(() => false));
    setTimeout(() => EXISTS.delete(url), 15000); // a file written a moment later is found on the next render
  }
  return EXISTS.get(url);
}

function FileRef({ path, viewer, children }) {
  const st = useStore.getState();
  const sid = useStore((s) => s.sessionId);
  const url = sid ? st.fileApi(`/fs/raw?path=${encodeURIComponent(path)}`) : "";
  const [ok, setOk] = useState(null);
  useEffect(() => {
    let live = true;
    if (!url) { setOk(false); return undefined; }
    fileExists(url).then((v) => live && setOk(v));
    return () => { live = false; };
  }, [url]);
  if (!ok) return <code>{children}</code>;
  const ft = fileType(path);
  const Icon = ft.icon;
  const open = (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (viewer === "image") st.viewImages([path]);
    else if (viewer === "page") st.browse({ path });
    else st.previewFile(path);
  };
  return (
    <button type="button" onClick={open} title={path}
      className="mx-0.5 inline-flex translate-y-[1px] items-center gap-1 rounded-md border border-line bg-elev px-1.5 py-px align-middle text-[0.88em] font-medium hover:border-accent hover:text-accent">
      <Icon size={13} style={{ color: ft.color }} />{path}
    </button>
  );
}

// Stable component maps: defined once so React never remounts code blocks between renders.
// chips=false (text still being written live): a file named there may not exist yet, so it is no link; and a code
// fence that is still open has no content yet (was shown as "undefined").
const makeComponents = (chips) => ({
  pre: ({ children }) => <>{children}</>,
  code({ className, children, node }) {
    const content = String(children ?? "").replace(/\n$/, "");
    const isBlock = /language-/.test(className || "") || node?.position?.start.line !== node?.position?.end.line;
    if (!isBlock) {
      // A generated file's path (`docs/report.xlsx`, `logo.png`, `site/index.html`) opens its viewer.
      // "gorseller/01…05-*.png" names many files at once (or none): no viewer for wildcards or ellipses.
      const viewer = !chips || /\s|:\/\/|[*?…{}<>|]|\.\.\./.test(content) || !/(^|[\\/])[^./\\\s][^/\\]*\.[a-z0-9]{1,5}$/i.test(content) ? null : docKind(content) ? "previewFile" : isImage(content) ? "image"
        : isWebPage(content) ? "page" : null;
      if (viewer) return <FileRef path={content} viewer={viewer}>{children}</FileRef>;
      return <code>{children}</code>;
    }
    const lang = (className || "").replace("language-", "");
    // A Mermaid block is drawn as a diagram once the answer is complete; while it is still being written it stays
    // code (a half diagram does not parse and would flash errors).
    if (mermaidLang(lang, content)) {
      return chips ? <Diagram code={content} /> : <CodeBlock code={content} language="mermaid" />;
    }
    return <CodeBlock code={content} language={lang} />;
  },
  img({ src, alt }) {
    // A picture the model wrote with a path in the chat folder (images/x.jpg): served by the file API, not by the
    // app's own address (it showed as a broken image, mostly while the answer was still streaming).
    const st = useStore.getState();
    const local = src && !/^(https?:|data:|blob:|\/)/i.test(src);
    const url = local ? st.fileApi(`/fs/raw?path=${encodeURIComponent(src.replace(/^\.\//, ""))}`) : src;
    if (!url) return null;
    return (
      <img src={url} alt={alt || ""} loading="lazy"
        className="my-2 inline-block max-h-64 max-w-[min(100%,460px)] cursor-zoom-in rounded-xl border border-line bg-panel object-contain shadow-[0_2px_10px_rgb(0_0_0/0.08)] transition hover:border-accent/50 hover:shadow-md"
        onClick={(e) => { e.preventDefault(); e.stopPropagation(); local ? st.viewImages([src.replace(/^\.\//, "")]) : window.open(url, "_blank", "noreferrer"); }}
        onError={(e) => { e.currentTarget.style.display = "none"; }} />
    );
  },
  a({ href, children }) {
    if (href?.startsWith("#mention-")) return <MentionChip token={decodeURIComponent(href.slice(9))} />;
    // Local dev servers (http://localhost:3000) open in the in-app browser.
    if (/^https?:\/\/(localhost|127\.0\.0\.1|\[::1\])(:\d+)?(\/|$)/i.test(href || "")) {
      return <a href={href} onClick={(e) => { e.preventDefault(); useStore.getState().browse({ url: href }); }}>{children}</a>;
    }
    // A file of the chat folder (screenshots/home.png, docs/report.pdf): as a plain link the browser went to
    // <app>/screenshots/home.png, the app answered with its own page and the chat "reloaded". Open it in the app.
    if (href && !/^([a-z][a-z0-9+.-]*:|#|\/\/|\/api\/)/i.test(href)) {
      const path = decodeURIComponent(href.replace(/^\.?\//, "").split(/[?#]/)[0]);
      const open = (e) => {
        e.preventDefault();
        e.stopPropagation();
        const st = useStore.getState();
        if (isImage(path)) st.viewImages([path]);
        else if (docKind(path)) st.previewFile(path);
        else if (isWebPage(path)) st.browse({ path });
        else st.openFile(path);
      };
      return <a href={href} onClick={open} title={path}>{children}</a>;
    }
    return <a href={href} target="_blank" rel="noreferrer">{children}</a>;
  },
});
const COMPONENTS = makeComponents(true);
const COMPONENTS_LIVE = makeComponents(false);

function useMentionNames() {
  const catalog = useStore((s) => s.catalog);
  return useMemo(() => ({
    "@": new Set(catalog.agents.map((x) => x.name)), "/": new Set(catalog.skills.map((x) => x.name)),
  }), [catalog]);
}

const REMARK = [remarkGfm, [remarkMath, { singleDollarTextMath: true }]];
const REHYPE = [[rehypeKatex, { throwOnError: false, strict: "ignore", errorColor: "var(--danger)", output: "htmlAndMathml" }]];

// Text still being written ends mid-syntax: an open code fence, "**bold" without its end, a half link. Closed here
// for display only, so a streaming answer reads as formatted text at every moment instead of flashing raw symbols.
export function closeMarkdown(text) {
  let s = text.replace(/\s+$/, "");
  if ((s.match(/^\s*```/gm) || []).length % 2) return s + "\n```"; // inside a code block: nothing else applies
  const lastPara = s.slice(s.lastIndexOf("\n\n") + 1);
  const outside = lastPara.replace(/`[^`\n]*`/g, "");
  if ((outside.match(/`/g) || []).length % 2) return s + "`";
  s = s.replace(/!?\[[^\]\n]*\]?\([^)\n]*$/, "").replace(/!?\[[^\]\n]*$/, ""); // a link still being written
  const plain = outside.replace(/^\s*[*+-]\s/gm, "");
  if ((plain.match(/\*\*/g) || []).length % 2) s += "**";
  else if ((plain.replace(/\*\*/g, "").match(/\*/g) || []).length % 2) s += "*";
  if ((plain.match(/~~/g) || []).length % 2) s += "~~";
  return s;
}

function Markdown({ text, mentions = false, live = false }) {
  const names = useMentionNames();
  const src = useMemo(() => {
    // Mermaid code pasted without a fence (flowchart TD …) is drawn too.
    if (!text.includes("```") && isMermaid(text)) return "```mermaid\n" + text.trim() + "\n```";
    if (looksLikeCode(text)) return "```\n" + text + "\n```";
    let out = prepareMath(live ? closeMarkdown(text) : text);
    if (!mentions) return out;
    // A user's message: line breaks stay, and known @agent and /skill tokens become chip links (outside code).
    out = keepBreaks(out);
    return out.split(/(```[\s\S]*?```)/g).map((part) => (part.startsWith("```") ? part
      : part.replace(/(^|\s)([@/#])([\w./-]+)/g, (m, sp, sig, name) =>
        (sig === "#" ? /^[a-z0-9_-]{1,32}\/[\w.-]{1,64}$/.test(name) : names[sig].has(name)) ? `${sp}[${sig}${name}](#mention-${encodeURIComponent(sig + name)})` : m))).join("");
  }, [text, mentions, names, live]);
  return (
    <div className="prose-chat break-words">
      <ReactMarkdown remarkPlugins={REMARK} rehypePlugins={REHYPE} components={live ? COMPONENTS_LIVE : COMPONENTS}>{src}</ReactMarkdown>
    </div>
  );
}

export default memo(Markdown);
