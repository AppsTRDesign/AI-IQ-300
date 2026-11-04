---
name: compare
title: Product comparison
title_tr: Ürün karşılaştırma
title_en: Product comparison
description: Side-by-side comparison of products or services with a table, sources and a clear recommendation.
description_tr: Ürünleri veya hizmetleri tablo, kaynak ve net bir öneriyle yan yana karşılaştırır.
description_en: Side-by-side comparison of products or services with a table, sources and a clear recommendation.
tools: research, web_search, fetch_url, web_screenshot, make_doc, write_file
---
Compare the items fairly and decide.

1. Items: the ones the user named; if only a category is given, choose the 3-5 most relevant current options and say why.
2. Criteria: 5-8 that matter for the user's need (price, key specs, quality/reviews, warranty/support, ecosystem, running costs). State assumptions about the need in one line.
3. Data: `research` per item (official spec pages, reputable reviews). Prices with currency, date and region. Unknown values stay "unknown" - never guess.
4. Output:
   - Comparison table (items as columns, criteria as rows, units in cells).
   - Pros/cons per item (1-2 lines each).
   - Recommendation: best overall for the stated need, best value, and when another one wins.
   - Sources with URLs.
5. If the user wants a file: `make_doc` xlsx for the table alone, docx/pdf for the full comparison.
