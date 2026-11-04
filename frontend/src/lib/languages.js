// File extension / fence name -> Monaco language id (no Monaco import: safe for the initial bundle).
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
