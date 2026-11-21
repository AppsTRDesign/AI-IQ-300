import { memo, useState } from "react";
import { ChevronDown, ExternalLink, Globe, BookOpenCheck } from "lucide-react";
import { useStore, useT } from "../lib/store";

// Web / image search results of a step as cards: the site's icon, title, address and a short excerpt; the photos a
// stock search downloaded as a thumbnail grid. Light: plain elements, lazy images, nothing measured or animated.

export const hostOf = (url) => {
  try { return new URL(url).hostname.replace(/^www\./, ""); } catch { return ""; }
};

// The site's icon (a small cached image from the icon service; a globe when the site has none)
export const Favicon = memo(function Favicon({ url, size = 16, className = "" }) {
  const host = hostOf(url);
  const [bad, setBad] = useState(!host);
  if (bad) return <Globe size={size} className={`shrink-0 text-subtle ${className}`} />;
  return (
    <img src={`https://icons.duckduckgo.com/ip3/${host}.ico`} alt="" width={size} height={size} loading="lazy" decoding="async"
      referrerPolicy="no-referrer" onError={() => setBad(true)}
      className={`shrink-0 rounded-[4px] bg-white object-contain ${className}`} style={{ width: size, height: size }} />
  );
});

// A few overlapping site icons next to the step title (the sources at a glance, also while the step is closed)
export function FaviconStack({ results, max = 4 }) {
  const seen = new Set();
  const uniq = (results || []).filter((r) => { const h = hostOf(r.url); if (!h || seen.has(h)) return false; seen.add(h); return true; });
  if (!uniq.length) return null;
  return (
    <span className="flex shrink-0 items-center">
      {uniq.slice(0, max).map((r, i) => (
        <span key={r.url} title={hostOf(r.url)} className={`grid h-[18px] w-[18px] place-items-center rounded-full bg-elev ring-2 ring-bg ${i ? "-ml-1.5" : ""}`}>
          <Favicon url={r.url} size={13} />
        </span>
      ))}
      {uniq.length > max && <span className="ml-1 text-[11px] text-subtle">+{uniq.length - max}</span>}
    </span>
  );
}

export function SearchResults({ results, engines, raw }) {
  const t = useT();
  const [all, setAll] = useState(false);
  const shown = all ? results : results.slice(0, 4);
  return (
    <div className="space-y-1.5">
      <div className="grid gap-1.5 md:grid-cols-2">
        {shown.map((r) => (
          <a key={r.url} href={r.url} target="_blank" rel="noreferrer"
            className="group/card flex min-w-0 flex-col gap-1 rounded-xl border border-line bg-elev px-3 py-2 transition-colors hover:border-accent/50 hover:bg-hover">
            <span className="flex min-w-0 items-center gap-1.5 text-[11.5px] text-subtle">
              <Favicon url={r.url} size={14} />
              <span className="truncate">{hostOf(r.url)}</span>
              {r.read && <span title={t("search_read_tip")} className="ml-auto inline-flex shrink-0 items-center gap-0.5 rounded bg-ok/10 px-1 text-[10.5px] text-ok"><BookOpenCheck size={10} />{t("search_read")}</span>}
              <ExternalLink size={11} className={`shrink-0 opacity-0 group-hover/card:opacity-70 ${r.read ? "" : "ml-auto"}`} />
            </span>
            <span className="line-clamp-2 text-[13px] font-medium leading-snug text-fg">{r.title || hostOf(r.url)}</span>
            {r.snippet && <span className="line-clamp-2 text-[12px] leading-snug text-muted">{r.snippet}</span>}
          </a>
        ))}
      </div>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 px-0.5 text-[11.5px] text-subtle">
        {results.length > 4 && (
          <button onClick={() => setAll(!all)} className="inline-flex items-center gap-0.5 text-accent hover:underline">
            <ChevronDown size={12} className={all ? "rotate-180" : ""} />{all ? t("search_less") : t("search_all", { n: results.length })}
          </button>
        )}
        {engines?.length > 0 && <span>{t("search_engines")}: {engines.join(", ")}</span>}
        {raw && (
          <details className="w-full">
            <summary className="cursor-pointer select-none">{t("search_raw")}</summary>
            <pre className="mt-1 max-h-60 overflow-auto whitespace-pre-wrap rounded-lg border border-line bg-code p-2 font-mono text-[11px] text-muted">{raw}</pre>
          </details>
        )}
      </div>
    </div>
  );
}

// The photos a stock search downloaded: thumbnails (lazy, from the chat's folder), who took them, under which license
export function PhotoResults({ photos, rawUrl }) {
  const t = useT();
  return (
    // like a web result card: a small photo on the left, the site, title and credits beside it
    <div className="grid gap-1.5 md:grid-cols-2">
      {photos.map((p) => {
        const site = hostOf(p.page) || (p.provider || "").replace(/\s*\(via .*\)$/, "");
        return (
          <div key={p.path} className="group/ph flex min-w-0 gap-2.5 rounded-xl border border-line bg-elev p-1.5 pr-3 transition-colors hover:border-accent/50 hover:bg-hover">
            <button onClick={() => useStore.getState().openFile(p.path)} title={p.path}
              className="h-[68px] w-[92px] shrink-0 overflow-hidden rounded-lg bg-hover">
              <img src={rawUrl(p.path)} alt={p.title} loading="lazy" decoding="async"
                className="h-full w-full object-cover transition-transform duration-300 group-hover/ph:scale-[1.04]" />
            </button>
            <span className="flex min-w-0 flex-1 flex-col justify-center gap-0.5">
              <span className="flex min-w-0 items-center gap-1.5 text-[11.5px] text-subtle">
                {p.page ? <Favicon url={p.page} size={13} /> : <Globe size={13} className="shrink-0" />}
                <span className="truncate">{site}</span>
                {p.page && <a href={p.page} target="_blank" rel="noreferrer" title={p.page} className="ml-auto shrink-0 rounded p-0.5 opacity-60 hover:bg-hover hover:opacity-100"><ExternalLink size={11} /></a>}
              </span>
              <span className="line-clamp-1 text-[13px] font-medium leading-snug text-fg">{p.title || p.path.split("/").pop()}</span>
              <span className="line-clamp-1 text-[11.5px] leading-snug text-muted">
                {[p.author && p.author !== "unknown" && t("photo_by", { name: p.author }), p.license, p.w && p.h && `${p.w}×${p.h}`].filter(Boolean).join(" · ")}
              </span>
              <span className="truncate font-mono text-[10.5px] text-subtle">{p.path}</span>
            </span>
          </div>
        );
      })}
    </div>
  );
}
