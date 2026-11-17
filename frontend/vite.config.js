import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { readFileSync } from "node:fs";

// The app version comes from the VERSION file at the project root (the single place to change it).
const version = (() => { try { return readFileSync(new URL("../VERSION", import.meta.url), "utf8").trim(); } catch { return "0.0.0"; } })();

const backend = process.env.AIIQ_BACKEND || "http://127.0.0.1:8300";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  define: { __APP_VERSION__: JSON.stringify(version) },
  server: {
    port: 5173,
    proxy: {
      "/api": { target: backend, changeOrigin: false },
      "/ws": { target: backend.replace("http", "ws"), ws: true },
    },
  },
  build: { chunkSizeWarningLimit: 6000 },
});
