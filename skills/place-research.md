---
name: place-research
title: Place research
title_tr: Mekân araştırması
title_en: Place research
description: Finds places near a location on the map and researches them: address, hours, phone, rating, reviews, prices, with an interactive map.
description_tr: Bir konumun yakınındaki mekânları haritada bulur ve araştırır: adres, saatler, telefon, puan, yorumlar, fiyatlar; etkileşimli haritayla.
description_en: Finds places near a location on the map and researches them: address, hours, phone, rating, reviews, prices, with an interactive map.
tools: places, research, web_search, fetch_url, make_doc, write_file, todo
---
Research places around a location like a local guide who checks facts.

1. Location and need: the district, address or coordinates the user gave, and what they look for (kind of place, budget, open now, quiet, parking...). If no location is given, ask for one in one short question.
2. `places` with `near` set to the location, a sensible `radius` (walking: 800-1500 m, city: 3000-8000 m) and `map: true`. If too few results: widen the radius or use a broader word (e.g. "kafe" instead of "üçüncü nesil kahve").
3. Pick the 3-6 best candidates for the need (distance, category, hours). For each one `research` "<name> <district> yorum" / "menü fiyat" to add reviews, price level, specialities. Ratings and review counts come only from the tool results or sources; never invent them. Unknown stays "unknown".
4. Answer:
   - A table: name, kind, distance, rating (reviews), price level, hours, phone, address.
   - 1-2 lines per place: why it fits, what to watch out for.
   - The best pick for the user's need, plus an alternative.
   - The map page path (`maps/...html`) and the sources with URLs.
5. If the user wants a file: `make_doc` (docx/pdf for a guide, xlsx for the list).
