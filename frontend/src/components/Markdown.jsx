import { memo, useMemo } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import "katex/dist/katex.min.css";
import { keepBreaks, prepareMath } from "../lib/mathText";
import { Bot, Sparkles } from "lucide-react";
import { useStore } from "../lib/store";
import { docKind, fileType, isImage, isWebPage } from "../lib/fileTypes";
import CodeBlock from "./CodeBlock";

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
  const Icon = isAgent ? Bot : Sparkles;
  return (
    <span className={`mx-0.5 inline-flex translate-y-[-1px] items-center gap-1 rounded-md px-1.5 py-px align-middle text-[0.86em] font-medium ${isAgent ? "bg-violet-500/12 text-violet-600 dark:text-violet-300" : "bg-accent-soft text-accent"}`}>
      <Icon size={12} />{token}
    </span>
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
      const viewer = !chips || /\s|:\/\/|[*?…{}<>|]|\.\.\./.test(content) ? null : docKind(content) ? "previewFile" : isImage(content) ? "image"
        : isWebPage(content) ? "page" : null;
      if (viewer) {
        const ft = fileType(content);
        const Icon = ft.icon;
        const st = useStore.getState();
        const open = () => (viewer === "image" ? st.viewImages([content]) : viewer === "page" ? st.browse({ path: content }) : st.previewFile(content));
        return (
          <button onClick={open} title={content}
            className="mx-0.5 inline-flex translate-y-[1px] items-center gap-1 rounded-md border border-line bg-elev px-1.5 py-px align-middle text-[0.88em] font-medium hover:border-accent hover:text-accent">
            <Icon size={13} style={{ color: ft.color }} />{content}
          </button>
        );
      }
      return <code>{children}</code>;
    }
    return <CodeBlock code={content} language={(className || "").replace("language-", "")} />;
  },
  a({ href, children }) {
    if (href?.startsWith("#mention-")) return <MentionChip token={decodeURIComponent(href.slice(9))} />;
    // Local dev servers (http://localhost:3000) open in the in-app browser.
    if (/^https?:\/\/(localhost|127\.0\.0\.1|\[::1\])(:\d+)?(\/|$)/i.test(href || "")) {
      return <a href={href} onClick={(e) => { e.preventDefault(); useStore.getState().browse({ url: href }); }}>{children}</a>;
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
    if (looksLikeCode(text)) return "```\n" + text + "\n```";
    let out = prepareMath(live ? closeMarkdown(text) : text);
    if (!mentions) return out;
    // A user's message: line breaks stay, and known @agent and /skill tokens become chip links (outside code).
    out = keepBreaks(out);
    return out.split(/(```[\s\S]*?```)/g).map((part) => (part.startsWith("```") ? part
      : part.replace(/(^|\s)([@/])([\w-]+)/g, (m, sp, sig, name) =>
        names[sig].has(name) ? `${sp}[${sig}${name}](#mention-${encodeURIComponent(sig + name)})` : m))).join("");
  }, [text, mentions, names, live]);
  return (
    <div className="prose-chat break-words">
      <ReactMarkdown remarkPlugins={REMARK} rehypePlugins={REHYPE} components={live ? COMPONENTS_LIVE : COMPONENTS}>{src}</ReactMarkdown>
    </div>
  );
}

export default memo(Markdown);
