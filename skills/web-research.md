---
name: web-research
title: Web research
title_tr: Web araştırması
title_en: Web research
description: Fast sourced answer from the web for a current or factual question.
description_tr: Güncel veya olgusal bir soruya web'den hızlı ve kaynaklı cevap verir.
description_en: Fast sourced answer from the web for a current or factual question.
tools: research, web_search, fetch_url, web_screenshot
---
Answer the question from the web with sources, using as few calls as possible.

1. Call `research` with the user's own topic words (do not add years or terms they did not ask for). One call is usually enough; make a second, differently worded call only if the first left the main point open.
2. Use `fetch_url` only for one specific page the user named or that the results point to; never repeat a call.
3. Confirm key numbers and dates in two sources when possible; otherwise say "single source".
4. Answer: the direct answer first (1-3 sentences), then up to 6 supporting bullets, each with its URL. End with "Sources". State plainly what you could not verify. If a site is blocked, say so and use others.
