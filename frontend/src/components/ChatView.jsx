import { memo, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";

import { liveFiles } from "../lib/changes";
import { ArrowDown, Brain, Check, ListChecks, Copy, CornerDownRight, FileUp, Folder, Laptop, Loader2, MessageSquarePlus, MessageSquareText, RotateCw, ShieldAlert, Square, Trash2, Volume2 } from "lucide-react";
import TaskBoard from "./TaskBoard";
import ChangesCard from "./ChangesCard";
import { onSpeech, speak, speakingId, speechOpts, speechSupported, stopSpeech } from "../lib/speech";
import { useStore, useT } from "../lib/store";
import Markdown from "./Markdown";
import ActivityTrace, { DiffView, shotsOf } from "./ActivityTrace";
import Composer from "./Composer";
import { Thinking, Logo } from "./Brand";
import { FileChip } from "./ui";
import { ErrorNote } from "./Feedback";
import TodoList from "./TodoList";
import { DocCard } from "./DocPreview";
import OutputGallery from "./OutputGallery";

// Screenshots already show inline in the step trace, so the gallery under the answer leaves them out.
const withoutShots = (outputs, steps) => {
  const shots = new Set(shotsOf(steps).map((s) => s.data.screenshot));
  return shots.size ? (outputs || []).filter((p) => !shots.has(p)) : outputs;
};

// What a file write will change, shown before the user decides: new file, overwrite, edit or deletion.
function ChangePreview({ p }) {
  const t = useT();
  const [full, setFull] = useState(false);
  return (
    <div>
      <div className="mb-1.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs">
        <span className={`rounded-md px-1.5 py-0.5 font-medium ${p.kind === "delete" ? "bg-danger/10 text-danger" : p.kind === "new" ? "bg-ok/10 text-ok" : "bg-accent-soft text-accent"}`}>
          {t(`preview_${p.kind}`)}</span>
        <span className="min-w-0 truncate font-mono text-muted" title={p.path}>{p.path}</span>
        {!p.binary && <span className="font-mono tabular-nums"><span className="text-ok">+{p.added}</span> <span className="text-danger">−{p.removed}</span></span>}
        {p.diff && <button onClick={() => setFull(!full)} className="ml-auto text-accent hover:underline">{t(full ? "preview_collapse" : "preview_expand")}</button>}
      </div>
      {p.binary ? <div className="rounded-xl bg-elev p-2.5 text-xs text-muted">{t("preview_binary")}</div>
        : p.diff ? <DiffView diff={p.diff} height={full ? "max-h-[70vh]" : "max-h-72"} />
        : <div className="rounded-xl bg-elev p-2.5 text-xs text-muted">{t("preview_empty")}</div>}
      {p.truncated && <div className="mt-1 text-[11px] text-subtle">{t("preview_truncated")}</div>}
    </div>
  );
}

const Approval = memo(function Approval({ sid, a }) {
  const t = useT();
  const op = a.op || {};
  const label = t(`appr_${a.category}`);
  const category = label.startsWith("appr_") ? a.category : label;
  return (
    <div className="fade-in my-2 rounded-2xl border border-warn/40 bg-warn/10 p-3 text-[13px]">
      <div className="mb-1.5 flex items-center gap-1.5 font-semibold text-warn"><ShieldAlert size={15} /> {t("approval_needed")} · {category}</div>
      {a.preview ? <ChangePreview p={a.preview} /> : (
        <pre className="max-h-48 overflow-auto whitespace-pre-wrap rounded-xl bg-elev p-2.5 font-mono text-xs">
          {op.command || op.path || op.url || op.query || JSON.stringify(op, null, 2)}
        </pre>
      )}
      {op.cwd && <div className="mt-1 truncate font-mono text-[11px] text-subtle">{op.cwd}</div>}
      <div className="mt-2.5 flex gap-2">
        <button onClick={() => useStore.getState().answerApproval(sid, a, true)} className="rounded-xl bg-accent px-3.5 py-1.5 font-medium text-accent-fg">{t("approve")}</button>
        <button onClick={() => useStore.getState().answerApproval(sid, a, false)} className="rounded-xl border border-line bg-elev px-3.5 py-1.5 hover:bg-hover">{t("deny")}</button>
      </div>
    </div>
  );
});

// Documents the run generated (make_doc), shown as clickable cards under the answer.
const docsOf = (steps) => [...new Set((steps || []).filter((s) => s.status === "done" && s.data?.tool === "make_doc" && s.data.path)
  .map((s) => s.data.path))];

// Read an answer aloud (browser speech synthesis); a second click stops it.
function SpeakButton({ m }) {
  const t = useT();
  const [on, setOn] = useState(speakingId() === m.id);
  useEffect(() => onSpeech((id) => setOn(id === m.id)), [m.id]);
  if (!speechSupported() || !m.content) return null;
  const prefs = useStore.getState().prefs;
  return (
    <button onClick={() => (on ? stopSpeech() : speak(m.id, m.content, speechOpts(prefs)))}
      title={t(on ? "voice_stop" : "voice_read")}
      className={`grid h-7 w-7 place-items-center rounded-lg hover:bg-hover ${on ? "text-accent" : "text-subtle hover:text-fg"}`}>
      {on ? <Square size={12} fill="currentColor" /> : <Volume2 size={14} />}
    </button>
  );
}

// Copy / delete (and read aloud) under every message; shown on hover, always on touch screens.
function MessageActions({ m, align = "start" }) {
  const t = useT();
  const [copied, setCopied] = useState(false);
  const busy = useStore((s) => !!s.runs[s.sessionId] && m.role === "user" && s.messages.at(-1) === m);
  const copy = async () => {
    try { await navigator.clipboard.writeText(m.content || ""); setCopied(true); setTimeout(() => setCopied(false), 1400); } catch {}
  };
  const btn = "grid h-7 w-7 place-items-center rounded-lg text-subtle hover:bg-hover hover:text-fg";
  return (
    <div className={`msg-actions mt-1 flex items-center gap-0.5 ${align === "end" ? "justify-end" : ""}`}>
      {m.content && <button onClick={copy} title={t("copy")} className={btn}>{copied ? <Check size={14} className="text-ok" /> : <Copy size={14} />}</button>}
      {m.role === "assistant" && <SpeakButton m={m} />}
      <button onClick={() => useStore.getState().deleteMessage(m)} disabled={busy}
        title={t("delete")} className={`${btn} hover:!text-danger disabled:opacity-30`}><Trash2 size={14} /></button>
      <button onClick={() => useStore.getState().startSelect(m)}
        title={t("select_messages")} className={btn}><ListChecks size={14} /></button>
    </div>
  );
}

// A message sent while a task was running: it steers that task (no new task). Marked as such, with its state:
// waiting until the model picks it up at its next step, then applied.
function SteerMessage({ m }) {
  const t = useT();
  const applied = useStore((s) => {
    const r = s.runs[s.sessionId];
    if (!r || !["running", "starting"].includes(r.status)) return true;
    const text = (m.content || "").trim();
    return (r.steps || []).some((x) => x.kind === "note" && x.title === "steer" && (x.detail || "").trim() === text);
  });
  return (
    <div className="msg flex flex-col items-end gap-1" data-mid={m.id}>
      <div className="max-w-[90%] overflow-hidden rounded-2xl rounded-br-md border border-accent/35 bg-accent-soft/50 sm:max-w-[80%]">
        <div className="flex items-center gap-1.5 border-b border-accent/20 px-3.5 py-1 text-[11px] font-semibold uppercase tracking-wide text-accent">
          <CornerDownRight size={12} />{t("steer_label")}
          <span className={`ml-auto flex items-center gap-1 rounded-full px-1.5 py-px text-[10px] normal-case tracking-normal ${applied ? "bg-ok/15 text-ok" : "bg-accent/15 text-accent"}`}>
            {applied ? <><Check size={10} />{t("steer_state_applied")}</> : <><Loader2 size={10} className="animate-spin" />{t("steer_state_waiting")}</>}
          </span>
        </div>
        <div className="msg-body px-3.5 py-2"><Markdown text={m.content} mentions /></div>
      </div>
      <MessageActions m={m} align="end" />
    </div>
  );
}

// Errors a "continue" can get past (a stalled or busy provider); quota, payment or key problems need the user first.
const RESUMABLE = new Set(["timeout", "unavailable", "server", "bad_gateway", "overloaded", "rate_limit", "network", "internal", "empty"]);

const Message = memo(function Message({ m, last }) {
  const t = useT();
  if (m.role === "user" && m.meta?.steer) return <SteerMessage m={m} />;
  if (m.role === "user") {
    const atts = m.meta?.attachments || [];
    return (
      <div className="msg flex flex-col items-end gap-1.5" data-mid={m.id}>
        {atts.length > 0 && <div className="flex max-w-[90%] flex-wrap justify-end gap-1.5">{atts.map((a, i) => <FileChip key={i} file={a} compact />)}</div>}
        <div className="msg-body max-w-[90%] rounded-3xl rounded-br-lg bg-hover px-4 py-2.5 sm:max-w-[80%]">
          <Markdown text={m.content} mentions />
        </div>
        <MessageActions m={m} align="end" />
      </div>
    );
  }
  return (
    <div className="msg" data-mid={m.id}>
      <ActivityTrace steps={m.meta?.steps} timing={m.meta?.timing} />
      <TaskBoard steps={m.meta?.steps} />
      {m.content && <div className="msg-body"><Markdown text={m.content} /></div>}
      <TodoList todos={m.meta?.todos} />
      {docsOf(m.meta?.steps).length > 0 && <div className="mt-3 flex flex-wrap gap-2">{docsOf(m.meta.steps).map((p) => <DocCard key={p} path={p} />)}</div>}
      <OutputGallery paths={withoutShots(m.meta?.outputs, m.meta?.steps)} steps={m.meta?.steps} />
      {m.meta?.changes?.files?.length > 0 && <ChangesCard changes={m.meta.changes} steps={m.meta?.steps} />}
      {m.meta?.error && <ErrorNote code={m.meta.errorCode} message={m.meta.error} />}
      {m.meta?.status === "cancelled" && <div className="text-[13px] text-subtle">{t("cancelled")}</div>}
      {last && (["interrupted", "budget", "cancelled"].includes(m.meta?.status)
        || (m.meta?.status === "error" && RESUMABLE.has(m.meta?.errorCode))) && (
        <button onClick={() => useStore.getState().send(t("continue_prompt"))}
          className="mt-2 inline-flex items-center gap-1.5 rounded-xl border border-line bg-elev px-3 py-1.5 text-[13px] font-medium hover:border-accent hover:text-accent">
          <RotateCw size={13} /> {t("resume_task")}
        </button>
      )}
      <MessageActions m={m} />
    </div>
  );
});

// Select mode (the "select" button under a message): a checkbox at every message, a click anywhere on one toggles it.
// Messages still being saved (a live id) cannot be picked until the chat reloads them.
function Selectable({ m, children }) {
  const sel = useStore((s) => s.msgSel);
  if (!sel) return children;
  const ok = typeof m.id === "number";
  const picked = sel.has(m.id);
  return (
    <div onClick={async () => { if (ok) return useStore.getState().toggleSel("msgSel", m.id); await useStore.getState().syncIds(useStore.getState().sessionId); }}
      className={`-mx-2 flex cursor-pointer gap-2 rounded-2xl px-2 py-1 transition ${picked ? "bg-accent-soft/60 ring-1 ring-accent/40" : "hover:bg-hover/60"} ${ok ? "" : "opacity-60"}`}>
      <span className={`mt-2 grid h-[18px] w-[18px] shrink-0 place-items-center rounded-md border ${picked ? "border-accent bg-accent text-accent-fg" : "border-line bg-elev"}`}>
        {picked && <Check size={12} strokeWidth={3} />}
      </span>
      <div className="pointer-events-none min-w-0 flex-1 select-none [&_.msg-actions]:hidden">{children}</div>
    </div>
  );
}

// The bar of select mode: how many are picked, select all / none, delete the selection, delete the whole chat
// history (messages, summaries, saved progress), cancel.
function SelectBar({ messages }) {
  const t = useT();
  const sel = useStore((s) => s.msgSel);
  if (!sel) return null;
  const st = useStore.getState();
  const ids = messages.map((m) => m.id).filter((x) => typeof x === "number");
  const all = sel.size === ids.length && ids.length > 0;
  return (
    <div className="sticky top-2 z-20 mb-3 flex flex-wrap items-center gap-1.5 rounded-2xl border border-line bg-elev/95 px-3 py-2 text-[12.5px] shadow-lg backdrop-blur">
      <span className="mr-auto font-medium">{t("selected_n", { n: sel.size })}</span>
      <button onClick={() => useStore.setState({ msgSel: all ? new Set() : new Set(ids) })} className="rounded-lg px-2 py-1 hover:bg-hover">{t(all ? "select_none" : "select_all")}</button>
      <button onClick={() => st.deleteMessages(false)} disabled={!sel.size}
        className="flex items-center gap-1 rounded-lg bg-danger/10 px-2 py-1 font-medium text-danger hover:bg-danger/20 disabled:opacity-40"><Trash2 size={13} />{t("delete_selected")}</button>
      <button onClick={() => st.deleteMessages(true)} className="rounded-lg px-2 py-1 text-danger hover:bg-danger/10">{t("delete_all_messages")}</button>
      <button onClick={() => useStore.setState({ msgSel: null })} className="rounded-lg px-2 py-1 text-muted hover:bg-hover">{t("cancel")}</button>
    </div>
  );
}

// Text selected in a message: a floating "Add to chat" button; with an optional comment it becomes a quote that
// goes with the next message. It closes when the selection goes away or on a click elsewhere.
function SelectionAsk({ root }) {
  const t = useT();
  const [sel, setSel] = useState(null); // { text, messageId, x, y }
  const [commenting, setCommenting] = useState(false);
  const [comment, setComment] = useState("");
  const box = useRef(null);
  const read = useCallback(() => {
    const s = getSelection();
    if (!s || s.isCollapsed || !s.rangeCount) return null;
    const text = s.toString().trim();
    const a = s.anchorNode?.parentElement?.closest?.("[data-mid]"), f = s.focusNode?.parentElement?.closest?.("[data-mid]");
    if (!text || !a || a !== f || !root.current?.contains(a)) return null;
    const r = s.getRangeAt(0).getBoundingClientRect();
    return { text: text.slice(0, 4000), messageId: a.dataset.mid, x: r.left + r.width / 2, y: r.top };
  }, [root]);
  useEffect(() => {
    const el = root.current;
    const up = () => setTimeout(() => { if (!commenting) setSel(read()); }, 0);
    const change = () => { if (!commenting && getSelection()?.isCollapsed) setSel(null); };
    const down = (e) => {
      if (box.current && !box.current.contains(e.target)) { if (commenting) setSel(null); setCommenting(false); setComment(""); }
    };
    const esc = (e) => { if (e.key === "Escape") { setSel(null); setCommenting(false); } };
    const scroll = () => { if (!commenting) setSel(null); };
    el?.addEventListener("mouseup", up);
    el?.addEventListener("keyup", up);
    el?.addEventListener("scroll", scroll);
    document.addEventListener("selectionchange", change);
    document.addEventListener("mousedown", down);
    document.addEventListener("keydown", esc);
    return () => {
      el?.removeEventListener("mouseup", up); el?.removeEventListener("keyup", up); el?.removeEventListener("scroll", scroll);
      document.removeEventListener("selectionchange", change); document.removeEventListener("mousedown", down);
      document.removeEventListener("keydown", esc);
    };
  }, [read, commenting, root]);
  if (!sel) return null;
  const add = () => {
    useStore.getState().addQuote({ text: sel.text, comment: comment.trim(), messageId: sel.messageId });
    setSel(null); setCommenting(false); setComment("");
    getSelection()?.removeAllRanges();
    dispatchEvent(new CustomEvent("aiiq:focus-composer"));
  };
  const left = Math.min(Math.max(12, sel.x), innerWidth - 12);
  return (
    <div ref={box} style={{ left, top: Math.max(8, sel.y - 8) }} onMouseDown={(e) => { if (!commenting) e.preventDefault(); }}
      className="fade-in fixed z-50 -translate-x-1/2 -translate-y-full">
      {commenting ? (
        <div className="flex w-[min(360px,90vw)] items-center gap-1.5 rounded-2xl border border-line bg-elev p-1.5 pl-3 shadow-xl">
          <input autoFocus value={comment} onChange={(e) => setComment(e.target.value)} placeholder={t("quote_comment_ph")}
            onKeyDown={(e) => { if (e.key === "Enter") add(); }} className="min-w-0 flex-1 bg-transparent text-[13px] outline-none placeholder:text-subtle" />
          <button onClick={add} title={t("add_to_chat")} className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-fg text-bg"><Check size={14} /></button>
        </div>
      ) : (
        <div className="flex items-center overflow-hidden rounded-xl border border-line bg-elev text-[12.5px] shadow-xl">
          <button onClick={add} className="flex items-center gap-1.5 px-2.5 py-1.5 font-medium hover:bg-hover"><MessageSquarePlus size={14} />{t("add_to_chat")}</button>
          <span className="h-5 border-l border-line" />
          <button onClick={() => setCommenting(true)} className="px-2.5 py-1.5 text-muted hover:bg-hover hover:text-fg">{t("add_comment")}</button>
        </div>
      )}
    </div>
  );
}

// A quote chip in the message box was clicked: its message scrolls into view and the quoted words blink.
function findRange(body, text) {
  const walker = document.createTreeWalker(body, NodeFilter.SHOW_TEXT);
  const nodes = [];
  let all = "";
  for (let n = walker.nextNode(); n; n = walker.nextNode()) { nodes.push([n, all.length]); all += n.data; }
  // compare with whitespace collapsed; map each kept character back to its raw index
  let hay = "";
  const map = [];
  for (let i = 0; i < all.length; i++) {
    const ws = /\s/.test(all[i]);
    if (ws && hay.endsWith(" ")) continue;
    map.push(i);
    hay += ws ? " " : all[i];
  }
  const needle = text.replace(/\s+/g, " ").trim().slice(0, 300);
  const at = hay.indexOf(needle);
  if (at < 0 || !needle) return null;
  const startRaw = map[at], endRaw = map[at + needle.length - 1];
  const pos = (raw) => { for (let k = nodes.length - 1; k >= 0; k--) if (nodes[k][1] <= raw) return [nodes[k][0], raw - nodes[k][1]]; return null; };
  const a = pos(startRaw), b = pos(endRaw);
  if (!a || !b) return null;
  const r = new Range();
  r.setStart(a[0], a[1]);
  r.setEnd(b[0], Math.min(b[1] + 1, b[0].data.length));
  return r;
}

function useFlash(root) {
  const flash = useStore((s) => s.flash);
  useEffect(() => {
    if (!flash || !root.current) return;
    const el = root.current.querySelector(`[data-mid="${CSS.escape(String(flash.messageId))}"]`);
    if (!el) return;
    el.scrollIntoView({ behavior: "smooth", block: "center" });
    const body = el.querySelector(".msg-body") || el;
    body.classList.remove("flash-msg");
    void body.offsetWidth;
    body.classList.add("flash-msg");
    const hl = window.CSS?.highlights && window.Highlight;
    const range = hl ? findRange(body, flash.text) : null;
    let on = true, n = 0;
    const tick = () => {
      if (range) { if (on) CSS.highlights.set("aiiq-flash", new Highlight(range)); else CSS.highlights.delete("aiiq-flash"); }
      on = !on; n += 1;
    };
    tick();
    const iv = setInterval(() => { tick(); if (n > 7) { clearInterval(iv); if (range) CSS.highlights.set("aiiq-flash", new Highlight(range)); } }, 380);
    const off = setTimeout(() => { if (hl) CSS.highlights.delete("aiiq-flash"); body.classList.remove("flash-msg"); }, 6000);
    return () => { clearInterval(iv); clearTimeout(off); if (hl) CSS.highlights.delete("aiiq-flash"); };
  }, [flash, root]);
}

// The app's own action record ("[Tool actions in this turn ...]") that a model sometimes copies: never shown.
const ACTION_ECHO = /\[Tool actions in this turn[^\]]*\]/g;

// Everything the model writes while a task runs (notes before tool calls, the reply as it streams) is shown in ONE
// fixed slot under the steps. When a note moves into the step list the slot keeps showing the same text, so nothing
// jumps or blinks, even with very fast models; the reply takes its full place when the task ends.
function LiveNote({ text, thought = false }) {
  const long = text.length > 420 || text.split("\n").length > 7;
  const Icon = thought ? Brain : MessageSquareText;
  return (
    <div className="-mt-0.5 mb-1 ml-[7px] flex gap-2 border-l border-line py-1 pl-[17px]">
      <Icon size={13} className={`mt-[5px] shrink-0 ${thought ? "text-accent/70" : "text-subtle"}`} />
      <div className={`note-md min-w-0 flex-1 ${thought ? "note-thought" : ""} ${long ? "note-tail" : ""}`}>
        <Markdown text={text.trim()} live />
      </div>
    </div>
  );
}

// A provider error the app is waiting out (rate limit, overload, server error): shown at once in the chat with the
// reason and a countdown, not only as a folded step, so a waiting task never looks frozen.
function RetryNotice({ step }) {
  const t = useT();
  const d = step.data || {};
  const end = useRef(0);
  const [, tick] = useState(0);
  if (!end.current) end.current = Date.now() + (d.seconds || 0) * 1000;
  useEffect(() => { const i = setInterval(() => tick((n) => n + 1), 1000); return () => clearInterval(i); }, []);
  const left = Math.max(0, Math.ceil((end.current - Date.now()) / 1000));
  const k = `cd_${step.title}`;
  const label = t(k) === k ? step.title : t(k);
  return (
    <div className="fade-in my-2 rounded-2xl border border-warn/40 bg-warn/10 px-3.5 py-2.5 text-[13px]">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 font-medium text-warn">
        <RotateCw size={14} className="animate-spin [animation-duration:2.5s]" />
        <span>{label}</span>
        <span className="font-normal text-muted">{t("retry_notice", { s: left, n: d.attempt || 1 })}</span>
      </div>
      {step.detail && <div className="mt-1 line-clamp-3 break-words font-mono text-[11.5px] leading-snug text-muted">{step.detail}</div>}
    </div>
  );
}

// Files the running task has written so far (live; the full review card with diffs comes when it ends).
// The same counts as the review card (the sum of each operation), and the full diff view, which follows the task.
// The same grouped card as the final review, filled from the running task's steps and updated with each operation.
function LiveChanges({ steps }) {
  const list = useMemo(() => liveFiles(steps), [steps]);
  const changes = useMemo(() => ({ files: list }), [list]);
  if (!list.length) return null;
  return <div className="fade-in"><ChangesCard changes={changes} steps={steps} live /></div>;
}

// One readable line of progress from the reasoning being written: the last COMPLETE sentence (a sliding window of
// characters started mid-word and read like nonsense). The sentence still being written is not shown.
function lastSentence(text) {
  const clean = (s) => {
    // A sentence cut out of "(*... text.)*" keeps stray wrappers: dropped (the Markdown view closes real ones).
    s = s.replace(/^[-*#>\d.)\s(_]+/, "").replace(/[*_\s]+$/, "").trim();
    if ((s.match(/\(/g) || []).length < (s.match(/\)/g) || []).length) s = s.replace(/\)+$/, "");
    return s;
  };
  const tail = (text.match(/[^.!?\n]*$/) || [""])[0]; // the sentence being written now
  const done = text.slice(0, text.length - tail.length);
  const parts = done.split(/(?<=[.!?])\s+|\n+/).map(clean).filter((s) => s.length > 3);
  // Enough of the end to read: the last finished sentences up to ~160 characters (one short line like "Better:"
  // alone said nothing), then the start of the sentence being written, so it reads like a live stream.
  const picked = [];
  for (let i = parts.length - 1; i >= 0 && picked.join(" ").length < 160 && picked.length < 3; i--) picked.unshift(parts[i]);
  let s = picked.join(" ");
  const now = clean(tail);
  if (now.length > 20) s = (s ? s + " " : "") + now + "…";
  return s.length > 360 ? "…" + s.slice(-357) : s;
}

// Only this component re-renders while a run streams.
// A long answer is parsed as Markdown again for every update: at 60 updates a second that grew slower with every
// paragraph (the whole text, each frame). Long texts are redrawn a few times a second instead; short ones at once.
function useThrottled(value, ms) {
  const [shown, setShown] = useState(value);
  const last = useRef(0);
  useEffect(() => {
    const wait = ms - (Date.now() - last.current);
    if (wait <= 0) { last.current = Date.now(); setShown(value); return undefined; }
    const timer = setTimeout(() => { last.current = Date.now(); setShown(value); }, wait);
    return () => clearTimeout(timer);
  }, [value, ms]);
  return ms > 0 ? shown : value;
}

function LiveRun({ sid }) {
  const live = useStore((s) => s.runs[sid]);
  const n = live?.text?.length || 0;
  const shownText = useThrottled(live?.text || "", n > 12000 ? 350 : n > 4000 ? 160 : 0);
  if (!live) return null;
  const run = shownText === live.text ? live : { ...live, text: shownText };
  const waiting = [...run.steps].reverse().find((x) => x.kind === "retry" && x.status === "running");
  const running = run.steps.some((x) => x.status === "running");
  const lastNote = [...run.steps].reverse().find((x) => x.kind === "note" && x.detail);
  // The slot shows the streaming text, else the latest note, else ONE line of progress: the last sentence of the
  // reasoning being written now. (The whole tail repeated here drew the same growing text twice.)
  const thinking = [...run.steps].reverse().find((x) => x.kind === "thinking" && x.status === "running" && x.detail);
  const progress = thinking ? lastSentence(thinking.detail) : "";
  const text = (run.text || "").replace(ACTION_ECHO, "").trim();
  // A conversation reply (small talk, a plain question) streams straight into the chat as the answer, as long as no
  // tool ran; tool work keeps everything in the slot under the steps.
  const tooled = run.steps.some((x) => !["thinking", "prepare", "retry", "fallback", "compress", "note"].includes(x.kind));
  const asAnswer = run.chat && !tooled && text;
  const slot = asAnswer ? "" : text || progress || lastNote?.detail || "";
  const thought = !asAnswer && !text && !!progress;
  return (
    <div>
      <ActivityTrace steps={run.steps} live started={run.started} />
      <TaskBoard steps={run.steps} />
      {run.approvals.map((a) => <Approval key={a.approval_id} sid={sid} a={a} />)}
      {slot && <LiveNote text={slot} thought={thought} />}
      {asAnswer && <Markdown text={text} live />}
      <TodoList todos={run.todos} live />
      <LiveChanges steps={run.steps} />
      {waiting && !run.error && <RetryNotice key={waiting.id} step={waiting} />}
      {/* Before the first step: show that the task started (later the live step line shows the activity; toggling
          this indicator between steps made the chat blink). */}
      {!run.error && !running && !run.steps.length && !slot && !asAnswer && run.approvals.length === 0 && <Thinking role={run.role} compact={false} />}
      {run.error && <ErrorNote code={run.errorCode} message={run.error} />}
    </div>
  );
}

function ScopeTabs() {
  const t = useT();
  const project = useStore((s) => s.projects.find((p) => p.id === s.projectId));
  const scope = useStore((s) => s.scope);
  const tab = (active) => `flex items-center gap-1.5 rounded-full border px-3.5 py-1.5 text-[13px] transition ${active ? "border-line bg-elev font-medium shadow-sm" : "border-transparent text-muted hover:bg-hover"}`;
  return (
    <div className="flex flex-wrap justify-center gap-1.5 rounded-full bg-panel p-1">
      {project && (
        <button onClick={() => { useStore.setState({ scope: "project" }); useStore.getState().loadContext(); }} className={tab(scope === "project")}>
          <Folder size={14} /> {project.name}
        </button>
      )}
      <button onClick={() => useStore.setState({ scope: "computer" })} className={tab(scope === "computer" || !project)}>
        <Laptop size={14} /> {t("this_computer")}
      </button>
    </div>
  );
}

// Scrolled up in a long chat: a round button above the message box brings the latest message back.
// While a task runs it shows the working dots, and the arrow on hover (always on touch screens).
function JumpButton({ live, onClick }) {
  const t = useT();
  return (
    <button onClick={onClick} title={t("jump_latest")} aria-label={t("jump_latest")}
      className="jump-in group absolute -top-12 left-1/2 z-30 grid h-9 w-9 -translate-x-1/2 place-items-center rounded-full border border-line bg-elev text-muted shadow-[0_4px_16px_rgb(0_0_0/0.12)] transition hover:border-accent/50 hover:text-fg">
      {live ? (
        <>
          <span className="flex gap-[3px] group-hover:hidden [@media(hover:none)]:hidden">
            {[0, 1, 2].map((i) => <span key={i} className="pulse-dot h-[5px] w-[5px] rounded-full bg-accent" style={{ animationDelay: `${i * 0.18}s` }} />)}
          </span>
          <ArrowDown size={16} className="hidden group-hover:block [@media(hover:none)]:block" />
        </>
      ) : <ArrowDown size={16} />}
    </button>
  );
}

// Reads a dropped folder entry recursively; each file keeps its path inside the folder as relPath.
const readTree = async (entry) => {
  if (entry.isFile) {
    const f = await new Promise((res, rej) => entry.file(res, rej));
    f.relPath = entry.fullPath.replace(/^\//, "");
    return [f];
  }
  const reader = entry.createReader();
  const out = [];
  for (;;) {
    const batch = await new Promise((res, rej) => reader.readEntries(res, rej));
    if (!batch.length) return out;
    for (const e of batch) out.push(...await readTree(e));
  }
};

// Drop zone over the whole chat: a full overlay while files are dragged in, then files and folders go to the composer.
function useDropZone() {
  const [over, setOver] = useState(false);
  const depth = useRef(0);
  const hasFiles = (e) => [...(e.dataTransfer?.types || [])].includes("Files") && !e.target.closest?.("[role=dialog]");
  const handlers = {
    onDragEnter: (e) => { if (!hasFiles(e)) return; e.preventDefault(); depth.current += 1; setOver(true); },
    onDragOver: (e) => { if (!hasFiles(e)) return; e.preventDefault(); e.dataTransfer.dropEffect = "copy"; },
    onDragLeave: (e) => { if (!hasFiles(e)) return; depth.current = Math.max(0, depth.current - 1); if (!depth.current) setOver(false); },
    onDrop: async (e) => {
      if (!hasFiles(e)) return;
      e.preventDefault();
      depth.current = 0;
      setOver(false);
      const entries = [...e.dataTransfer.items].map((i) => i.webkitGetAsEntry?.()).filter(Boolean);
      const plain = [...e.dataTransfer.files];
      const files = [], folders = [];
      if (entries.length === plain.length) {
        for (const [i, en] of entries.entries()) {
          if (en.isDirectory) folders.push(await readTree(en));
          else files.push(plain[i]);
        }
      } else files.push(...plain);
      dispatchEvent(new CustomEvent("aiiq:drop", { detail: { files, folders: folders.filter((f) => f.length) } }));
    },
  };
  return [over, handlers];
}

function DropOverlay() {
  const t = useT();
  return (
    <div className="drop-in pointer-events-none absolute inset-0 z-40 grid place-items-center p-3 backdrop-blur-md sm:p-5"
      style={{ background: "color-mix(in srgb, var(--bg) 90%, transparent)" }}>
      <div className="flex h-full w-full flex-col items-center justify-center gap-4 rounded-[28px] border-2 border-dashed border-accent px-6 text-center shadow-[inset_0_0_80px_color-mix(in_srgb,var(--accent)_10%,transparent)]"
        style={{ background: "color-mix(in srgb, var(--accent) 7%, var(--elev))" }}>
        <div className="grid h-16 w-16 place-items-center rounded-2xl bg-accent text-accent-fg shadow-lg shadow-accent/25">
          <FileUp size={30} strokeWidth={1.8} />
        </div>
        <div className="space-y-1.5">
          <div className="text-[19px] font-semibold tracking-tight">{t("drop_title")}</div>
          <div className="max-w-sm text-[13px] leading-relaxed text-muted">{t("drop_sub")}</div>
        </div>
      </div>
    </div>
  );
}

export default function ChatView() {
  const t = useT();
  const sessionId = useStore((s) => s.sessionId);
  const messages = useStore((s) => s.messages);
  const hasRun = useStore((s) => !!s.runs[s.sessionId]);
  const project = useStore((s) => s.projects.find((p) => p.id === s.projectId));
  const scope = useStore((s) => s.scope);
  const scroller = useRef(null);
  const stick = useRef(true);
  const loading = useStore((s) => s.loadingMessages);
  const hasMore = useStore((s) => s.hasMore);
  const loadingOlder = useStore((s) => s.loadingOlder);
  const empty = messages.length === 0 && !hasRun && !loading;
  useFlash(scroller);

  // Older pages load while scrolling up; the view keeps its place when they are added above.
  const keep = useRef(null);
  const older = async () => {
    const el = scroller.current;
    if (!el || keep.current) return;
    keep.current = { h: el.scrollHeight, top: el.scrollTop };
    const n = await useStore.getState().loadOlder();
    if (!n) keep.current = null;
  };
  useLayoutEffect(() => {
    const el = scroller.current;
    if (keep.current && el) {
      stick.current = false;
      el.scrollTop = keep.current.top + (el.scrollHeight - keep.current.h);
      keep.current = null;
    }
  }, [messages]);

  // Follow the stream only while the user is at the bottom.
  const [away, setAway] = useState(false); // scrolled up from the bottom: show the jump button
  const onScroll = () => {
    const el = scroller.current;
    stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
    setAway(!stick.current && el.scrollHeight - el.scrollTop - el.clientHeight > 120);
    if (el.scrollTop < 240 && hasMore && !loadingOlder) older();
  };
  const toBottom = () => {
    const el = scroller.current;
    stick.current = true;
    el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  };
  useLayoutEffect(() => { stick.current = true; setAway(false); }, [sessionId]);
  useEffect(() => {
    const el = scroller.current;
    if (!el) return;
    const ro = new ResizeObserver(() => { if (stick.current) el.scrollTop = el.scrollHeight; });
    ro.observe(el.firstElementChild);
    return () => ro.disconnect();
  }, [empty, loading]);

  const [dropping, drop] = useDropZone();

  return (
    <div className="relative flex min-h-0 flex-1 flex-col" {...drop}>
      {dropping && <DropOverlay />}
      <div ref={scroller} onScroll={onScroll} className="min-h-0 flex-1 overflow-y-auto">
        {loading ? (
          <div className="flex h-full flex-col items-center justify-center gap-3 text-[13px] text-muted">
            <Loader2 size={22} className="animate-spin text-accent" />
            {t("loading_messages")}
          </div>
        ) : empty ? (
          <div className="flex h-full flex-col items-center justify-center gap-5 px-4 pb-8 text-center">
            <Logo size={52} />
            <div className="-mb-2 text-[13px] font-medium text-muted">{t("welcome_hi")}</div>
            <h1 className="max-w-xl text-[22px] font-semibold tracking-tight sm:text-[28px]">
              {project && scope === "project" ? t("what_work", { project: project.name }) : t("what_work_pc")}
            </h1>
            <ScopeTabs />
            <p className="max-w-md text-[13px] leading-relaxed text-subtle">{t("welcome_sub")}</p>
          </div>
        ) : (
          <div className="mx-auto w-full max-w-[60rem] space-y-7 px-4 py-6 sm:px-6">
            {hasMore && (
              <div className="flex justify-center">
                <button onClick={older} disabled={loadingOlder} className="flex items-center gap-1.5 rounded-full border border-line bg-elev px-3 py-1 text-xs text-muted hover:text-fg">
                  {loadingOlder ? <Loader2 size={12} className="animate-spin" /> : <ArrowDown size={12} className="rotate-180" />}
                  {t(loadingOlder ? "loading_messages" : "load_older")}
                </button>
              </div>
            )}
            <SelectBar messages={messages} />
            {messages.map((m, i) => <Selectable key={m.id} m={m}><Message m={m} last={!hasRun && i === messages.length - 1} /></Selectable>)}
            {hasRun && <LiveRun sid={sessionId} />}
          </div>
        )}
      </div>
      <SelectionAsk root={scroller} />
      <div className="relative">
        {away && !empty && <JumpButton live={hasRun} onClick={toBottom} />}
        <Composer />
      </div>
    </div>
  );
}
