import { createRoot } from "react-dom/client";
import "./index.css";
import App from "./App";
import { useStore } from "./lib/store";

// Automated layout checks (Playwright) switch views through the store; nothing in the app reads this.
window.__aiiq = useStore;

// The app was rebuilt / updated while this tab was open: its hashed files (index-*.css, lazy chunks) are gone (404).
// Reload once to get the new index.html instead of a half-styled page; never in a loop.
const staleReload = () => {
  try {
    const last = Number(sessionStorage.getItem("aiiq_stale_reload") || 0);
    if (Date.now() - last < 30000) return;
    sessionStorage.setItem("aiiq_stale_reload", String(Date.now()));
  } catch { /* no storage: still reload once per page */ }
  location.reload();
};
window.addEventListener("vite:preloadError", (e) => { e.preventDefault(); staleReload(); });
window.addEventListener("error", (e) => {
  const el = e.target;
  if (el && (el.tagName === "LINK" || el.tagName === "SCRIPT") && /\/assets\//.test(el.href || el.src || "")) staleReload();
}, true);

createRoot(document.getElementById("root")).render(<App />);
