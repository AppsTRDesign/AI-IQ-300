import { forwardRef, useCallback, useEffect, useImperativeHandle, useRef, useState } from "react";
import { Bold, Check, ChevronDown, Code, Italic, Link2, Strikethrough, X } from "lucide-react";
import { useT } from "../lib/store";

// The message box: a rich editor (contenteditable) that is sent as Markdown. Formatting shows at once (Ctrl+B makes
// text bold, not **text**), a toolbar appears over selected text, lists/headings/quotes start with Markdown shortcuts
// at the line start ("- ", "1. ", "# ", "> "), line breaks stay as typed, and @agent / /skill tokens become chips.

const BLOCKS = new Set(["DIV", "P", "LI", "UL", "OL", "H1", "H2", "H3", "H4", "BLOCKQUOTE", "PRE"]);

function inline(node) {
  let out = "";
  for (const n of node.childNodes) {
    if (n.nodeType === 3) { out += n.data.replace(/ /g, " ").replace(/​/g, ""); continue; }
    if (n.nodeType !== 1) continue;
    const tag = n.tagName;
    if (tag === "BR") { out += "\n"; continue; }
    if (n.classList?.contains("mention")) { out += n.textContent; continue; }
    if (BLOCKS.has(tag)) { out += (out && !out.endsWith("\n") ? "\n" : "") + block(n).replace(/\n+$/, "") + "\n"; continue; }
    const inner = inline(n);
    if (!inner.trim()) { out += inner; continue; }
    const lead = inner.match(/^\s*/)[0], trail = inner.match(/\s*$/)[0], core = inner.trim();
    const wrap = (a, b = a) => lead + a + core + b + trail;
    if (tag === "B" || tag === "STRONG" || (tag === "SPAN" && /bold|[6-9]00/.test(n.style.fontWeight))) out += wrap("**");
    else if (tag === "I" || tag === "EM" || (tag === "SPAN" && n.style.fontStyle === "italic")) out += wrap("*");
    else if (tag === "S" || tag === "STRIKE" || tag === "DEL") out += wrap("~~");
    else if (tag === "CODE") out += wrap("`");
    else if (tag === "A" && n.getAttribute("href")) out += lead + `[${core}](${n.getAttribute("href")})` + trail;
    else out += inner;
  }
  return out;
}

function list(el, depth) {
  const ordered = el.tagName === "OL";
  let i = 0, out = "";
  for (const li of el.children) {
    if (li.tagName !== "LI") continue;
    i += 1;
    const nested = [...li.children].filter((c) => c.tagName === "UL" || c.tagName === "OL");
    const clone = li.cloneNode(true);
    clone.querySelectorAll(":scope > ul, :scope > ol").forEach((x) => x.remove());
    const text = inline(clone).trim().replace(/\n/g, "\n" + "   ".repeat(depth + 1));
    out += `${"   ".repeat(depth)}${ordered ? `${i}.` : "-"} ${text}\n`;
    for (const sub of nested) out += list(sub, depth + 1);
  }
  return out;
}

function block(el) {
  const tag = el.tagName;
  if (tag === "UL" || tag === "OL") return list(el, 0);
  if (/^H[1-4]$/.test(tag)) return `${"#".repeat(+tag[1])} ${inline(el).trim()}\n`;
  if (tag === "BLOCKQUOTE") return inline(el).trim().split("\n").map((l) => `> ${l}`).join("\n") + "\n";
  if (tag === "PRE") return "```\n" + el.textContent.replace(/\n+$/, "") + "\n```\n";
  return inline(el) + "\n";
}

export function toMarkdown(root) {
  let out = "";
  let line = "";
  for (const n of root.childNodes) {
    if (n.nodeType === 1 && BLOCKS.has(n.tagName)) {
      if (line) { out += line + (line.endsWith("\n") ? "" : "\n"); line = ""; }
      const b = block(n);
      // lists/headings/quotes/code get a blank line around them so Markdown sees them as blocks
      const structural = /^(UL|OL|H\d|BLOCKQUOTE|PRE)$/.test(n.tagName);
      out += (structural && out && !out.endsWith("\n\n") ? "\n" : "") + b + (structural ? "\n" : "");
    } else {
      const wrap = document.createElement("span");
      wrap.appendChild(n.cloneNode(true));
      line += inline(wrap);
    }
  }
  out += line;
  return out.replace(/\n{3,}/g, "\n\n").replace(/^\n+|\s+$/g, "");
}

const esc = (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

function caretRange(root) {
  const s = getSelection();
  if (!s?.rangeCount) return null;
  const r = s.getRangeAt(0);
  return root.contains(r.startContainer) ? r : null;
}

function placeAfter(node, offset = 0) {
  const r = document.createRange();
  if (node.nodeType === 3) r.setStart(node, Math.min(offset, node.data.length));
  else r.setStartAfter(node);
  r.collapse(true);
  const s = getSelection();
  s.removeAllRanges();
  s.addRange(r);
}

const TEXT_STYLES = [
  { id: "p", key: "fmt_text", cmd: ["formatBlock", "div"] },
  { id: "h1", key: "fmt_h1", cmd: ["formatBlock", "h1"] },
  { id: "h2", key: "fmt_h2", cmd: ["formatBlock", "h2"] },
  { id: "h3", key: "fmt_h3", cmd: ["formatBlock", "h3"] },
  { id: "ol", key: "fmt_ol", cmd: ["insertOrderedList"] },
  { id: "ul", key: "fmt_ul", cmd: ["insertUnorderedList"] },
  { id: "quote", key: "fmt_quote", cmd: ["formatBlock", "blockquote"] },
  { id: "pre", key: "fmt_code_block", cmd: ["formatBlock", "pre"] },
];

const topOf = (root, node) => { let n = node; while (n && n.parentNode !== root) n = n.parentNode; return n; };

function caretIn(el, atEnd = true) {
  const r = document.createRange();
  r.selectNodeContents(el);
  r.collapse(!atEnd);
  const s = getSelection();
  s.removeAllRanges();
  s.addRange(r);
}

// Every line of the editor is a block element (bare text and <br> lines are wrapped), so block formats apply to
// whole lines predictably.
function ensureBlocks(root) {
  let line = null;
  for (const n of [...root.childNodes]) {
    if (n.nodeType === 1 && BLOCKS.has(n.tagName)) { line = null; continue; }
    if (n.nodeName === "BR") {
      if (!line) { line = document.createElement("div"); root.insertBefore(line, n); line.appendChild(n); } else n.remove();
      line = null;
      continue;
    }
    if (!line) { line = document.createElement("div"); root.insertBefore(line, n); }
    line.appendChild(n);
  }
}

// Text / Heading 1-3 / Quote / Code block for the selected lines; choosing the active format again returns to text.
// Inline code on the selection: wraps it (and keeps it selected), or unwraps when it already is code - never nested.
function toggleCode(root) {
  root.focus();
  const r = caretRange(root);
  if (!r) return;
  const inCode = (n) => (n?.nodeType === 3 ? n.parentElement : n)?.closest?.("code");
  const a = inCode(r.startContainer), b = inCode(r.endContainer);
  const inside = [...root.querySelectorAll("code")].filter((c) => !c.closest("pre") && r.intersectsNode(c));
  if (a || b || inside.length) { // unwrap every code element the selection touches
    const freed = [];
    for (const c of new Set([a, b, ...inside].filter(Boolean))) { freed.push(...c.childNodes); c.replaceWith(...c.childNodes); }
    if (freed.length) { // the same text stays selected, so pressing the button again wraps it again
      const k = document.createRange();
      k.setStartBefore(freed[0]);
      k.setEndAfter(freed[freed.length - 1]);
      const s = getSelection();
      s.removeAllRanges();
      s.addRange(k);
    }
    return;
  }
  if (r.collapsed) return; // nothing selected: nothing to mark
  const c = document.createElement("code");
  c.appendChild(r.extractContents());
  r.insertNode(c);
  const sel = document.createRange();
  sel.selectNodeContents(c);
  const s = getSelection();
  s.removeAllRanges();
  s.addRange(sel);
}

function setBlock(root, tag, below = false) {
  const r0 = caretRange(root);
  const keep = r0 ? [r0.startContainer, r0.endContainer, r0.startOffset] : null;
  ensureBlocks(root);
  if (!root.firstChild) { const d = document.createElement("div"); d.appendChild(document.createElement("br")); root.appendChild(d); }
  let a = keep && keep[0] !== root ? topOf(root, keep[0]) : root.childNodes[Math.min(keep ? keep[2] : 0, root.childNodes.length - 1)];
  let b = keep && keep[1] !== root ? topOf(root, keep[1]) : a;
  if (!a) a = root.lastChild;
  if (!b) b = a;
  const sources = [];
  for (let n = a; n; n = n.nextSibling) { sources.push(n); if (n === b) break; }
  const want = tag.toUpperCase();
  if (sources.every((n) => n.tagName === want)) tag = "div";
  const lines = []; // [childNodes[], plain text] per line
  for (const el of sources) {
    if (el.tagName === "PRE") for (const l of (el.innerText || el.textContent).replace(/\n+$/, "").split("\n")) lines.push([[document.createTextNode(l)], l]);
    else if (el.tagName === "BLOCKQUOTE") { ensureBlocks(el); for (const c of [...el.children]) lines.push([[...c.childNodes], c.textContent]); }
    else if (el.tagName === "UL" || el.tagName === "OL") for (const li of [...el.children]) lines.push([[...li.childNodes], li.textContent]);
    else lines.push([[...el.childNodes], el.textContent]);
  }
  const made = [];
  const fill = (el, nodes) => { nodes.forEach((n) => el.appendChild(n)); if (!el.firstChild) el.appendChild(document.createElement("br")); return el; };
  if (tag === "pre") {
    const pre = document.createElement("pre");
    pre.textContent = lines.map((l) => l[1]).join("\n");
    if (!pre.textContent) pre.appendChild(document.createElement("br"));
    made.push(pre);
  } else if (tag === "blockquote") {
    const q = document.createElement("blockquote");
    for (const [nodes] of lines) q.appendChild(fill(document.createElement("div"), nodes));
    made.push(q);
  } else for (const [nodes] of lines) made.push(fill(document.createElement(tag), nodes));
  for (const el of made) root.insertBefore(el, sources[0]);
  sources.forEach((n) => n.remove());
  const last = made[made.length - 1];
  // A quote or code block at the very end gets an empty line under it, so there is always a way out of the block
  // (click below it, press the down arrow, or Enter on an empty line).
  const emptyLine = (n) => n && n.tagName === "DIV" && !n.textContent.trim();
  if ((tag === "pre" || tag === "blockquote") && (!last.nextSibling || (below && !emptyLine(last.nextSibling)))) {
    const d = document.createElement("div");
    d.appendChild(document.createElement("br"));
    last.after(d);
  }
  // From the menu with text in it, the caret moves to the empty line under the new code block / quote.
  if (below && (tag === "pre" || tag === "blockquote") && last.textContent.trim() && last.nextSibling) caretIn(last.nextSibling, false);
  else caretIn(last.tagName === "BLOCKQUOTE" ? last.lastChild : last);
}

// Leave a quote / code block / heading: a new plain line right after it.
function exitBlock(el) {
  const d = document.createElement("div");
  d.appendChild(document.createElement("br"));
  el.after(d);
  if (!el.textContent.trim() && !el.querySelector("img")) el.remove();
  caretIn(d, false);
}

const closestBlock = (node, root) => {
  let n = node?.nodeType === 3 ? node.parentElement : node;
  while (n && n !== root) { if (["H1", "H2", "H3", "BLOCKQUOTE", "PRE"].includes(n.tagName)) return n; n = n.parentElement; }
  return null;
};

function blockOf(node, root) {
  let n = node?.nodeType === 3 ? node.parentElement : node;
  while (n && n !== root) {
    if (["H1", "H2", "H3", "BLOCKQUOTE", "PRE", "LI"].includes(n.tagName)) return n.tagName;
    n = n.parentElement;
  }
  return null;
}

// Floating toolbar over a selection inside the editor.
function Toolbar({ root, onChange }) {
  const t = useT();
  const [pos, setPos] = useState(null);
  const [menu, setMenu] = useState(false);
  const [link, setLink] = useState(null); // url being typed
  const saved = useRef(null);
  const bar = useRef(null);
  const [, force] = useState(0);
  useEffect(() => { // a press outside the toolbar closes its menu; outside the editor too, the toolbar itself
    const down = (e) => {
      if (bar.current && bar.current.contains(e.target)) return;
      setMenu(false);
      setLink(null);
      if (!root.current?.contains(e.target)) setPos(null);
    };
    document.addEventListener("mousedown", down);
    return () => document.removeEventListener("mousedown", down);
  }, [root]);
  useEffect(() => {
    const update = () => {
      if (link !== null) return;
      const r = caretRange(root.current);
      if (!r || r.collapsed) { setMenu(false); return setPos(null); }
      const rect = r.getBoundingClientRect();
      if (!rect.width && !rect.height) return setPos(null);
      setPos({ x: rect.left + rect.width / 2, y: rect.top });
      force((n) => n + 1);
    };
    document.addEventListener("selectionchange", update);
    return () => document.removeEventListener("selectionchange", update);
  }, [root, link, menu]);
  if (!pos) return null;
  const exec = (...cmd) => { root.current.focus(); document.execCommand(...cmd); onChange(); force((n) => n + 1); };
  const state = (c) => { try { return document.queryCommandState(c); } catch { return false; } };
  const cur = caretRange(root.current);
  const kind = cur ? blockOf(cur.startContainer, root.current) : null;
  const listKind = kind === "LI" ? (cur.startContainer.parentElement?.closest("ol") ? "ol" : "ul") : null;
  const curStyle = listKind || { H1: "h1", H2: "h2", H3: "h3", BLOCKQUOTE: "quote", PRE: "pre" }[kind] || "p";
  const code = () => { toggleCode(root.current); onChange(); force((n) => n + 1); };
  const btn = (on) => `grid h-7 w-7 place-items-center rounded-lg ${on ? "bg-active text-fg" : "text-muted hover:bg-hover hover:text-fg"}`;
  const keep = (e) => e.preventDefault();
  return (
    <div ref={bar} style={{ left: Math.min(Math.max(150, pos.x), innerWidth - 150), top: pos.y - 8 }} onMouseDown={keep}
      className="fade-in fixed z-50 flex -translate-x-1/2 -translate-y-full items-center gap-0.5 rounded-xl border border-line bg-elev p-1 shadow-xl">
      {link !== null ? (
        <div className="flex items-center gap-1 pl-1.5" onMouseDown={(e) => e.stopPropagation()}>
          <Link2 size={14} className="text-subtle" />
          <input autoFocus value={link} onChange={(e) => setLink(e.target.value)} placeholder="https://"
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                const s = getSelection(); s.removeAllRanges(); if (saved.current) s.addRange(saved.current);
                if (link.trim()) exec("createLink", false, /^\w+:/.test(link.trim()) ? link.trim() : `https://${link.trim()}`);
                setLink(null);
              }
              if (e.key === "Escape") setLink(null);
            }}
            className="w-56 bg-transparent px-1 text-[13px] outline-none" />
          <button onMouseDown={keep} onClick={() => setLink(null)} className={btn(false)}><X size={14} /></button>
        </div>
      ) : (
        <>
          <button title={`${t("fmt_link")} (Ctrl+K)`} onClick={() => { saved.current = caretRange(root.current)?.cloneRange(); setLink(""); }} className={btn(state("createLink"))}><Link2 size={15} /></button>
          <button title={`${t("fmt_bold")} (Ctrl+B)`} onClick={() => exec("bold")} className={btn(state("bold"))}><Bold size={15} /></button>
          <button title={`${t("fmt_italic")} (Ctrl+I)`} onClick={() => exec("italic")} className={btn(state("italic"))}><Italic size={15} /></button>
          <button title={`${t("fmt_strike")} (Ctrl+Shift+X)`} onClick={() => exec("strikeThrough")} className={btn(state("strikeThrough"))}><Strikethrough size={15} /></button>
          <button title={`${t("fmt_code")} (Ctrl+E)`} onClick={code} className={btn(false)}><Code size={15} /></button>
          <span className="mx-0.5 h-5 border-l border-line" />
          <div className="relative">
            <button onClick={() => setMenu(!menu)} className="flex h-7 items-center gap-1 rounded-lg px-2 text-[12.5px] text-muted hover:bg-hover hover:text-fg">
              {t(TEXT_STYLES.find((x) => x.id === curStyle)?.key || "fmt_text")}<ChevronDown size={12} />
            </button>
            {menu && (
              <div className={`fade-in absolute left-0 z-10 w-48 rounded-xl border border-line bg-elev p-1 shadow-xl ${pos.y + 300 > innerHeight ? "bottom-full mb-1.5" : "top-full mt-1.5"}`}>
                {TEXT_STYLES.map((s) => (
                  <button key={s.id} onClick={() => {
                    setMenu(false);
                    if ((s.id === "ol" || s.id === "ul") && listKind === s.id) return exec(...s.cmd); // toggles off
                    if (s.id === "p" && listKind) return exec(listKind === "ol" ? "insertOrderedList" : "insertUnorderedList");
                    if (s.id === "ol" || s.id === "ul") return exec(...s.cmd);
                    root.current.focus();
                    setBlock(root.current, s.id === "p" ? "div" : s.id === "quote" ? "blockquote" : s.id, true); // p, h1-h3, quote, pre
                    onChange();
                    force((n) => n + 1);
                  }}
                    className="flex w-full items-center justify-between rounded-lg px-2.5 py-1.5 text-left text-[13px] hover:bg-hover">
                    {t(s.key)}{curStyle === s.id && <Check size={14} className="text-accent" />}
                  </button>
                ))}
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}

const RichInput = forwardRef(function RichInput({ placeholder, onChange, onKeyDown, onPaste, onSubmit, names }, ref) {
  const root = useRef(null);
  const namesRef = useRef(names);
  namesRef.current = names;

  const emit = useCallback(() => {
    const el = root.current;
    if (!el) return;
    if (el.innerHTML === "<br>" || el.innerHTML === "<div><br></div>") el.innerHTML = "";
    const r = caretRange(el);
    let before = "";
    if (r && r.startContainer.nodeType === 3) before = r.startContainer.data.slice(0, r.startOffset);
    onChange?.(toMarkdown(el), before);
  }, [onChange]);

  const chipFor = (token) => {
    const chip = document.createElement("span");
    chip.className = `mention ${token[0] === "@" ? "mention-agent" : "mention-skill"}`;
    chip.contentEditable = "false";
    chip.textContent = token;
    return chip;
  };

  // A known @agent or /skill followed by a space becomes a chip; line-start Markdown shortcuts become blocks.
  const afterInput = () => {
    const r = caretRange(root.current);
    if (!r || !r.collapsed || r.startContainer.nodeType !== 3) return;
    const node = r.startContainer, off = r.startOffset;
    const before = node.data.slice(0, off);
    const m = before.match(/(^|\s)([@/])([\w-]+)\s$/);
    if (m && namesRef.current?.[m[2]]?.has(m[3])) {
      const start = off - m[0].length + m[1].length;
      const range = document.createRange();
      range.setStart(node, start);
      range.setEnd(node, off - 1);
      range.deleteContents();
      const chip = chipFor(m[2] + m[3]);
      range.insertNode(chip);
      const next = chip.nextSibling;
      if (next?.nodeType === 3) placeAfter(next, 1); else placeAfter(chip);
      return;
    }
    const atStart = !node.previousSibling || node.previousSibling.nodeName === "BR";
    if (!atStart) return;
    // "# ", "## ", "### ", "> ", "- ", "1. " at the start of a plain line (typed or pasted) and a lone ``` become
    // the block; the marker is removed, the rest of the line stays.
    if (closestBlock(node, root.current) || node.parentElement?.closest("li")) return;
    const text = before.split(String.fromCharCode(160)).join(" ");
    const short = [["### ", ["formatBlock", "h3"]], ["## ", ["formatBlock", "h2"]], ["# ", ["formatBlock", "h1"]], ["> ", ["formatBlock", "blockquote"]],
      ["- ", ["insertUnorderedList"]], ["* ", ["insertUnorderedList"]], ["1. ", ["insertOrderedList"]], ["1) ", ["insertOrderedList"]]];
    const hit = text === "```" ? ["```", ["formatBlock", "pre"]] : short.find(([mark]) => text.startsWith(mark));
    if (!hit) return;
    const range = document.createRange();
    range.setStart(node, 0);
    range.setEnd(node, hit[0].length);
    range.deleteContents();
    if (hit[1][0] === "formatBlock") setBlock(root.current, hit[1][1]);
    else {
      placeAfter(node, node.data.length);
      // This runs inside the input event of another execCommand (paste / insertText): a nested call is refused by the
      // browser ("called recursively"), so it runs right after that one ends.
      setTimeout(() => { document.execCommand(...hit[1]); emit(); }, 0);
    }
  };

  useImperativeHandle(ref, () => ({
    focus: () => { root.current?.focus(); const s = getSelection(); if (root.current && !caretRange(root.current)) { s.selectAllChildren(root.current); s.collapseToEnd(); } },
    clear: () => { if (root.current) root.current.innerHTML = ""; emit(); },
    getMarkdown: () => (root.current ? toMarkdown(root.current) : ""),
    // Plain text (dictation, prefixes, voice) replaces the content; known mentions become chips.
    setText: (text) => {
      const el = root.current;
      if (!el) return;
      el.innerHTML = esc(text).replace(/(^|\s)([@/])([\w-]+)/g, (m, sp, sig, name) =>
        namesRef.current?.[sig]?.has(name) ? `${sp}<span class="mention ${sig === "@" ? "mention-agent" : "mention-skill"}" contenteditable="false">${sig}${name}</span>` : m)
        .replace(/\n/g, "<br>");
      el.focus();
      const s = getSelection(); s.selectAllChildren(el); s.collapseToEnd();
      emit();
    },
    insertText: (text, atEnd = true) => {
      const el = root.current;
      if (!el) return;
      el.focus();
      if (atEnd || !caretRange(el)) { const s = getSelection(); s.selectAllChildren(el); s.collapseToEnd(); }
      document.execCommand("insertText", false, text);
      emit();
    },
    // Autocomplete picked an agent/skill: the typed "@na" before the caret becomes the chip.
    insertMention: (sig, name) => {
      const el = root.current;
      el.focus();
      const r = caretRange(el);
      if (r && r.startContainer.nodeType === 3) {
        const node = r.startContainer, off = r.startOffset;
        const m = node.data.slice(0, off).match(/([@/])([\w-]*)$/);
        if (m) {
          const range = document.createRange();
          range.setStart(node, off - m[0].length);
          range.setEnd(node, off);
          range.deleteContents();
          const chip = chipFor(sig + name);
          range.insertNode(chip);
          const sp = document.createTextNode(" ");
          chip.after(sp);
          placeAfter(sp, 1);
          emit();
          return;
        }
      }
      if (!r) { const s = getSelection(); s.selectAllChildren(el); s.collapseToEnd(); }
      const chip = chipFor(sig + name);
      const range = caretRange(el);
      range.insertNode(chip);
      const sp = document.createTextNode(" ");
      chip.after(sp);
      placeAfter(sp, 1);
      emit();
    },
  }), [emit]);

  const keyDown = (e) => {
    onKeyDown?.(e);
    if (e.defaultPrevented) return;
    const k = e.key.toLowerCase();
    const mod = e.ctrlKey || e.metaKey;
    if (mod && !e.shiftKey && k === "e") { e.preventDefault(); toggleCode(root.current); return emit(); }
    if (mod && e.shiftKey && k === "x") { e.preventDefault(); document.execCommand("strikeThrough"); return emit(); }
    if (mod && e.shiftKey && (k === "7" || e.code === "Digit7")) { e.preventDefault(); document.execCommand("insertOrderedList"); return emit(); }
    if (mod && e.shiftKey && (k === "8" || e.code === "Digit8")) { e.preventDefault(); document.execCommand("insertUnorderedList"); return emit(); }
    if (mod && k === "k") {
      e.preventDefault();
      const url = prompt("URL", "https://");
      if (url) { document.execCommand("createLink", false, url); emit(); }
      return;
    }
    if (mod && k === "u") { e.preventDefault(); return; } // no underline in Markdown
    if (e.key === "ArrowDown" && !mod && !e.shiftKey) { // down arrow on the last line of the last block: leave it
      const r = caretRange(root.current);
      const blk = r && closestBlock(r.startContainer, root.current);
      if (blk && !blk.nextSibling) {
        const after = document.createRange();
        after.selectNodeContents(blk);
        after.setStart(r.endContainer, r.endOffset);
        if (!after.toString().includes(String.fromCharCode(10)) && !(blk.tagName === "BLOCKQUOTE" && topOf(blk, r.startContainer)?.nextSibling)) {
          e.preventDefault();
          exitBlock(blk);
          return emit();
        }
      }
    }
    if (e.key === "Enter" && !e.nativeEvent.isComposing) {
      const r = caretRange(root.current);
      const blk = r && closestBlock(r.startContainer, root.current);
      if (blk && !mod && !e.shiftKey) {
        // Inside a heading, quote or code block Enter stays in the editor: a new line in the block; on an empty
        // line (a second Enter) it leaves the block. Ctrl+Enter sends.
        e.preventDefault();
        if (blk.tagName === "PRE") {
          const before = document.createRange();
          before.selectNodeContents(blk);
          before.setEnd(r.startContainer, r.startOffset);
          const after = document.createRange();
          after.selectNodeContents(blk);
          after.setStart(r.endContainer, r.endOffset);
          if ((before.toString().endsWith("\n") || !before.toString()) && !after.toString().trim()) {
            blk.textContent = blk.textContent.replace(/\n+$/, "");
            exitBlock(blk);
          } else {
            r.deleteContents();
            const nl = document.createTextNode("\n");
            r.insertNode(nl);
            if (!after.toString().length || !nl.nextSibling || (nl.nextSibling.nodeType === 3 && !nl.nextSibling.data)) blk.appendChild(document.createTextNode("\n"));
            placeAfter(nl, 1);
          }
        } else if (blk.tagName === "BLOCKQUOTE") {
          ensureBlocks(blk);
          const line = topOf(blk, r.startContainer === blk ? blk.lastChild : r.startContainer) || blk.lastChild;
          if (line && !line.textContent.trim()) { line.remove(); exitBlock(blk); } else {
            const d = document.createElement("div");
            const tail = document.createRange();
            tail.selectNodeContents(line);
            tail.setStart(r.endContainer, r.endOffset);
            d.appendChild(tail.extractContents());
            if (!d.textContent) d.replaceChildren(document.createElement("br"));
            if (!line.firstChild) line.appendChild(document.createElement("br"));
            line.after(d);
            caretIn(d, false);
          }
        } else exitBlock(blk); // headings: one line, Enter returns to text
        return emit();
      }
      const inBlock = r && blockOf(r.startContainer, root.current);
      if (mod) { e.preventDefault(); return onSubmit?.(); }
      if (!e.shiftKey && !inBlock) { e.preventDefault(); return onSubmit?.(); }
      if (e.shiftKey && !inBlock) { e.preventDefault(); document.execCommand("insertLineBreak"); return emit(); }
    }
  };

  const paste = (e) => {
    onPaste?.(e);
    if (e.defaultPrevented) return;
    e.preventDefault();
    // Plain text keeps line breaks; formulas and Markdown are sent as written and render in the chat.
    const text = e.clipboardData.getData("text/plain");
    if (text) document.execCommand("insertText", false, text);
    emit();
  };

  return (
    <div className="relative">
      <div ref={root} contentEditable suppressContentEditableWarning role="textbox" aria-multiline="true"
        data-placeholder={placeholder} spellCheck={false}
        onInput={(e) => {
          // Deleting everything also removes the last empty heading / quote / code block (the browser keeps it).
          const el = root.current;
          if (String(e.nativeEvent.inputType || "").startsWith("delete") && !el.textContent.replace(/[\u200b\u00a0\s]/g, "") && !el.querySelector("img, .mention")) {
            el.innerHTML = ""; // nothing left: no empty code / heading / quote stays to catch the next typing
            getSelection().removeAllRanges();
            const r = document.createRange(); r.setStart(el, 0); r.collapse(true); getSelection().addRange(r);
          }
          afterInput(); emit();
        }} onKeyDown={keyDown} onKeyUp={emit} onMouseUp={emit} onPaste={paste}
        className="rich-input max-h-[360px] min-h-[72px] w-full overflow-y-auto px-4 pb-1.5 pt-4 text-[15px] leading-6" />
      <Toolbar root={root} onChange={emit} />
    </div>
  );
});

export default RichInput;
