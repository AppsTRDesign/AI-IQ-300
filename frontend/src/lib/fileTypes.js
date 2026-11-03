import {
  File, FileArchive, FileAudio, FileCode2, FileImage, FileJson, FileSpreadsheet, FileTerminal, FileText, FileVideo,
  Presentation, Database,
} from "lucide-react";

// Extension -> icon + brand-ish color, used for attachment chips everywhere.
const GROUPS = [
  [["php"], FileCode2, "#7a86b8", "PHP"],
  [["js", "mjs", "cjs", "jsx"], FileCode2, "#e0b400", "JS"],
  [["ts", "tsx"], FileCode2, "#3178c6", "TS"],
  [["py", "ipynb"], FileCode2, "#3776ab", "PY"],
  [["html", "htm", "vue", "svelte"], FileCode2, "#e34f26", "HTML"],
  [["css", "scss", "sass", "less"], FileCode2, "#7c4dff", "CSS"],
  [["java", "kt", "cs", "cpp", "c", "h", "go", "rs", "rb", "swift", "dart"], FileCode2, "#10b981", "CODE"],
  [["json", "yml", "yaml", "toml", "xml", "ini", "env"], FileJson, "#f59e0b", "CFG"],
  [["sql", "db", "sqlite"], Database, "#0ea5e9", "SQL"],
  [["sh", "bat", "cmd", "ps1"], FileTerminal, "#64748b", "SH"],
  [["md", "txt", "log", "rtf"], FileText, "#64748b", "TXT"],
  [["pdf"], FileText, "#dc2626", "PDF"],
  [["doc", "docx", "odt"], FileText, "#2b579a", "DOC"],
  [["xls", "xlsx", "csv", "ods"], FileSpreadsheet, "#217346", "XLS"],
  [["ppt", "pptx", "odp", "key"], Presentation, "#d24726", "PPT"],
  [["png", "jpg", "jpeg", "gif", "webp", "svg", "bmp", "ico"], FileImage, "#db2777", "IMG"],
  [["mp4", "mov", "avi", "mkv", "webm"], FileVideo, "#9333ea", "VID"],
  [["mp3", "wav", "ogg", "flac", "m4a"], FileAudio, "#0891b2", "AUD"],
  [["zip", "rar", "7z", "tar", "gz"], FileArchive, "#a16207", "ZIP"],
];
const MAP = {};
for (const [exts, icon, color, label] of GROUPS) for (const e of exts) MAP[e] = { icon, color, label };

export function fileType(name = "") {
  const ext = name.includes(".") ? name.split(".").pop().toLowerCase() : "";
  return { ext, ...(MAP[ext] || { icon: File, color: "#71717a", label: ext.toUpperCase().slice(0, 4) || "FILE" }) };
}

export const formatSize = (n = 0) => (n < 1024 ? `${n} B` : n < 1048576 ? `${(n / 1024).toFixed(0)} KB` : `${(n / 1048576).toFixed(1)} MB`);
export const formatTokens = (n = 0) => (n >= 1e6 ? `${+(n / 1e6).toFixed(1)}M` : n >= 1000 ? `${Math.round(n / 1000)}K` : `${n}`);

// Coarse categories for the file manager filters.
const CATEGORY = {
  code: ["php", "js", "mjs", "cjs", "jsx", "ts", "tsx", "py", "ipynb", "html", "htm", "vue", "svelte", "css", "scss", "sass",
    "less", "java", "kt", "cs", "cpp", "c", "h", "go", "rs", "rb", "swift", "dart", "sh", "bat", "cmd", "ps1"],
  image: ["png", "jpg", "jpeg", "gif", "webp", "svg", "bmp", "ico", "avif"],
  document: ["pdf", "doc", "docx", "odt", "rtf", "md", "txt", "ppt", "pptx", "odp", "key"],
  sheet: ["xls", "xlsx", "csv", "ods"],
  data: ["json", "yml", "yaml", "toml", "xml", "ini", "env", "sql", "db", "sqlite", "log", "lock"],
  media: ["mp4", "mov", "avi", "mkv", "webm", "mp3", "wav", "ogg", "flac", "m4a"],
  archive: ["zip", "rar", "7z", "tar", "gz"],
};
const EXT_CATEGORY = Object.fromEntries(Object.entries(CATEGORY).flatMap(([c, exts]) => exts.map((e) => [e, c])));
export const fileCategory = (name = "") => EXT_CATEGORY[name.split(".").pop().toLowerCase()] || "other";
export const CATEGORIES = ["code", "image", "document", "sheet", "data", "media", "archive", "other"];
const TEXT_EXT = new Set([...CATEGORY.code, ...CATEGORY.data, "md", "txt", "csv", "svg", "gitignore", "gitkeep", "htaccess"]);
export const isTextFile = (name = "") => TEXT_EXT.has(name.split(".").pop().toLowerCase()) || !name.includes(".");

// Documents with an in-app preview (components/DocPreview.jsx).
const DOC_KINDS = { xlsx: "sheet", xls: "sheet", ods: "sheet", docx: "word", pdf: "pdf", pptx: "slides" };
export const docKind = (name = "") => DOC_KINDS[name.split(".").pop().toLowerCase()] || null;
