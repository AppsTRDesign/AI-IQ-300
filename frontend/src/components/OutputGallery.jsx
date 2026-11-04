import { useStore, useT } from "../lib/store";
import { fileType, isImage, isWebPage } from "../lib/fileTypes";

const rawUrl = (path) => useStore.getState().fileApi(`/fs/raw?path=${encodeURIComponent(path)}`);
const nameOf = (path) => path.split(/[\\/]/).pop();

// What a task produced: image thumbnails (open the viewer) and web pages (open the browser), under the answer.
export default function OutputGallery({ paths }) {
  const t = useT();
  const images = (paths || []).filter(isImage);
  const pages = (paths || []).filter(isWebPage);
  if (!images.length && !pages.length) return null;
  const st = useStore.getState();
  return (
    <div className="mt-3 space-y-2">
      {images.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {images.map((p, i) => (
            <button key={p} onClick={() => st.viewImages(images, i)} title={p}
              className="group relative h-36 w-36 overflow-hidden rounded-2xl border border-line bg-[conic-gradient(#8881_25%,transparent_0_50%,#8881_0_75%,transparent_0)] bg-[length:16px_16px] shadow-sm transition hover:shadow-md sm:h-44 sm:w-44">
              <img src={rawUrl(p)} alt={nameOf(p)} loading="lazy" className="h-full w-full object-contain transition group-hover:scale-[1.03]" />
              <span className="absolute inset-x-0 bottom-0 truncate bg-gradient-to-t from-black/70 to-transparent px-2 pb-1.5 pt-4 text-left text-[11px] font-medium text-white">{nameOf(p)}</span>
            </button>
          ))}
        </div>
      )}
      {pages.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {pages.map((p) => {
            const Icon = fileType(p).icon;
            return (
              <button key={p} onClick={() => st.browse({ path: p })} title={p}
                className="group flex w-full max-w-sm items-center gap-3 rounded-2xl border border-line bg-elev p-2.5 pr-4 text-left shadow-[0_1px_4px_rgb(0_0_0/0.04)] transition hover:border-subtle hover:shadow-md">
                <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-[#e34f26] text-white shadow-sm"><Icon size={22} /></span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[13.5px] font-semibold">{nameOf(p)}</span>
                  <span className="block truncate text-xs text-subtle">{t("web_page")} · {p}</span>
                </span>
                <span className="shrink-0 rounded-lg bg-hover px-2 py-1 text-[11px] font-medium text-muted group-hover:bg-accent group-hover:text-accent-fg">{t("open_browser")}</span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
