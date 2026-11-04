---
name: place-compare
title: Place comparison
title_tr: Mekân karşılaştırma
title_en: Place comparison
description: Compares two or more places (restaurants, hotels, shops, gyms...) side by side: location, rating, reviews, prices, hours, access, with a recommendation.
description_tr: İki veya daha fazla mekânı (restoran, otel, mağaza, spor salonu...) yan yana karşılaştırır: konum, puan, yorumlar, fiyat, saatler, ulaşım ve öneri.
description_en: Compares two or more places (restaurants, hotels, shops, gyms...) side by side: location, rating, reviews, prices, hours, access, with a recommendation.
tools: places, research, web_search, fetch_url, make_doc, write_file, todo
---
Compare the places fairly and decide.

1. Identify each place exactly: `places` with its name as `query` and its district/city as `near` (small radius). If a name matches several branches, ask which one or compare the closest branches and say so.
2. Criteria (6-8): location and distance to the user's point if given, rating and review count, price level, menu/services, opening hours, accessibility/parking/transport, atmosphere, strengths and complaints from reviews.
3. Data: `research` per place (official site, menu, review sites, recent news). Prices with currency and date. Never invent a rating or a price; unknown stays "unknown".
4. Answer: a comparison table (places as columns), pros/cons per place, a clear recommendation for the user's need ("for a business lunch", "for families"...) and when the other one wins, sources with URLs.
5. `places` with `map: true` for both locations when the distance between them matters. `make_doc` when a file is wanted.
