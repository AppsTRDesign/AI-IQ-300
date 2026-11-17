// Text preparation for Markdown with math: every LaTeX notation models and users write becomes the $ / $$ form
// remark-math understands, outside code. Currency ("$5 and $10") stays text.

const CODE = /(```[\s\S]*?```|~~~[\s\S]*?~~~|`[^`\n]+`)/g;
const ENVS = "equation|align|gather|multline|eqnarray|split|cases|matrix|pmatrix|bmatrix|vmatrix|Bmatrix|Vmatrix|array|aligned|gathered|alignat";

function mathPart(s) {
  // \[ ... \]  ->  $$ ... $$     \( ... \)  ->  $ ... $
  s = s.replace(/\\\[([\s\S]+?)\\\]/g, (_, m) => `\n$$\n${m.trim()}\n$$\n`);
  s = s.replace(/\\\(([\s\S]+?)\\\)/g, (_, m) => `$${m.trim()}$`);
  // a bare \begin{align}...\end{align} block (no $$ around it)
  s = s.replace(new RegExp(`(^|[^$])(\\\\begin\\{(${ENVS})\\*?\\}[\\s\\S]+?\\\\end\\{\\3\\*?\\})`, "g"),
    (_, pre, env) => `${pre}\n$$\n${env}\n$$\n`);
  // $$ ... $$ written inline in a sentence: keep it display math on its own lines
  s = s.replace(/([^\n])\$\$([^$]+?)\$\$/g, (_, pre, m) => `${pre}\n$$\n${m.trim()}\n$$\n`);
  // currency: "$5 and $10", "$1,200 per month" -> escaped dollars (math has operators, commands or letters glued)
  s = s.replace(/(^|[^\\$])\$(\d[\d.,]*)(?=[\s,.;:!?)]|$)/gm, (m, pre, num) => `${pre}\\$${num}`);
  return s;
}

export function prepareMath(text) {
  if (!text || !/[$\\]/.test(text)) return text;
  return text.split(CODE).map((part, i) => (i % 2 ? part : mathPart(part))).join("");
}

// A user's message keeps its line breaks (Markdown would join single lines into one paragraph).
export function keepBreaks(text) {
  return text.split(CODE).map((part, i) => (i % 2 ? part
    : part.replace(/([^\n])\n(?=[^\n])/g, (m, ch, off, all) => {
      // not inside a list/table/heading structure line pair, where Markdown already breaks
      const next = all.slice(off + 2, off + 6);
      return /^(\s*[-*+]\s|\s*\d+[.)]\s|\s*\||\s*#|\s*>)/.test(next) ? m : `${ch}  \n`;
    }))).join("");
}
