---
name: docs
title: Document generator
title_tr: Belge üretici
title_en: Document generator
description: Produces professional, designed Word, Excel, PDF, PowerPoint or HTML documents (every language, LaTeX formulas, clickable sources), or adds content to an existing one.
description_tr: Tasarımlı, profesyonel Word, Excel, PDF, PowerPoint veya HTML belgesi üretir (her dil, LaTeX formüller, tıklanır kaynaklar) ya da mevcut bir belgeye içerik ekler.
description_en: Produces professional, designed Word, Excel, PDF, PowerPoint or HTML documents (every language, LaTeX formulas, clickable sources), or adds content to an existing one.
tools: make_doc, read_file, list_dir, write_file, run, research, fetch_url
---
The user wants a document. Ask nothing when the request is clear; choose sensible defaults.

1. Type: docx for letters, reports and contracts; xlsx for tables and calculations; pdf for a fixed, printable layout; pptx for slides; html for a web page. Follow the user's choice when given. Several formats asked: one make_doc call per format from the same content.
2. Content first, real data only: when facts, prices, rates or dates are needed, `research` first and use what the sources say. Never lorem ipsum, never invented numbers, never "a chart would go here" placeholders. Cite sources as real Markdown links `[Site name](https://...)` - they become clickable in every format.
3. Reports, analyses and anything that should look professional: write **HTML** (a fragment; make_doc's template adds fonts, colours, cover band and page numbers). Use `<h1>` once, `<h2>` sections, `<p>`, `<table>` with `<thead>`, and the ready components - they need no image file and work in pdf, html, docx and pptx:
   - KPI cards: `<div class="kpis"><div class="kpi"><span>USD/TRY</span><b>50,36</b><em class="up">+0,22%</em></div>...</div>` (`up` / `down` colour the change).
   - Bar chart: `<div class="bars"><div style="--v:76%"><span>USD</span><i></i><b>50,36</b></div>...</div>` (`--v` = the bar's length in % of the largest value; compute it from the real numbers).
   - `<div class="callout">note</div>` (`callout warn` for warnings), `<span class="badge">tag</span>`, `<div class="cols"><div>left</div><div>right</div></div>`, inline `<svg>` for custom charts.
   A typical report: h1 + one lead paragraph, KPI cards, a table, a bar chart, a short analysis, sources as links.
   Simple letters and notes can stay Markdown (below).
3b. Markdown (also accepted everywhere; make_doc turns it into the same designed document - do not write python-docx/reportlab code for new documents):
   - `#` title once, `##` sections, `###` subsections, short paragraphs, `**bold**` key terms.
   - Real Markdown tables (`| a | b |` with a `|---|` line) for every comparison or data list; numbers in their own columns.
   - `- ` bullets and `1. ` numbered steps, `> ` for notes/callouts, fenced code blocks for code.
   - Formulas in LaTeX: `$inline$` and `$$display$$` (they are typeset in PDF/HTML and inserted as images in Word/PowerPoint).
   - Images: `![caption](relative/path.png)` ONLY for files that really exist in the working folder. A chart is created first: `run` with shell=python and matplotlib (`plt.savefig("chart.png", dpi=160)`), then referenced. Images that do not exist are removed from the document and reported; never mention a picture the result says was not included.
   - pptx: every `##` heading starts a slide; the first `#` with one short paragraph is the title slide; keep 3-6 bullets or one table per slide; last slide summary/next steps.
   - xlsx: JSON rows `[["Header",...],[...]]`, `[{"col": value}]` or `{"sheets": {"Name": rows}}`, or Markdown tables (one sheet each). Keep numbers as numbers; formulas start with `=`.
4. Pick `theme` to fit the topic (corporate, blue, green, red, purple, orange, teal, gray, dark); `landscape=true` for wide PDF tables.
5. Long documents: write the Markdown to a file in parts first (`write_file`, then `write_file` with `append=true`), then `make_doc` with `source=<that file>`; one giant call can stall or be cut off.
6. Save under docs/ with a short descriptive file name in the user's language.
7. Adding to an existing .docx/.xlsx: read it first, then run Python (python-docx / openpyxl) to append in place and keep the original content and styles.
8. Report the path(s) and a one-line summary of what is inside.
