---
name: web-to-doc
title: Web to document
title_tr: Web'den belgeye
title_en: Web to document
description: Researches the web and writes a summary, comparison or section into a document you name (new or existing Word, Excel, Markdown).
description_tr: Web'de araştırır; özeti, karşılaştırmayı veya bölümü belirttiğiniz belgeye (yeni ya da mevcut Word, Excel, Markdown) yazar.
description_en: Researches the web and writes a summary, comparison or section into a document you name (new or existing Word, Excel, Markdown).
tools: research, web_search, fetch_url, read_file, list_dir, make_doc, write_file, edit_file, run
---
Research, then write the result into the target document without damaging what is already there.

1. Target: find the document the user named (`list_dir` if the path is unclear). Read it first (`read_file`; for .docx/.xlsx run a short Python script that prints its headings / sheet names) so the new content fits its structure, tone and language.
2. Research the requested content with `research` (one call per sub-topic, no repeats); keep URLs.
3. Write the content type asked for:
   - Summary: TL;DR + key points.
   - Comparison: a table (items as columns, criteria as rows) + short verdict.
   - Section/report: heading, paragraphs, sources.
4. Insert it:
   - .md/.txt/.html: `edit_file` at the right place (or append under a new heading).
   - .docx: Python with python-docx - open, add heading + paragraphs/table at the end or after the named heading, save to the same file.
   - .xlsx: Python with openpyxl - new sheet named after the topic, header row bold, sources in a last column.
   - No existing file: `make_doc` with a suitable type.
5. Verify by reading the file back (headings or row count), then reply with the path, what was added where, and the sources.
