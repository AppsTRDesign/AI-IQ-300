import { useEffect, useRef, useState } from "react";
import Lightbox from "yet-another-react-lightbox";
import Zoom from "yet-another-react-lightbox/plugins/zoom";
import Download from "yet-another-react-lightbox/plugins/download";
import Counter from "yet-another-react-lightbox/plugins/counter";
import "yet-another-react-lightbox/styles.css";
import "yet-another-react-lightbox/plugins/counter.css";
import {
  AlertTriangle, ExternalLink, Globe, Loader2, Monitor, RotateCw, Smartphone, Tablet, X,
} from "lucide-react";
import { useStore, useT } from "../lib/store";
import { api } from "../lib/api";

// Images the agent produced open in a zoomable lightbox; web pages open in an in-app browser that serves the
// working folder from its own localhost origin (relative CSS/JS/images load, the page cannot reach the app API).

const rawUrl = (path) => useStore.getState().fileApi(`/fs/raw?path=${encodeURIComponent(path)}`);
const nameOf = (path) => path.split(/[\\/]/).pop();

export function ImageViewer() {
  const dialog = useStore((s) => s.dialog);
  const close = () => useStore.setState({ dialog: null });
  const paths = dialog.paths || [];
  return (
    <Lightbox open close={close} index={dialog.index || 0} plugins={[Zoom, Download, Counter]}
      slides={paths.map((p) => ({ src: rawUrl(p), alt: nameOf(p), download: { url: rawUrl(p) + "&download=true", filename: nameOf(p) } }))}
      zoom={{ maxZoomPixelRatio: 4, scrollToZoom: true }}
      carousel={{ finite: paths.length < 2, padding: "64px" }} // keeps the counter and toolbar off the image
      render={paths.length < 2 ? { buttonPrev: () => null, buttonNext: () => null } : undefined}
      styles={{ container: { backgroundColor: "rgba(10,10,14,.92)" } }} />
  );
}

const SIZES = [["desktop", Monitor, "100%"], ["tablet", Tablet, "820px"], ["mobile", Smartphone, "390px"]];

export function BrowserDialog() {
  const t = useT();
  const dialog = useStore((s) => s.dialog);
  const close = () => useStore.setState({ dialog: null });
  const [url, setUrl] = useState(dialog.url || "");
  const [address, setAddress] = useState(dialog.url || "");
  const [error, setError] = useState("");
  const [size, setSize] = useState("desktop");
  const [loading, setLoading] = useState(true);
  const [nonce, setNonce] = useState(0);
  const frame = useRef(null);

  useEffect(() => {
    if (!dialog.path) return;
    let alive = true;
    api.get(useStore.getState().fileApi(`/fs/preview?path=${encodeURIComponent(dialog.path)}`))
      .then((r) => { if (alive) { setUrl(r.url); setAddress(r.url); } })
      .catch((e) => alive && setError(e.message));
    return () => { alive = false; };
  }, [dialog.path]);
  useEffect(() => {
    const k = (e) => e.key === "Escape" && close();
    addEventListener("keydown", k);
    return () => removeEventListener("keydown", k);
  }, []);

  const go = (e) => {
    e.preventDefault();
    let next = address.trim();
    if (!next) return;
    if (!/^https?:\/\//i.test(next)) next = /^(localhost|127\.|\[::1\])/.test(next) ? `http://${next}` : `https://${next}`;
    setError(""); setLoading(true); setUrl(next); setAddress(next); setNonce((n) => n + 1);
  };
  const reload = () => { setLoading(true); setNonce((n) => n + 1); };
  const width = SIZES.find((s) => s[0] === size)[2];
  const title = dialog.path ? nameOf(dialog.path) : (() => { try { return new URL(url).host; } catch { return url; } })();

  return (
    <div role="dialog" aria-modal="true" className="fixed inset-0 z-50 flex items-center justify-center bg-black/45 p-0 backdrop-blur-[2px] sm:p-5"
      onMouseDown={(e) => e.target === e.currentTarget && close()}>
      <div className="fade-in flex h-full w-full max-w-6xl flex-col overflow-hidden border border-line bg-elev shadow-2xl sm:h-[92vh] sm:rounded-3xl">
        <div className="flex items-center gap-2 border-b border-line px-3 py-2.5">
          <span className="grid h-8 w-8 shrink-0 place-items-center rounded-xl bg-[#e34f26] text-white"><Globe size={16} /></span>
          <div className="hidden min-w-0 max-w-[180px] sm:block">
            <div className="truncate text-[13px] font-semibold">{title}</div>
            <div className="text-[11px] text-subtle">{t("browser")}</div>
          </div>
          <button onClick={reload} title={t("reload")} className="rounded-lg p-1.5 text-muted hover:bg-hover"><RotateCw size={15} /></button>
          <form onSubmit={go} className="min-w-0 flex-1">
            <input value={address} onChange={(e) => setAddress(e.target.value)} spellCheck={false} aria-label={t("address")}
              className="w-full rounded-xl border border-line bg-bg px-3 py-1.5 font-mono text-xs outline-none focus:border-accent" />
          </form>
          <div className="hidden items-center rounded-xl border border-line p-0.5 md:flex">
            {SIZES.map(([k, Icon]) => (
              <button key={k} onClick={() => setSize(k)} title={t(`view_${k}`)}
                className={`rounded-lg p-1.5 ${size === k ? "bg-hover text-fg" : "text-subtle hover:text-fg"}`}><Icon size={14} /></button>
            ))}
          </div>
          <a href={url || undefined} target="_blank" rel="noreferrer" title={t("open_new_tab")} className="rounded-lg p-1.5 text-muted hover:bg-hover"><ExternalLink size={15} /></a>
          <button onClick={close} className="rounded-lg p-1.5 text-muted hover:bg-hover"><X size={18} /></button>
        </div>
        <div className="relative min-h-0 flex-1 overflow-auto bg-panel">
          {error ? (
            <div className="grid h-full place-items-center p-6 text-center text-[13px] text-muted">
              <div><AlertTriangle size={22} className="mx-auto mb-2 text-warn" />{t("preview_failed")}<div className="mt-1 font-mono text-xs text-subtle">{error}</div></div>
            </div>
          ) : url ? (
            <>
              <iframe key={nonce} ref={frame} src={url} title={title} onLoad={() => setLoading(false)}
                sandbox="allow-scripts allow-same-origin allow-forms allow-modals allow-popups allow-downloads"
                className="mx-auto block h-full border-0 bg-white transition-[width]" style={{ width, maxWidth: "100%" }} />
              {loading && <div className="pointer-events-none absolute inset-x-0 top-0 h-0.5 overflow-hidden"><div className="h-full w-1/3 animate-pulse bg-accent" /></div>}
            </>
          ) : (
            <div className="grid h-full place-items-center"><Loader2 size={20} className="animate-spin text-accent" /></div>
          )}
        </div>
      </div>
    </div>
  );
}
