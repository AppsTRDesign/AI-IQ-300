import {
  Bot, CircleHelp, ExternalLink, Files, Gauge, Github, Globe, Map, Rocket, ShieldCheck, Sparkles, Star, Folder, Wrench, Check,
} from "lucide-react";
import { useStore } from "../lib/store";
import { AUTHOR, VERSION, pagesFor } from "../content/pages";
import { Logo } from "./Brand";

const ICONS = { rocket: Rocket, folder: Folder, bot: Bot, wrench: Wrench, shield: ShieldCheck, gauge: Gauge, files: Files, globe: Globe, help: CircleHelp };

const Shell = ({ children }) => (
  <div className="min-h-0 flex-1 overflow-y-auto">
    <div className="mx-auto max-w-4xl px-4 py-6 sm:px-6 sm:py-10">{children}</div>
  </div>
);

export function GuideView() {
  const lang = useStore((s) => s.prefs.lang);
  const g = pagesFor(lang).guide;
  return (
    <Shell>
      <div className="mb-8 flex items-center gap-4">
        <div className="grid h-12 w-12 place-items-center rounded-2xl bg-accent-soft text-accent"><Map size={24} /></div>
        <div><h1 className="text-2xl font-semibold tracking-tight">{g.title}</h1><p className="mt-1 text-[14px] text-muted">{g.intro}</p></div>
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        {g.sections.map((s) => {
          const I = ICONS[s.icon] || Sparkles;
          return (
            <section key={s.title} className="rounded-2xl border border-line bg-elev p-5">
              <h2 className="mb-3 flex items-center gap-2 text-[15px] font-semibold"><I size={17} className="text-accent" />{s.title}</h2>
              <ul className="space-y-2">
                {s.items.map((it, i) => (
                  <li key={i} className="flex gap-2 text-[13px] leading-relaxed text-muted"><Check size={14} className="mt-1 shrink-0 text-ok" /><span>{it}</span></li>
                ))}
              </ul>
            </section>
          );
        })}
      </div>
    </Shell>
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
            <p className="mt-2 max-w-2xl text-[15px] leading-relaxed text-muted">{a.tagline}</p>
          </div>
        </div>
      </div>

      <section className="mt-8">
        <h2 className="mb-2 text-lg font-semibold">{a.what_title}</h2>
        <p className="text-[14px] leading-relaxed text-muted">{a.what}</p>
      </section>

      <section className="mt-8">
        <h2 className="mb-3 text-lg font-semibold">{a.features_title}</h2>
        <div className="grid gap-3 sm:grid-cols-2">
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
