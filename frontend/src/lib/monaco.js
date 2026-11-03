// Bundle Monaco locally (no CDN) so the IDE works offline.
import * as monaco from "monaco-editor";
import { loader } from "@monaco-editor/react";
import EditorWorker from "monaco-editor/esm/vs/editor/editor.worker?worker";
import JsonWorker from "monaco-editor/esm/vs/language/json/json.worker?worker";
import CssWorker from "monaco-editor/esm/vs/language/css/css.worker?worker";
import HtmlWorker from "monaco-editor/esm/vs/language/html/html.worker?worker";
import TsWorker from "monaco-editor/esm/vs/language/typescript/ts.worker?worker";

self.MonacoEnvironment = {
  getWorker(_, label) {
    if (label === "json") return new JsonWorker();
    if (["css", "scss", "less"].includes(label)) return new CssWorker();
    if (["html", "handlebars", "razor"].includes(label)) return new HtmlWorker();
    if (["typescript", "javascript"].includes(label)) return new TsWorker();
    return new EditorWorker();
  },
};
loader.config({ monaco });

const EXT = {
  js: "javascript", jsx: "javascript", mjs: "javascript", ts: "typescript", tsx: "typescript", py: "python",
  php: "php", html: "html", htm: "html", css: "css", scss: "scss", json: "json", md: "markdown", sql: "sql",
  sh: "shell", bash: "shell", ps1: "powershell", bat: "bat", cmd: "bat", yml: "yaml", yaml: "yaml", xml: "xml",
  java: "java", cs: "csharp", cpp: "cpp", c: "c", go: "go", rs: "rust", rb: "ruby", kt: "kotlin", vue: "html",
};
const ALIAS = { py: "python", js: "javascript", ts: "typescript", sh: "shell", ps: "powershell", pwsh: "powershell",
  cmd: "bat", batch: "bat", yml: "yaml", "c#": "csharp", "c++": "cpp", jsx: "javascript", tsx: "typescript" };

export const languageForPath = (p = "") => EXT[p.split(".").pop().toLowerCase()] || "plaintext";
export const normalizeLanguage = (l = "") => ALIAS[l.toLowerCase()] || l.toLowerCase() || "plaintext";
