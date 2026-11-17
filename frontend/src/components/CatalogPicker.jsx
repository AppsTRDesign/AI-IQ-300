import { useEffect, useMemo, useRef, useState } from "react";
import { Bot, Search, Sparkles } from "lucide-react";
import { loc, useStore, useT } from "../lib/store";

const PAGE = 25;

// Search over names, titles and descriptions (every language the catalog item has): all words must appear;
// an exact or prefix match of the name ranks first, then name, title and description hits.
export function rankCatalog(items, query) {
  const words = (query || "").toLowerCase().replace(/^[@/]/, "").split(/\s+/).filter(Boolean);
  if (!words.length) return items;
  const out = [];
  for (const x of items) {
    const name = x.name.toLowerCase();
    const title = Object.keys(x).filter((k) => k.startsWith("title")).map((k) => String(x[k] || "")).join(" ").toLowerCase();
    const desc = Object.keys(x).filter((k) => k.startsWith("description")).map((k) => String(x[k] || "")).join(" ").toLowerCase();
    const hay = `${name} ${name.replace(/-/g, " ")} ${title} ${desc}`;
    if (!words.every((w) => hay.includes(w))) continue;
    const w0 = words[0];
    const score = name === w0 ? 0 : name.startsWith(w0) ? 1 : name.includes(w0) ? 2 : title.includes(w0) ? 3 : 4;
    out.push([score, x]);
  }
  return out.sort((a, b) => a[0] - b[0] || a[1].name.localeCompare(b[1].name)).map((p) => p[1]);
}

// The / (skills) and @ (agents) list: as wide as the message box, searchable, loads more while scrolling.
// typed: the query comes from the text before the caret (keyboard navigation by the parent); otherwise it has its
// own search box (opened from the + menu).
export default function CatalogPicker({ trigger, query, typed, sel = 0, onSel, onPick, onClose }) {
  const t = useT();
  const catalog = useStore((s) => s.catalog);
  const [own, setOwn] = useState("");
  const [shown, setShown] = useState(PAGE);
  const [i, setI] = useState(0);
  const listRef = useRef(null);
  // Typed after / or @ in the message: the text filters; the search box can refine it (its own words win).
  const items = useMemo(() => rankCatalog(trigger === "@" ? catalog.agents : catalog.skills, own || (typed ? query : "")),
    [catalog, trigger, query, own, typed]);
  useEffect(() => { setShown(PAGE); setI(0); listRef.current?.scrollTo(0, 0); }, [trigger, query, own]);
  const active = typed && !own ? sel : i;
  useEffect(() => { // keep the highlighted row visible (and loaded)
    if (active >= shown - 2) setShown((n) => Math.min(items.length, n + PAGE));
    listRef.current?.querySelector(`[data-i="${active}"]`)?.scrollIntoView({ block: "nearest" });
  }, [active]);
  useEffect(() => { if (typed) onSel?.(Math.min(sel, Math.max(0, items.length - 1)), items); }, [items]);
  const onScroll = (e) => {
    const el = e.currentTarget;
    if (el.scrollHeight - el.scrollTop - el.clientHeight < 80 && shown < items.length) setShown((n) => n + PAGE);
  };
  const Icon = trigger === "@" ? Bot : Sparkles;
  const keys = (e) => {
    if (e.key === "ArrowDown") { e.preventDefault(); setI((x) => Math.min(items.length - 1, x + 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setI((x) => Math.max(0, x - 1)); }
    else if (e.key === "Enter" && items[i]) { e.preventDefault(); onPick(items[i].name); }
    else if (e.key === "Escape") { e.preventDefault(); onClose?.(); }
  };
  return (
    <div className="fade-in absolute bottom-full left-0 right-0 z-40 mb-2 flex max-h-[min(460px,62vh)] flex-col rounded-2xl border border-line bg-elev shadow-xl"
      onMouseDown={(e) => typed && e.target.tagName !== "INPUT" && e.preventDefault()}>
      <div className="flex items-center gap-2 border-b border-line px-3 py-2">
        <Icon size={14} className={trigger === "@" ? "text-violet-500" : "text-accent"} />
        <span className="text-[11px] font-semibold uppercase tracking-wider text-subtle">{trigger === "@" ? t("agents") : t("skills")}</span>
        {(
          <div className="ml-2 flex min-w-0 flex-1 items-center gap-1.5 rounded-lg bg-bg px-2 py-1">
            <Search size={13} className="text-subtle" />
            <input autoFocus={!typed} value={own} onChange={(e) => setOwn(e.target.value)} onKeyDown={keys} onMouseDown={(e) => e.stopPropagation()}
              placeholder={t(trigger === "@" ? "search_agents" : "search_skills")} className="min-w-0 flex-1 bg-transparent text-[13px] outline-none" />
          </div>
        )}
        <span className="ml-auto shrink-0 text-[11px] text-subtle">{items.length}</span>
      </div>
      <div ref={listRef} onScroll={onScroll} className="min-h-0 flex-1 overflow-y-auto p-1.5">
        {items.length === 0 && <div className="px-3 py-6 text-center text-xs text-subtle">{t("no_results")}</div>}
        {items.slice(0, shown).map((x, n) => (
          <button key={x.name} data-i={n} onClick={() => onPick(x.name)} onMouseEnter={() => (typed ? onSel?.(n, items) : setI(n))}
            className={`flex w-full items-start gap-2.5 rounded-xl px-2.5 py-2 text-left text-[13px] ${n === active ? "bg-hover" : "hover:bg-hover"}`}>
            <Icon size={15} className="mt-0.5 shrink-0 text-muted" />
            <span className="min-w-0 flex-1">
              <span className="flex items-baseline gap-2">
                <span className="truncate font-medium">{trigger}{x.name}</span>
                {loc(x, "title") && <span className="truncate text-xs text-subtle">{loc(x, "title")}</span>}
              </span>
              {loc(x, "description") && <span className="mt-0.5 line-clamp-2 block text-xs leading-snug text-muted">{loc(x, "description")}</span>}
            </span>
          </button>
        ))}
        {shown < items.length && <div className="py-2 text-center text-[11px] text-subtle">{t("scroll_more")}</div>}
      </div>
    </div>
  );
}
