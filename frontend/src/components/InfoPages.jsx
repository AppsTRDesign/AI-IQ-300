import { useEffect, useMemo, useRef, useState } from "react";
import {
  Bot, ChevronDown, ChevronLeft, ChevronRight, CircleHelp, ExternalLink, Files, Gauge, Github, Globe, ListTree, Map, Mic, Rocket,
  Search, ShieldCheck, Sparkles, Star, Folder, Users, Wrench, Check, X,
} from "lucide-react";
import { useStore } from "../lib/store";
import { AUTHOR, VERSION, pagesFor } from "../content/pages";
import { guideFor } from "../content/guide";
import { Logo } from "./Brand";
import Markdown from "./Markdown";

const ICONS = { rocket: Rocket, folder: Folder, bot: Bot, wrench: Wrench, shield: ShieldCheck, gauge: Gauge, files: Files, globe: Globe,
  help: CircleHelp, users: Users, mic: Mic };

const Shell = ({ children }) => (
  <div className="min-h-0 flex-1 overflow-y-auto">
    <div className="mx-auto max-w-6xl px-4 py-6 sm:px-6 sm:py-10">{children}</div>
  </div>
);

const GUIDE_KEY = "aiiq.guide.article";
const fold = (x) => x.toLocaleLowerCase("tr").normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/ı/g, "i");
const plain = (md) => md.replace(/[#*`|>_]|\[|\]|\(.*?\)/g, " ").replace(/\s+/g, " ");

function snippet(text, words) {
  const at = Math.max(0, fold(text).indexOf(words[0]));
  const from = Math.max(0, at - 50);
  return (from ? "…" : "") + text.slice(from, at + 110).trim() + "…";
}

function Highlight({ text, words }) {
  const f = fold(text);
  const marks = [];
  for (const w of words) for (let i = f.indexOf(w); w && i >= 0; i = f.indexOf(w, i + w.length)) marks.push([i, i + w.length]);
  marks.sort((a, b) => a[0] - b[0]);
  const out = [];
  let pos = 0;
  for (const [a, b] of marks) {
    if (a < pos) continue;
    out.push(text.slice(pos, a), <mark key={a} className="rounded bg-accent-soft px-0.5 text-accent">{text.slice(a, b)}</mark>);
    pos = b;
  }
  out.push(text.slice(pos));
  return <>{out}</>;
}

function GuideTree({ g, current, open, toggle, pick }) {
  return (
    <nav className="space-y-0.5">
      {g.cats.map((c) => {
        const I = ICONS[c.icon] || Sparkles;
        const isOpen = open.has(c.id);
        return (
          <div key={c.id}>
            <button onClick={() => toggle(c.id)} aria-expanded={isOpen}
              className="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-[13px] font-semibold hover:bg-hover">
              <ChevronRight size={13} className={`shrink-0 text-subtle transition-transform ${isOpen ? "rotate-90" : ""}`} />
              <I size={15} className="shrink-0 text-accent" /><span className="truncate">{c.title}</span>
              <span className="ml-auto text-[11px] font-normal text-subtle">{c.articles.length}</span>
            </button>
            {isOpen && (
              <div className="mb-1 ml-[22px] border-l border-line pl-2">
                {c.articles.map((a) => (
                  <button key={a.id} onClick={() => pick(a.id)}
                    className={`block w-full truncate rounded-md px-2 py-1 text-left text-[13px] ${a.id === current ? "bg-accent-soft font-medium text-accent" : "text-muted hover:bg-hover hover:text-fg"}`}>
                    {a.title}
                  </button>
                ))}
              </div>
            )}
          </div>
        );
      })}
    </nav>
  );
}

export function GuideView() {
  const lang = useStore((s) => s.prefs.lang);
  const g = guideFor(lang);
  const all = useMemo(() => g.cats.flatMap((c) => c.articles.map((a) => ({ ...a, cat: c }))), [g]);
  const [current, setCurrent] = useState(() => {
    try { return localStorage.getItem(GUIDE_KEY) || ""; } catch { return ""; }
  });
  const article = all.find((a) => a.id === current) || all[0];
  const [open, setOpen] = useState(() => new Set([article.cat.id]));
  const [query, setQuery] = useState("");
  const [menu, setMenu] = useState(false);
  const scroller = useRef(null);
  const body = useRef(null);

  const pick = (id) => {
    setCurrent(id);
    setQuery("");
    setMenu(false);
    const a = all.find((x) => x.id === id);
    if (a) setOpen((o) => new Set(o).add(a.cat.id));
    try { localStorage.setItem(GUIDE_KEY, id); } catch { /* private mode */ }
  };
  useEffect(() => { scroller.current?.scrollTo({ top: 0 }); }, [article.id]);
  const toggle = (id) => setOpen((o) => { const n = new Set(o); n.has(id) ? n.delete(id) : n.add(id); return n; });

  const words = fold(query).split(/\s+/).filter(Boolean);
  const hits = useMemo(() => (words.length ? all.map((a) => {
    const text = `${a.title} ${a.summary} ${plain(a.md)}`;
    const f = fold(text);
    if (!words.every((w) => f.includes(w))) return null;
    const score = words.reduce((n, w) => n + (fold(a.title).includes(w) ? 10 : 0) + (fold(a.summary).includes(w) ? 3 : 0), 0);
    return { a, score, snip: snippet(plain(a.md), words) };
  }).filter(Boolean).sort((x, y) => y.score - x.score) : []), [all, query]); // eslint-disable-line react-hooks/exhaustive-deps

  const headings = useMemo(() => [...article.md.matchAll(/^## (.+)$/gm)].map((m) => m[1]), [article]);
  const idx = all.indexOf(article);
  const prev = all[idx - 1];
  const next = all[idx + 1];
  const jump = (i) => body.current?.querySelectorAll("h2")[i]?.scrollIntoView({ behavior: "smooth", block: "start" });

  return (
    <div ref={scroller} className="min-h-0 flex-1 overflow-y-auto">
      <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 sm:py-8">
        <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-center">
          <div className="flex min-w-0 items-center gap-4">
            <div className="grid h-12 w-12 shrink-0 place-items-center rounded-2xl bg-accent-soft text-accent"><Map size={24} /></div>
            <div className="min-w-0"><h1 className="text-2xl font-semibold tracking-tight">{g.title}</h1><p className="mt-1 text-[14px] text-muted">{g.intro}</p></div>
          </div>
          <label className="relative w-full sm:ml-auto sm:w-80">
            <Search size={15} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-subtle" />
            <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder={g.search} aria-label={g.search}
              onKeyDown={(e) => { if (e.key === "Escape") setQuery(""); if (e.key === "Enter" && hits[0]) pick(hits[0].a.id); }}
              className="w-full rounded-xl border border-line bg-elev py-2 pl-9 pr-8 text-[14px] outline-none focus:border-accent" />
            {query && <button onClick={() => setQuery("")} aria-label="clear" className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-1 text-subtle hover:bg-hover"><X size={14} /></button>}
          </label>
        </div>

        <button onClick={() => setMenu(!menu)} className="mb-3 flex w-full items-center gap-2 rounded-xl border border-line bg-elev px-3 py-2 text-[13px] font-medium lg:hidden">
          <ListTree size={15} className="text-accent" />{g.topics}<span className="ml-1 truncate font-normal text-muted">· {article.title}</span>
          <ChevronDown size={14} className={`ml-auto shrink-0 transition-transform ${menu ? "rotate-180" : ""}`} />
        </button>

        <div className="flex gap-6">
          <aside className={`${menu ? "block" : "hidden"} fixed inset-x-4 top-36 z-30 max-h-[65vh] overflow-y-auto rounded-2xl border border-line bg-elev p-2 shadow-xl lg:sticky lg:inset-auto lg:top-0 lg:z-auto lg:block lg:max-h-[calc(100vh-8rem)] lg:w-64 lg:shrink-0 lg:self-start lg:rounded-none lg:border-0 lg:bg-transparent lg:p-0 lg:shadow-none`}>
            <GuideTree g={g} current={article.id} open={open} toggle={toggle} pick={pick} />
          </aside>

          <main className="min-w-0 flex-1">
            {words.length > 0 ? (
              <div>
                <div className="mb-3 text-[13px] text-muted">{g.results.replace("{n}", hits.length)}</div>
                {hits.length === 0 && <div className="rounded-2xl border border-dashed border-line p-8 text-center text-[14px] text-muted">{g.empty}</div>}
                <div className="space-y-2">
                  {hits.map(({ a, snip }) => (
                    <button key={a.id} onClick={() => pick(a.id)} className="block w-full rounded-2xl border border-line bg-elev p-4 text-left hover:border-accent">
                      <div className="text-[11.5px] font-medium uppercase tracking-wide text-subtle">{a.cat.title}</div>
                      <div className="mt-0.5 text-[15px] font-semibold"><Highlight text={a.title} words={words} /></div>
                      <div className="mt-1 text-[13px] leading-relaxed text-muted"><Highlight text={snip} words={words} /></div>
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              <article className="rounded-2xl border border-line bg-elev p-5 sm:p-7">
                <div className="flex items-center gap-1.5 text-[12px] text-subtle">
                  <button onClick={() => setOpen((o) => new Set(o).add(article.cat.id))} className="hover:text-accent">{article.cat.title}</button>
                  <ChevronRight size={12} /><span className="truncate">{article.title}</span>
                </div>
                <h2 className="mt-2 text-xl font-semibold tracking-tight sm:text-2xl">{article.title}</h2>
                <p className="mt-1 text-[14px] text-muted">{article.summary}</p>
                <div ref={body} className="guide-md mt-5 border-t border-line pt-5"><Markdown text={article.md.trim()} /></div>
                <div className="mt-8 grid grid-cols-2 gap-3 border-t border-line pt-5">
                  {prev ? (
                    <button onClick={() => pick(prev.id)} className="min-w-0 rounded-xl border border-line p-3 text-left hover:border-accent">
                      <div className="flex items-center gap-1 text-[11.5px] text-subtle"><ChevronLeft size={12} />{g.prev}</div>
                      <div className="truncate text-[13.5px] font-medium">{prev.title}</div>
                    </button>
                  ) : <span />}
                  {next && (
                    <button onClick={() => pick(next.id)} className="min-w-0 rounded-xl border border-line p-3 text-right hover:border-accent">
                      <div className="flex items-center justify-end gap-1 text-[11.5px] text-subtle">{g.next}<ChevronRight size={12} /></div>
                      <div className="truncate text-[13.5px] font-medium">{next.title}</div>
                    </button>
                  )}
                </div>
              </article>
            )}
          </main>

          {!words.length && headings.length > 1 && (
            <aside className="hidden w-48 shrink-0 self-start xl:sticky xl:top-0 xl:block">
              <div className="mb-2 text-[11.5px] font-semibold uppercase tracking-wide text-subtle">{g.toc}</div>
              {headings.map((h, i) => (
                <button key={h} onClick={() => jump(i)} className="block w-full truncate border-l border-line py-1 pl-3 text-left text-[13px] text-muted hover:border-accent hover:text-accent">{h}</button>
              ))}
            </aside>
          )}
        </div>
      </div>
    </div>
  );
}

export function AboutView() {
  const lang = useStore((s) => s.prefs.lang);
  const a = pagesFor(lang).about;
  return (
    <Shell>
      <div className="relative overflow-hidden rounded-3xl border border-line bg-gradient-to-br from-[#2563eb]/10 via-[#7c3aed]/10 to-[#db2777]/10 p-6 sm:p-10">
        <div className="flex flex-col items-start gap-5 sm:flex-row sm:items-center">
          <Logo size={72} />
          <div>
            <h1 className="text-3xl font-bold tracking-tight">AI IQ 300 <span className="ml-1 rounded-lg bg-elev px-2 py-0.5 align-middle font-mono text-sm font-medium text-muted">v{VERSION}</span></h1>
            <p className="mt-2 max-w-3xl text-[15px] leading-relaxed text-muted">{a.tagline}</p>
          </div>
        </div>
      </div>

      <section className="mt-8">
        <h2 className="mb-2 text-lg font-semibold">{a.what_title}</h2>
        <p className="text-[14px] leading-relaxed text-muted">{a.what}</p>
      </section>

      <section className="mt-8">
        <h2 className="mb-3 text-lg font-semibold">{a.features_title}</h2>
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {a.features.map(([title, desc]) => (
            <div key={title} className="rounded-2xl border border-line bg-elev p-4">
              <div className="flex items-center gap-2 text-[14px] font-semibold"><Star size={15} className="text-accent" />{title}</div>
              <p className="mt-1.5 text-[13px] leading-relaxed text-muted">{desc}</p>
            </div>
          ))}
        </div>
      </section>

      <div className="mt-8 grid gap-4 md:grid-cols-2">
        <section className="rounded-2xl border border-line bg-elev p-5">
          <h2 className="mb-3 text-[15px] font-semibold">{a.adv_title}</h2>
          <ul className="space-y-2">{a.advantages.map((x) => <li key={x} className="flex gap-2 text-[13px] leading-relaxed text-muted"><Check size={14} className="mt-1 shrink-0 text-ok" />{x}</li>)}</ul>
        </section>
        <section className="rounded-2xl border border-line bg-elev p-5">
          <h2 className="mb-3 text-[15px] font-semibold">{a.roadmap_title}</h2>
          <ol className="space-y-2">{a.roadmap.map((x, i) => (
            <li key={x} className="flex gap-2.5 text-[13px] leading-relaxed text-muted">
              <span className="grid h-5 w-5 shrink-0 place-items-center rounded-full bg-accent-soft text-[11px] font-semibold text-accent">{i + 1}</span>{x}
            </li>))}
          </ol>
        </section>
      </div>

      <section className="mt-8 rounded-2xl border border-line bg-elev p-5 sm:p-6">
        <h2 className="mb-4 text-[15px] font-semibold">{a.dev_title}</h2>
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center">
          <div className="grid h-16 w-16 shrink-0 place-items-center rounded-2xl bg-gradient-to-br from-[#2563eb] to-[#7c3aed] text-xl font-bold text-white">OÖ</div>
          <div className="min-w-0 flex-1">
            <div className="text-[16px] font-semibold">{AUTHOR.name}</div>
            <p className="mt-0.5 text-[13px] text-muted">{a.dev_desc}</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <a href={AUTHOR.github} target="_blank" rel="noreferrer" className="flex items-center gap-1.5 rounded-xl border border-line px-3 py-2 text-[13px] font-medium hover:bg-hover"><Github size={15} /> GitHub <ExternalLink size={12} className="text-subtle" /></a>
            <a href={AUTHOR.site} target="_blank" rel="noreferrer" className="flex items-center gap-1.5 rounded-xl bg-accent px-3 py-2 text-[13px] font-medium text-accent-fg"><Globe size={15} /> wplugins.shop <ExternalLink size={12} /></a>
          </div>
        </div>
      </section>
    </Shell>
  );
}
