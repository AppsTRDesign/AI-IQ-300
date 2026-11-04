---
name: web-summary
title: Web summary
title_tr: Web özeti
title_en: Web summary
description: Reads a web page or researches a topic and writes a short, faithful summary with key points.
description_tr: Bir web sayfasını okur veya bir konuyu araştırır, kısa ve aslına sadık bir özet ile ana noktaları yazar.
description_en: Reads a web page or researches a topic and writes a short, faithful summary with key points.
tools: research, web_search, fetch_url
---
Produce a faithful summary.

1. Source: if the user gave URLs, read each with `fetch_url` (once). If they gave a topic, call `research` once and use the 3-5 best sources.
2. Summarize only what the sources say - no outside facts, no opinions unless asked.
3. Format:
   - TL;DR: 2-3 sentences.
   - Key points: 5-8 bullets, most important first, with numbers and dates kept exact.
   - If several sources: one line on where they agree and where they differ.
   - Sources: title - URL.
4. Length: about 10-15% of the original, never more than 300 words unless the user asks. Say if a page was blocked or empty.
