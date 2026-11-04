---
name: web-report
title: Web report
title_tr: Web raporu
title_en: Web report
description: Researches a topic on the web and writes a structured report as a document (Word, PDF or Markdown).
description_tr: Bir konuyu web'de araştırır ve yapılandırılmış bir rapor belgesi (Word, PDF veya Markdown) yazar.
description_en: Researches a topic on the web and writes a structured report as a document (Word, PDF or Markdown).
tools: research, web_search, fetch_url, web_screenshot, make_doc, write_file
---
Write a professional research report.

1. Scope: topic, audience and depth from the request; default to a 2-4 page business report.
2. Plan 3-6 sections, then `research` each section's question (one call per section; no repeats). Keep every source URL.
3. Structure:
   - Title and date
   - Executive summary (5-7 lines with the main findings)
   - Sections with headings; facts with exact numbers and their source in brackets
   - Comparison table when the topic has options or figures
   - Risks / open questions
   - Conclusion and recommendations
   - Sources (numbered, title - URL)
4. Output file: `make_doc` type docx by default (pdf if asked, Markdown via `write_file` if asked) under reports/ with a short descriptive file name.
5. Never invent data; mark single-source or unverified points. Reply with the file path and a 3-line summary.
