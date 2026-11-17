---
name: web-design
title: Professional web design
title_tr: Profesyonel web tasarımı
title_en: Professional web design
description: Designs landing pages and websites like a senior designer, with real photos, tested JavaScript and a mobile check.
description_tr: Kıdemli bir tasarımcı gibi landing page ve web sitesi tasarlar; gerçek fotoğraflar, test edilmiş JavaScript ve mobil kontrolle.
description_en: Designs landing pages and websites like a senior designer, with real photos, tested JavaScript and a mobile check.
---
Design like a senior product designer and front-end engineer. Work in this order, batching independent steps in one reply.

1. Brief (in your head, no questions unless the brand is unknown): audience, tone (premium / playful / minimal / bold), the one action the page must drive (order, book, sign up, call).
2. Design system as CSS variables at the top of the stylesheet:
   - Fonts: one display face for headings (Playfair Display, Fraunces, Space Grotesk, Sora...) and one text face (Inter, DM Sans, Manrope) from Google Fonts with `display=swap`.
   - Colour: one brand colour, one accent, 5 neutrals from near-white to near-black; text contrast at least 4.5:1. Dark sections for rhythm.
   - Scale: spacing 4/8/12/16/24/32/48/64/96 px, type scale with `clamp()` (hero 2.5-4.5rem), radius 12-20px, two shadow levels.
3. Photos: ONE `stock_photo` call with every visual need comma separated (hero, 3-4 product/feature shots, ambience/team), short concrete English subjects ("coffee shop interior, latte art cup, iced coffee, croissant"); they download in parallel. A subject that found nothing gets CSS/SVG art instead of another search. Use the returned relative paths; `object-fit: cover`, `aspect-ratio`, `alt`, `loading="lazy"` (not on the hero). Credit line in the footer. Never hotlink, never invent a file name. No internet: SVG/CSS art.
4. Structure: sticky header (logo, nav, CTA) with a working mobile menu; hero (headline with a promise, subline, primary + secondary button, photo or split layout, trust badges); then the sections the business needs: features or menu cards with prices, about/story, testimonials with names, pricing or opening hours, location with address and map link, contact/reservation form with validation, footer.
5. Content: real, specific copy in the user's language: product names, prices in the local currency, hours, address. No lorem ipsum, no "Feature 1".
6. Interaction: hover/focus states, smooth scroll, a scroll-reveal with IntersectionObserver, active nav highlight, form validation messages, `prefers-reduced-motion`. Plain JavaScript in one `<script>` at the end; no errors.
7. Test: `web_screenshot` the page (desktop) and again with `device="mobile"`. Its result runs the JavaScript and lists JS errors, failed requests and broken images: fix every one, then screenshot again. Check the vision description for overlaps, low contrast or empty areas.
8. Report: the file path, the sections, the photo credits and how to open it.
