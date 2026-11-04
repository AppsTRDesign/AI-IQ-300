---
name: catalog
title: Product catalog
title_tr: Ürün kataloğu
title_en: Product catalog
description: Builds a product or service catalog from the web or the user's data: names, specs, prices, images and links, as a styled document, spreadsheet or web page.
description_tr: Web'den veya kullanıcının verisinden ürün/hizmet kataloğu oluşturur: ad, özellik, fiyat, görsel ve bağlantılar; biçimli belge, tablo veya web sayfası olarak.
description_en: Builds a product or service catalog from the web or the user's data: names, specs, prices, images and links, as a styled document, spreadsheet or web page.
tools: research, web_search, fetch_url, read_file, list_dir, write_file, make_doc, web_screenshot, todo
---
Build a clean, accurate catalog.

1. Scope: which products (a brand, a category, the user's own list or file), how many, which fields (name, model, key specs, price, currency, stock/availability, image URL, link) and the format (xlsx, docx, pdf, pptx or an HTML page). Assume sensible defaults and say them in one line.
2. Data: the user's file first (`read_file`); otherwise `research` official product pages and major retailers. Structured data on product pages (the "[Structured data]" block from fetch_url) gives exact names, prices and ratings: prefer it. Prices with currency and date; unknown stays "unknown", never invented.
3. Organize: group by category or series, consistent units, sorted by the order the user wants (price, popularity, name).
4. Output:
   - Spreadsheet catalog: `make_doc` xlsx with one row per product and a header row.
   - Printable catalog: `make_doc` docx/pdf with a cover, contents by category and one block per product.
   - Web catalog: one self-contained `catalog/index.html` (grid of cards, search box, filters by category and price) written with `write_file`; check it with `web_screenshot`.
5. End with the sources (URLs) and the date the data was collected.
