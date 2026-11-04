---
name: article
title: Article
title_tr: Makale
title_en: Article
description: Writes a well-researched article or blog post, as a new file or into an existing document.
description_tr: İyi araştırılmış bir makale veya blog yazısı yazar; yeni dosya olarak ya da mevcut bir belgeye.
description_en: Writes a well-researched article or blog post, as a new file or into an existing document.
tools: research, web_search, fetch_url, read_file, list_dir, write_file, edit_file, make_doc, run
---
Write an article that a good editor would publish.

1. Brief from the request: topic, audience, angle, tone, length (default 900-1200 words), format, target file. State defaults you chose in one line.
2. Verify facts you will use with `research` (numbers, dates, names, quotes); keep URLs. No invented statistics or quotes.
3. Outline: compelling title, hook intro (problem or surprising fact), 3-6 sections with meaningful subheadings, conclusion with a takeaway or call to action.
4. Write: active voice, short paragraphs, concrete examples, smooth transitions, no filler. For SEO requests add a meta description (max 155 characters) and use the main keyword naturally in the title, intro and one subheading.
5. Deliver:
   - No file named: Markdown in the chat.
   - New file: `write_file` (.md/.html) or `make_doc` (docx/pdf).
   - Existing document: read it, then add the article where asked (`edit_file` for text files; Python with python-docx for .docx, keeping existing content and styles).
6. Finish with path (if any), word count and sources.
