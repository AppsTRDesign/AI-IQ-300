// Reasoning text as models write it, made renderable (the live reasoning box and the saved "Thought" step):
// - basic formatting HTML (<p>, <br>, <b>/<strong>, <i>/<em>, <ul>/<ol>/<li>, <h1>-<h6>, <code>, <pre>, <a>, <hr>,
//   <blockquote>) becomes Markdown, so it renders as formatted text instead of showing tags;
// - real code written without ``` fences (an HTML page, CSS, Python, JS, PowerShell, SQL, Kotlin...) becomes a fenced
//   block with its language, shown in the Monaco-highlighted code frame like any code block;
// - a pipe table without its |---| line gets one; single line breaks are kept.

// Tags that only format text. Anything else (div, span with attributes, style, script, html, head, body, section,
// table markup with classes, svg...) is code the model is drafting.
const FORMAT_TAGS = "p|br|b|strong|i|em|u|s|del|ul|ol|li|h[1-6]|code|pre|a|hr|blockquote|mark|small|sub|sup";
const FORMAT_ONLY = new RegExp(`^(?:\\s|[^<]|</?(?:${FORMAT_TAGS})(?:\\s+href="[^"]*")?\\s*/?>)*$`, "i");
const ANY_TAG = /<\/?[a-zA-Z][\w-]*(\s[^>]*)?\/?>/;
const HTML_LINE = /^\s*(<!doctype|<!--|<\/?[a-zA-Z][\w-]*(\s[^>]*)?\/?>)/i;
const CODE_LINE = [
  [/^\s*(def |class \w+[(:]|import \w|from [\w.]+ import |async def |if __name__|print\(|return\b|elif |except\b|with \w+.*:$)/, "python"],
  [/^\s*(const |let |var |function |export |import .* from |=> ?\{|console\.|document\.|await |\}\s*\)?;?$)/, "javascript"],
  [/^\s*(\$\w+\s*=|Get-|Set-|New-Item|Write-Host|Invoke-)/, "powershell"],
  [/^\s*(SELECT |INSERT |UPDATE |CREATE TABLE|DELETE FROM)/i, "sql"],
  [/^\s*(fun |val |package [\w.]+$|plugins \{|android \{|dependencies \{|implementation\()/, "kotlin"],
  [/^\s*[.#]?[\w-]+\s*\{\s*$|^\s*[\w-]+:\s*[^;]+;\s*$/, "css"],
];

// A line that is formatted prose (only formatting tags), not code
const isFormatLine = (line) => ANY_TAG.test(line) && FORMAT_ONLY.test(line);

function lineLang(line) {
  if (HTML_LINE.test(line) && !isFormatLine(line)) return "html";
  for (const [re, lang] of CODE_LINE) if (re.test(line)) return lang;
  return null;
}

const ENTITIES = { amp: "&", lt: "<", gt: ">", quot: '"', apos: "'", nbsp: " ", "#39": "'" };
const decode = (s) => s.replace(/&(amp|lt|gt|quot|apos|nbsp|#39);/g, (_, k) => ENTITIES[k]);

// Formatting HTML -> Markdown (outside code fences only)
export function htmlToMarkdown(text) {
  if (!/<\/?(?:p|br|b|strong|i|em|u|s|del|ul|ol|li|h[1-6]|code|pre|a|hr|blockquote|mark|small|sub|sup)\b/i.test(text)) return text;
  let s = text;
  s = s.replace(/<pre[^>]*>\s*(?:<code[^>]*>)?([\s\S]*?)(?:<\/code>\s*)?<\/pre>/gi, (_, c) => `\n\`\`\`\n${decode(c).trim()}\n\`\`\`\n`);
  s = s.replace(/<br\s*\/?>/gi, "\n");
  s = s.replace(/<hr\s*\/?>/gi, "\n\n---\n\n");
  s = s.replace(/<h([1-6])[^>]*>([\s\S]*?)<\/h\1>/gi, (_, n, c) => `\n\n${"#".repeat(Number(n))} ${c.trim()}\n\n`);
  s = s.replace(/<(strong|b)>([\s\S]*?)<\/\1>/gi, (_, __, c) => (c.trim() ? `**${c.trim()}**` : ""));
  s = s.replace(/<(em|i)>([\s\S]*?)<\/\1>/gi, (_, __, c) => (c.trim() ? `*${c.trim()}*` : ""));
  s = s.replace(/<(s|del)>([\s\S]*?)<\/\1>/gi, (_, __, c) => `~~${c}~~`);
  s = s.replace(/<code>([\s\S]*?)<\/code>/gi, (_, c) => "`" + decode(c) + "`");
  s = s.replace(/<a\s+href="([^"]*)"[^>]*>([\s\S]*?)<\/a>/gi, (_, h, c) => `[${c}](${h})`);
  s = s.replace(/<blockquote>([\s\S]*?)<\/blockquote>/gi, (_, c) => "\n\n" + c.trim().split("\n").map((l) => `> ${l}`).join("\n") + "\n\n");
  // lists: <ol> items numbered, <ul> items bulleted
  s = s.replace(/<ol[^>]*>([\s\S]*?)<\/ol>/gi, (_, c) => {
    let n = 0;
    return "\n\n" + c.replace(/<li[^>]*>([\s\S]*?)(<\/li>|(?=<li)|$)/gi, (__, x) => `${++n}. ${x.trim()}\n`).trim() + "\n\n";
  });
  s = s.replace(/<ul[^>]*>([\s\S]*?)<\/ul>/gi, (_, c) => "\n\n" + c.replace(/<li[^>]*>([\s\S]*?)(<\/li>|(?=<li)|$)/gi, (__, x) => `- ${x.trim()}\n`).trim() + "\n\n");
  s = s.replace(/<li[^>]*>/gi, "\n- ").replace(/<\/li>/gi, "");
  s = s.replace(/<p[^>]*>/gi, "\n\n").replace(/<\/p>/gi, "\n\n");
  s = s.replace(/<\/?(u|mark|small|sub|sup|ul|ol)>/gi, "");
  s = decode(s);
  return s.replace(/\n{3,}/g, "\n\n");
}

// Line breaks as written: Markdown joins single newlines into one paragraph ("1. a\n2. b" became one line), so every
// line that is followed by another gets a hard break; <br> and escaped \n / \r\n (JSON-ish reasoning) are real breaks.
function hardBreaks(md) {
  const lines = md.split("\n");
  let fence = false;
  return lines.map((l, i) => {
    if (/^\s*(```|~~~)/.test(l)) { fence = !fence; return l; }
    const next = lines[i + 1];
    if (fence || !l.trim() || next == null || !next.trim() || /\s{2}$/.test(l) || /^\s*\|.*\|\s*$/.test(l)
      || /^\s*(```|~~~)/.test(next) || /^\s*#{1,6}\s/.test(l) || /^\s*(---|\*\*\*)\s*$/.test(l)) return l;
    return l + "  ";
  }).join("\n");
}

// Formatting HTML is converted only outside code fences (a fenced HTML page keeps its tags).
function outsideFences(text, fn) {
  return text.split(/(^\s*```[^\n]*\n[\s\S]*?^\s*```\s*$)/m).map((part, i) => (i % 2 ? part : fn(part))).join("");
}

// The reasoning as parts: {text} (HTML tags already turned into Markdown) and {code, lang, open} for code blocks
// (fenced by the model, or unfenced code the fence() pass found). `open` = a fence still being written.
export function thinkParts(text) {
  if (!text) return [];
  text = text.replace(/\r\n?/g, "\n");
  if (!/\n/.test(text.trim()) && /\\n/.test(text)) text = text.replace(/\\r\\n|\\n/g, "\n");
  const open = (text.match(/^[ \t]*(```|~~~)/gm) || []).length % 2 === 1; // the last fence is still being written
  const src = fence(text); // (closes an open fence for display)
  const parts = [];
  const re = /^[ \t]*(```|~~~)[ \t]*([\w+#.-]*)[^\n]*\n([\s\S]*?)^[ \t]*\1[ \t]*$/gm;
  let last = 0;
  let m;
  while ((m = re.exec(src))) {
    if (m.index > last) parts.push({ text: htmlToMarkdown(src.slice(last, m.index)) });
    parts.push({ code: m[3].replace(/\n$/, ""), lang: m[2] || "", open: false });
    last = m.index + m[0].length;
  }
  if (last < src.length) parts.push({ text: htmlToMarkdown(src.slice(last)) });
  const out = parts.filter((p) => p.code != null || p.text.trim());
  const lastCode = [...out].reverse().find((p) => p.code != null);
  if (open && lastCode && out[out.length - 1] === lastCode) lastCode.open = true;
  return out;
}

export function formatThinking(text) {
  if (!text) return "";
  text = text.replace(/\r\n?/g, "\n");
  if (!/\n/.test(text.trim()) && /\\n/.test(text)) text = text.replace(/\\r\\n|\\n/g, "\n"); // one escaped line
  const fenced = fence(text);
  return hardBreaks(outsideFences(fenced, htmlToMarkdown)).trim();
}

function fence(text) {
  const lines = text.split("\n");
  const out = [];
  let inFence = false;
  for (let i = 0; i < lines.length; i++) {
    const l = lines[i];
    if (/^\s*(```|~~~)/.test(l)) { inFence = !inFence; out.push(l); continue; }
    if (inFence) { out.push(l); continue; }
    // pipe table without the separator line: add it after the header row
    if (/^\s*\|.*\|\s*$/.test(l) && !/^\s*\|.*\|\s*$/.test(lines[i - 1] || "") && /^\s*\|.*\|\s*$/.test(lines[i + 1] || "")
      && !/^\s*\|[\s:|-]+\|\s*$/.test(lines[i + 1])) {
      if (out.length && out[out.length - 1].trim()) out.push("");
      out.push(l, l.replace(/[^|]+/g, (m) => (m.trim() ? "---" : m)).replace(/\|\s*\|/g, "| --- |"));
      continue;
    }
    const lang = lineLang(l);
    if (!lang) { out.push(l); continue; }
    // a run of code-looking lines (blank lines inside allowed): one fenced block; inside an HTML block, formatting
    // lines (<p>..</p>, <li>..) belong to the page being drafted
    let j = i;
    const block = [];
    let html = lang === "html";
    while (j < lines.length) {
      const cur = lines[j];
      if (/^\s*(```|~~~)/.test(cur)) break;
      const lg = lineLang(cur) || (html && HTML_LINE.test(cur) ? "html" : null);
      const cont = lg || (cur.trim() === "" && j + 1 < lines.length && (lineLang(lines[j + 1]) || (html && HTML_LINE.test(lines[j + 1]))))
        || (block.length && /^\s{2,}\S/.test(cur)) || (html && /^\s*\.\.\.\s*$/.test(cur))
        || (html && block.length && !/^\s*$/.test(cur) && /[<>{};]/.test(cur));
      if (!cont) break;
      if (lg === "html") html = true;
      block.push(cur);
      j++;
    }
    while (block.length && !block[block.length - 1].trim()) { block.pop(); j--; }
    const lang2 = html ? "html" : lang;
    if (block.length >= 2 || (lang2 === "html" && block[0].length > 40)) {
      if (out.length && out[out.length - 1].trim()) out.push("");
      out.push("```" + lang2, ...block, "```", "");
      i = j - 1;
    } else out.push(l);
  }
  if (inFence) out.push("```"); // a fence still open in a live stream closes for display
  return out.join("\n");
}
