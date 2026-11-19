import { useEffect, useMemo, useRef, useState } from "react";
import { Download, ImagePlus, Loader2, Palette, Save, Sparkles, Wand2 } from "lucide-react";
import { useStore, useT } from "../lib/store";
import { api } from "../lib/api";
import { Button, Modal, inputCls } from "./ui";
import { FONTS, FONT_CSS } from "./VideoStudio";

// Logo maker for brands: a live canvas (brand name, tagline, symbol, colours, layout, badge shapes), symbols drawn by
// the image services with their background removed, three AI brand directions, transparent PNG export.

const LAYOUTS = ["icon_left", "icon_top", "text_only", "badge"];
const SHAPES = ["none", "circle", "rounded", "hexagon"];
const START = { brand: "", tagline: "", industry: "", font: "sans", weight: 800, uppercase: false, letter_spacing: 1,
  layout: "icon_left", shape: "none", colors: { primary: "#2563EB", secondary: "#F59E0B", text: "#111827" }, icon: null, iconSize: 1, showTagline: true };

function loadImg(src) {
  return new Promise((ok, bad) => { const im = new Image(); im.onload = () => ok(im); im.onerror = bad; im.src = src; });
}

function hexagon(ctx, cx, cy, r) {
  ctx.beginPath();
  for (let i = 0; i < 6; i++) {
    const a = (Math.PI / 3) * i - Math.PI / 6;
    ctx[i ? "lineTo" : "moveTo"](cx + r * Math.cos(a), cy + r * Math.sin(a));
  }
  ctx.closePath();
}

// draws the logo on a canvas; returns nothing (the canvas is sized by the layout)
async function draw(canvas, s, scale = 1) {
  const ctx = canvas.getContext("2d");
  const icon = s.icon ? await loadImg(s.icon).catch(() => null) : null;
  const vertical = s.layout === "icon_top" || s.layout === "badge";
  const W = (vertical ? 1000 : 1400) * scale;
  const H = (vertical ? 1000 : 520) * scale;
  canvas.width = W;
  canvas.height = H;
  ctx.clearRect(0, 0, W, H);
  const name = s.uppercase ? (s.brand || "Brand").toUpperCase() : s.brand || "Brand";
  const tag = s.showTagline ? (s.tagline || "") : "";
  const font = FONT_CSS[s.font] || FONT_CSS.sans;
  const setFont = (px, w = s.weight) => { ctx.font = `${w} ${px}px ${font}`; ctx.letterSpacing = `${(s.letter_spacing || 0) * scale}px`; };
  const fit = (text, maxW, px, w) => { let p = px; setFont(p, w); while (ctx.measureText(text).width > maxW && p > 12) { p -= 4; setFont(p, w); } return p; };
  ctx.textBaseline = "alphabetic";
  if (s.layout === "badge") {
    const cx = W / 2;
    const cy = H / 2;
    const r = W * 0.46;
    ctx.fillStyle = s.colors.primary;
    if (s.shape === "rounded") { ctx.beginPath(); ctx.roundRect(cx - r, cy - r, 2 * r, 2 * r, r * 0.28); ctx.fill(); }
    else if (s.shape === "hexagon") { hexagon(ctx, cx, cy, r); ctx.fill(); }
    else { ctx.beginPath(); ctx.arc(cx, cy, r, 0, Math.PI * 2); ctx.fill(); }
    ctx.lineWidth = 10 * scale;
    ctx.strokeStyle = s.colors.secondary;
    ctx.beginPath(); ctx.arc(cx, cy, r * 0.9, 0, Math.PI * 2); if (s.shape === "none" || s.shape === "circle") ctx.stroke();
    let y = cy;
    if (icon) {
      const iw = r * 0.85 * s.iconSize;
      const ih = iw * (icon.height / icon.width);
      ctx.drawImage(icon, cx - iw / 2, cy - r * 0.62, iw, ih);
      y = cy - r * 0.62 + ih + r * 0.22;
    }
    ctx.fillStyle = "#ffffff";
    ctx.textAlign = "center";
    const px = fit(name, r * 1.6, 120 * scale);
    ctx.fillText(name, cx, icon ? y : cy + px * 0.35);
    if (tag) { const tp = fit(tag, r * 1.4, 46 * scale, 500); ctx.fillStyle = s.colors.secondary; ctx.fillText(tag, cx, (icon ? y : cy + px * 0.35) + tp * 1.5); }
    return;
  }
  ctx.textAlign = "left";
  const pad = 40 * scale;
  if (s.layout === "icon_top") {
    let y = pad;
    if (icon) {
      const iw = W * 0.42 * s.iconSize;
      const ih = iw * (icon.height / icon.width);
      if (s.shape !== "none") {
        ctx.fillStyle = s.colors.primary;
        const r = Math.max(iw, ih) * 0.62;
        if (s.shape === "circle") { ctx.beginPath(); ctx.arc(W / 2, y + r, r, 0, Math.PI * 2); ctx.fill(); }
        else if (s.shape === "hexagon") { hexagon(ctx, W / 2, y + r, r); ctx.fill(); }
        else { ctx.beginPath(); ctx.roundRect(W / 2 - r, y, 2 * r, 2 * r, r * 0.3); ctx.fill(); }
        ctx.drawImage(icon, W / 2 - iw / 2, y + r - ih / 2, iw, ih);
        y += 2 * r + pad;
      } else { ctx.drawImage(icon, W / 2 - iw / 2, y, iw, ih); y += ih + pad; }
    }
    ctx.textAlign = "center";
    const px = fit(name, W - 2 * pad, 150 * scale);
    ctx.fillStyle = s.colors.text;
    ctx.fillText(name, W / 2, y + px * 0.8);
    if (tag) { const tp = fit(tag, W - 2 * pad, 52 * scale, 500); ctx.fillStyle = s.colors.primary; ctx.fillText(tag, W / 2, y + px * 0.8 + tp * 1.6); }
    return;
  }
  // icon_left / text_only
  let x = pad;
  const mid = H / 2;
  if (icon && s.layout === "icon_left") {
    const ih = H * 0.72 * s.iconSize;
    const iw = ih * (icon.width / icon.height);
    if (s.shape !== "none") {
      const r = Math.max(iw, ih) * 0.58;
      ctx.fillStyle = s.colors.primary;
      if (s.shape === "circle") { ctx.beginPath(); ctx.arc(x + r, mid, r, 0, Math.PI * 2); ctx.fill(); }
      else if (s.shape === "hexagon") { hexagon(ctx, x + r, mid, r); ctx.fill(); }
      else { ctx.beginPath(); ctx.roundRect(x, mid - r, 2 * r, 2 * r, r * 0.3); ctx.fill(); }
      ctx.drawImage(icon, x + r - iw / 2, mid - ih / 2, iw, ih);
      x += 2 * r + pad * 1.2;
    } else { ctx.drawImage(icon, x, mid - ih / 2, iw, ih); x += iw + pad; }
  }
  const px = fit(name, W - x - pad, 170 * scale);
  ctx.fillStyle = s.colors.text;
  ctx.fillText(name, x, tag ? mid + px * 0.1 : mid + px * 0.35);
  if (tag) {
    const tp = fit(tag, W - x - pad, 54 * scale, 500);
    ctx.fillStyle = s.colors.primary;
    ctx.fillText(tag, x + 4 * scale, mid + px * 0.1 + tp * 1.5);
  }
}

// trims the transparent margins of a drawn logo
function trimmed(canvas) {
  const ctx = canvas.getContext("2d");
  const { width: w, height: h } = canvas;
  const d = ctx.getImageData(0, 0, w, h).data;
  let x0 = w, y0 = h, x1 = 0, y1 = 0;
  for (let y = 0; y < h; y += 2) for (let x = 0; x < w; x += 2) {
    if (d[(y * w + x) * 4 + 3] > 8) { if (x < x0) x0 = x; if (x > x1) x1 = x; if (y < y0) y0 = y; if (y > y1) y1 = y; }
  }
  if (x1 <= x0) return canvas;
  const m = 12;
  const out = document.createElement("canvas");
  out.width = Math.min(w, x1 - x0 + 2 * m);
  out.height = Math.min(h, y1 - y0 + 2 * m);
  out.getContext("2d").drawImage(canvas, Math.max(0, x0 - m), Math.max(0, y0 - m), out.width, out.height, 0, 0, out.width, out.height);
  return out;
}

export default function LogoMaker() {
  const t = useT();
  const st = useStore.getState();
  const sessionId = useStore((s) => s.sessionId);
  const [s, setS] = useState(START);
  const [bg, setBg] = useState("check");
  const [variants, setVariants] = useState([]);
  const [icons, setIcons] = useState([]);
  const [busy, setBusy] = useState("");
  const [saved, setSaved] = useState("");
  const canvas = useRef(null);
  const file = useRef(null);
  const set = (patch) => setS((x) => ({ ...x, ...patch }));
  const setCol = (k, v) => setS((x) => ({ ...x, colors: { ...x.colors, [k]: v } }));
  useEffect(() => { if (canvas.current) draw(canvas.current, s, 1); }, [s]);
  const close = () => useStore.setState({ dialog: null });
  const lang = st.prefs?.lang || "tr";

  const suggest = async () => {
    if (!s.brand.trim()) return st.notify(t("lm_need_brand"), "error");
    setBusy("suggest");
    try {
      const r = await api.post("/api/logo/suggest", { brand: s.brand, slogan: s.tagline, industry: s.industry, model: st.currentModel(), lang });
      setVariants(r.variants || []);
    } catch (e) { st.notify(t("lm_ai_failed"), "error", e.message); }
    setBusy("");
  };
  const makeIcons = async (prompt) => {
    const p = (prompt || `${s.industry || ""} ${s.brand}`).trim();
    if (!p) return st.notify(t("lm_need_brand"), "error");
    setBusy("icons");
    try {
      const r = await api.post("/api/logo/icons", { prompt: p, style: "modern minimal", colors: `${s.colors.primary} and ${s.colors.secondary}`, n: 3 });
      setIcons(r.icons || []);
      if (r.icons?.[0] && !s.icon) set({ icon: r.icons[0].png });
    } catch (e) { st.notify(t("lm_icons_failed"), "error", e.message); }
    setBusy("");
  };
  const apply = (v) => {
    set({ font: v.font, weight: v.weight, uppercase: v.uppercase, letter_spacing: v.letter_spacing, layout: v.layout, shape: v.shape,
      colors: v.colors, ...(v.tagline && !s.tagline ? { tagline: v.tagline } : {}) });
    if (v.icon_prompt) makeIcons(v.icon_prompt);
  };
  const uploadIcon = async (f) => {
    if (!f) return;
    setBusy("cutout");
    const fd = new FormData();
    fd.append("file", f);
    try {
      const r = await fetch("/api/logo/cutout", { method: "POST", body: fd });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail?.message || `HTTP ${r.status}`);
      setIcons((x) => [{ png: d.png, service: "upload" }, ...x]);
      set({ icon: d.png });
    } catch (e) { st.notify(t("lm_cutout_failed"), "error", e.message); }
    setBusy("");
  };
  const exportPng = async () => {
    const c = document.createElement("canvas");
    await draw(c, s, 2);
    return new Promise((ok) => trimmed(c).toBlob(ok, "image/png"));
  };
  const name = `${(s.brand || "logo").toLowerCase().replace(/[^a-z0-9ğüşöçı]+/gi, "-").replace(/^-|-$/g, "") || "logo"}-logo.png`;
  const download = async () => { const b = await exportPng(); const a = document.createElement("a"); a.href = URL.createObjectURL(b); a.download = name; a.click(); };
  const save = async () => {
    const b = await exportPng();
    const fd = new FormData();
    fd.append("file", new File([b], name, { type: "image/png" }));
    try { await fetch(st.fileApi("/fs/upload?path=logos"), { method: "POST", body: fd }); setSaved(`logos/${name}`); }
    catch (e) { st.notify(t("vl_save_failed"), "error", e.message); }
  };
  const bgCls = { check: "bg-elev bg-[repeating-conic-gradient(#8883_0_25%,transparent_0_50%)] bg-[length:20px_20px]", white: "bg-white", dark: "bg-[#111]" }[bg];
  const label = (k) => t(`lm_${k}`);
  const field = `${inputCls} !py-1.5 !text-[12.5px]`;

  return (
    <Modal title={<span className="flex items-center gap-2"><Palette size={17} className="text-amber-500" />{t("lm_title")}</span>} onClose={close} width="max-w-5xl"
      footer={<><Button variant="ghost" onClick={close}>{t("close")}</Button>
        {sessionId && <Button onClick={save} disabled={!s.brand} title={t("lm_save")}><Save size={14} /><span className="hidden sm:inline">{t("lm_save")}</span><span className="sm:hidden">{t("save")}</span></Button>}
        <Button variant="primary" onClick={download} disabled={!s.brand} title={t("lm_download")}><Download size={14} /><span className="hidden sm:inline">{t("lm_download")}</span><span className="sm:hidden">PNG</span></Button></>}>
      <div className="grid gap-4 text-[13px] lg:grid-cols-[1fr_340px]">
        {/* phones: this column dissolves into the grid, so the preview stays on top while everything below scrolls */}
        <div className="space-y-3 max-lg:contents">
          <div className={`sticky top-0 z-10 grid min-h-[150px] place-items-center rounded-2xl border border-line p-2 shadow-md lg:static lg:min-h-[260px] lg:p-4 lg:shadow-none ${bgCls}`}>
            <canvas ref={canvas} className="max-h-[150px] max-w-full lg:max-h-[360px]" />
          </div>
          <div className="flex flex-wrap items-center gap-1.5 text-[12px]">
            <span className="text-muted">{t("lm_preview_bg")}</span>
            {["check", "white", "dark"].map((b) => <button key={b} onClick={() => setBg(b)} className={`rounded-md px-2 py-0.5 ${bg === b ? "bg-active font-medium" : "text-muted hover:bg-hover"}`}>{label(`bg_${b}`)}</button>)}
            {saved && <span className="ml-auto text-ok">✓ {t("vl_saved", { path: saved })}</span>}
          </div>
          {variants.length > 0 && (
            <div className="grid gap-2 sm:grid-cols-3">
              {variants.map((v, i) => (
                <button key={i} onClick={() => apply(v)} className="rounded-xl border border-line p-2.5 text-left hover:border-accent/60 hover:bg-hover">
                  <div className="flex items-center gap-1.5"><span className="h-3 w-3 rounded-full" style={{ background: v.colors.primary }} /><span className="h-3 w-3 rounded-full" style={{ background: v.colors.secondary }} />
                    <b className="truncate" style={{ fontFamily: FONT_CSS[v.font] }}>{v.name}</b></div>
                  <div className="mt-1 text-[11.5px] leading-snug text-muted">{v.why}</div>
                </button>
              ))}
            </div>
          )}
          {icons.length > 0 && (
            <div>
              <div className="mb-1 text-[12px] font-medium">{t("lm_symbols")}</div>
              <div className="flex flex-wrap gap-2">
                {icons.map((ic, i) => (
                  <button key={i} onClick={() => set({ icon: ic.png })} className={`grid h-20 w-20 place-items-center rounded-xl border p-1.5 bg-[repeating-conic-gradient(#8883_0_25%,transparent_0_50%)] bg-[length:12px_12px] ${s.icon === ic.png ? "border-accent ring-2 ring-accent/30" : "border-line"}`}>
                    <img src={ic.png} alt="" className="max-h-full max-w-full" />
                  </button>
                ))}
                {s.icon && <button onClick={() => set({ icon: null })} className="h-20 rounded-xl border border-dashed border-line px-3 text-[12px] text-muted hover:bg-hover">{t("lm_no_symbol")}</button>}
              </div>
            </div>
          )}
        </div>
        <div className="space-y-2.5">
          <input className={field} value={s.brand} onChange={(e) => set({ brand: e.target.value })} placeholder={t("lm_brand")} />
          <input className={field} value={s.tagline} onChange={(e) => set({ tagline: e.target.value })} placeholder={t("lm_tagline")} />
          <input className={field} value={s.industry} onChange={(e) => set({ industry: e.target.value })} placeholder={t("lm_industry")} />
          <div className="grid grid-cols-2 gap-1.5">
            <button onClick={suggest} disabled={!!busy} className="flex items-center justify-center gap-1.5 rounded-xl bg-accent py-2 text-[12.5px] font-medium text-accent-fg disabled:opacity-50">
              {busy === "suggest" ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />}{t("lm_ai_suggest")}</button>
            <button onClick={() => makeIcons()} disabled={!!busy} className="flex items-center justify-center gap-1.5 rounded-xl bg-amber-500 py-2 text-[12.5px] font-medium text-white disabled:opacity-50">
              {busy === "icons" ? <Loader2 size={14} className="animate-spin" /> : <Wand2 size={14} />}{t("lm_ai_symbol")}</button>
          </div>
          <button onClick={() => file.current.click()} disabled={!!busy} className="flex w-full items-center justify-center gap-1.5 rounded-xl border border-dashed border-line py-1.5 text-[12px] hover:bg-hover">
            {busy === "cutout" ? <Loader2 size={13} className="animate-spin" /> : <ImagePlus size={13} />}{t("lm_upload_symbol")}</button>
          <input ref={file} type="file" accept="image/*" className="hidden" onChange={(e) => { uploadIcon(e.target.files?.[0]); e.target.value = ""; }} />
          <div className="grid grid-cols-2 gap-2">
            <label className="text-[11.5px] text-muted">{t("vs_font")}<select className={field} value={s.font} onChange={(e) => set({ font: e.target.value })}>{FONTS.map((f) => <option key={f} value={f}>{t(`vs_font_${f}`)}</option>)}</select></label>
            <label className="text-[11.5px] text-muted">{t("lm_weight")}<select className={field} value={s.weight} onChange={(e) => set({ weight: +e.target.value })}>{[400, 500, 600, 700, 800, 900].map((w) => <option key={w}>{w}</option>)}</select></label>
            <label className="text-[11.5px] text-muted">{t("lm_layout")}<select className={field} value={s.layout} onChange={(e) => set({ layout: e.target.value })}>{LAYOUTS.map((l) => <option key={l} value={l}>{label(`layout_${l}`)}</option>)}</select></label>
            <label className="text-[11.5px] text-muted">{t("lm_shape")}<select className={field} value={s.shape} onChange={(e) => set({ shape: e.target.value })}>{SHAPES.map((l) => <option key={l} value={l}>{label(`shape_${l}`)}</option>)}</select></label>
          </div>
          <div className="grid grid-cols-3 gap-2">
            {["primary", "secondary", "text"].map((k) => (
              <label key={k} className="text-[11.5px] text-muted">{label(`color_${k}`)}<input type="color" className="h-8 w-full cursor-pointer rounded-lg border border-line bg-bg" value={s.colors[k]} onChange={(e) => setCol(k, e.target.value)} /></label>
            ))}
          </div>
          <label className="block text-[11.5px] text-muted">{t("lm_spacing")} ({s.letter_spacing})<input type="range" min={-4} max={20} step={0.5} value={s.letter_spacing} onChange={(e) => set({ letter_spacing: +e.target.value })} className="w-full accent-[var(--accent)]" /></label>
          <label className="block text-[11.5px] text-muted">{t("lm_symbol_size")} ({s.iconSize.toFixed(2)})<input type="range" min={0.4} max={1.4} step={0.05} value={s.iconSize} onChange={(e) => set({ iconSize: +e.target.value })} className="w-full accent-[var(--accent)]" /></label>
          <div className="flex flex-wrap gap-3 text-[12px]">
            <label className="flex items-center gap-1.5"><input type="checkbox" checked={s.uppercase} onChange={(e) => set({ uppercase: e.target.checked })} />{t("lm_uppercase")}</label>
            <label className="flex items-center gap-1.5"><input type="checkbox" checked={s.showTagline} onChange={(e) => set({ showTagline: e.target.checked })} />{t("lm_show_tagline")}</label>
          </div>
          <p className="text-[11px] leading-snug text-subtle">{t("lm_note")}</p>
        </div>
      </div>
    </Modal>
  );
}
