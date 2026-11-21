import { memo, useMemo } from "react";
import CodeBlock from "./CodeBlock";
import { thinkParts } from "../lib/thinkfmt";
import katex from "katex";

// Reasoning text, fast: no full Markdown engine (it re-parsed the whole reasoning with math on every token and the
// live box fell behind fast models). Only what reasoning really contains: line breaks, basic HTML (b / i / u / ul /
// ol / li / table / br / p, turned into Markdown first), Markdown (headings, bold, italic, lists, tables, quotes,
// links, inline code) and code - shown in the Monaco code frame. A code block still being written is plain text
// until its fence closes, so the highlighter does not run on every token.

const esc = (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

// LaTeX ($..$, $$..$$, \(..\), \[..\]) with KaTeX - only when the text has a math marker, so plain reasoning costs
// nothing. Currency ("$5 and $10") stays text. A formula still being written renders when it closes.
const MATH_MARK = /\$|\\\(|\\\[/;
const tex = (m, display) => {
  try { return katex.renderToString(m, { displayMode: display, throwOnError: false, strict: "ignore", output: "html" }); } catch { return esc(m); }
};
// display formulas ($$..$$, \[..\]) become placeholder lines, rendered after the line parser
function displayMath(text) {
  if (!MATH_MARK.test(text)) return [text, []];
  const blocks = [];
  // "$$...$$" written as an example of the notation (only dots inside) is text, not a formula
  const put = (all, m) => {
    if (/^[\s.…]*$/.test(m)) return all;
    blocks.push(tex(m.trim(), true));
    return `\n\u0002${blocks.length - 1}\u0002\n`;
  };
  const out = text.replace(/\$\$([\s\S]+?)\$\$/g, put).replace(/\\\[([\s\S]+?)\\\]/g, put);
  return [out, blocks];
}
function inlineMath(s, keep) {
  if (!MATH_MARK.test(s)) return s;
  return s.replace(/\\\(([\s\S]+?)\\\)/g, (_, m) => { keep.push(tex(m, false)); return `\u0003${keep.length - 1}\u0003`; })
    .replace(/(^|[^\\$\w])\$(?!\s)([^$\n]{1,200}?[^\s$\\])\$(?!\w)/g, (all, pre, m) => {
      if (/^\d[\d.,]*$/.test(m) || /^[\s.…$]*$/.test(m)) return all; // $5 and $10: money; "$...$": an example
      keep.push(tex(m, false));
      return `${pre}\u0003${keep.length - 1}\u0003`;
    });
}

function inline(s) {
  const codes = [];
  const maths = [];
  s = s.replace(/`([^`\n]+)`/g, (_, c) => { codes.push(c); return `\u0000${codes.length - 1}\u0000`; });
  s = inlineMath(s, maths);
  s = esc(s)
    .replace(/\*\*([^*\n]+)\*\*/g, "<strong>$1</strong>")
    .replace(/__([^_\n]+)__/g, "<strong>$1</strong>")
    .replace(/(^|[^*\w])\*([^*\n]+)\*(?!\*)/g, "$1<em>$2</em>")
    .replace(/(^|[^_\w])_([^_\n]+)_(?!\w)/g, "$1<em>$2</em>")
    .replace(/~~([^~\n]+)~~/g, "<del>$1</del>")
    .replace(/\[([^\]\n]+)\]\((https?:\/\/[^)\s]+)\)/g, '<a href="$2" target="_blank" rel="noreferrer">$1</a>');
  return s.replace(/\u0000(\d+)\u0000/g, (_, i) => `<code>${esc(codes[+i])}</code>`)
    .replace(/\u0003(\d+)\u0003/g, (_, i) => maths[+i]);
}

const TABLE_ROW = /^\s*\|.*\|\s*$/;
const SEP_ROW = /^\s*\|[\s:|-]+\|\s*$/;
const cells = (l) => l.trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim());

// Reasoning as models really send it (measured 2026-11-21): deepseek-v4.1 and gpt-oss write ONE block with no line
// break at all, Nemotron uses lines and "- " lists, qwen3.8 short paragraphs. A wall of text is split here into
// readable paragraphs: at sentence ends, a new paragraph every ~2-3 sentences or where the thought turns ("Wait",
// "But", "So", "Ama", "Şimdi"...). Nothing else is added (user, 2026-11-21: plain text gets only spacing; HTML,
// Markdown and code are rendered when the model sends them; no extra work that slows the live box).
const TURN = /^(Wait|But|So|Hmm|Actually|However|Alternatively|Let me|Let's|Now|Then|Also|Okay|OK|Finally|First|Next|Ama|Ancak|Fakat|Şimdi|Peki|Yani|Sonra|Önce|Aslında|Bekle|Hmm|Tamam|Bu yüzden|Dolayısıyla|Kısaca|Plan|Problem|Çözüm|Sonuç)\b/;
const SENT = /(?<=[.!?…])\s+(?=["'“(\[]?[A-ZÇĞİÖŞÜ0-9])/;

export function paragraphize(text) {
  return text.split(/\n{2,}/).map((block) => {
    if (block.includes("\n") || block.length < 260 || /^\s*([-*•]|\d+[.)]|\||#)/.test(block)) return block;
    const sents = block.split(SENT);
    const out = [];
    let cur = "";
    for (const s of sents) {
      if (cur && (cur.length > 240 || (TURN.test(s) && cur.length > 60))) { out.push(cur.trim()); cur = ""; }
      cur += (cur ? " " : "") + s;
    }
    if (cur.trim()) out.push(cur.trim());
    return out.join("\n\n");
  }).join("\n\n");
}

export function mdToHtml(text) {
  const [prepared, blocks] = displayMath(text);
  const lines = paragraphize(prepared).replace(/\s+$/gm, "").split("\n");
  const out = [];
  let para = [];
  let list = null; // {tag, items}
  // every line of reasoning is its own paragraph (with space between), as in the final answer
  const flushPara = () => { for (const l of para) out.push(`<p>${inline(l)}</p>`); para = []; };
  const flushList = () => { if (list) { out.push(`<${list.tag}>${list.items.map((x) => `<li>${inline(x)}</li>`).join("")}</${list.tag}>`); list = null; } };
  for (let i = 0; i < lines.length; i++) {
    const l = lines[i];
    if (!l.trim()) { flushPara(); flushList(); continue; }
    let m;
    if ((m = l.match(/^\s*(#{1,6})\s+(.*)$/))) {
      flushPara(); flushList();
      out.push(`<h${Math.min(m[1].length + 2, 6)}>${inline(m[2])}</h${Math.min(m[1].length + 2, 6)}>`);
    } else if (TABLE_ROW.test(l) && TABLE_ROW.test(lines[i + 1] || "")) {
      flushPara(); flushList();
      const rows = [];
      while (i < lines.length && TABLE_ROW.test(lines[i])) { if (!SEP_ROW.test(lines[i])) rows.push(cells(lines[i])); i++; }
      i--;
      const [head, ...body] = rows;
      out.push(`<table><thead><tr>${head.map((c) => `<th>${inline(c)}</th>`).join("")}</tr></thead><tbody>`
        + body.map((r) => `<tr>${r.map((c) => `<td>${inline(c)}</td>`).join("")}</tr>`).join("") + "</tbody></table>");
    } else if ((m = l.match(/^\s*(?:[-*•+])\s+(.*)$/)) || (m = l.match(/^\s*\d+[.)]\s+(.*)$/))) {
      flushPara();
      const tag = /^\s*\d/.test(l) ? "ol" : "ul";
      if (list && list.tag !== tag) flushList();
      list = list || { tag, items: [] };
      list.items.push(m[1]);
    } else if ((m = l.match(/^\s*>\s?(.*)$/))) {
      flushPara(); flushList();
      out.push(`<blockquote>${inline(m[1])}</blockquote>`);
    } else if (/^\s*(---+|\*\*\*+)\s*$/.test(l)) {
      flushPara(); flushList();
      out.push("<hr>");
    } else {
      flushList();
      para.push(l.trim());
    }
  }
  flushPara(); flushList();
  const html = out.join("");
  return blocks.length ? html.replace(/<p>\u0002(\d+)\u0002<\/p>|\u0002(\d+)\u0002/g, (_, a, b) => `<div class="think-math">${blocks[+(a ?? b)]}</div>`) : html;
}

function ThinkText({ text, live = false }) {
  const parts = useMemo(() => thinkParts(text || ""), [text]);
  return (
    <div className="prose-chat think-text">
      {parts.map((p, i) => (p.code != null
        ? (p.open && live
          ? <pre key={i} className="think-pre">{p.code}</pre>
          : <CodeBlock key={i} code={p.code} language={p.lang} />)
        : <div key={i} dangerouslySetInnerHTML={{ __html: mdToHtml(p.text) }} />))}
    </div>
  );
}

export default memo(ThinkText);
