---
name: site-test
title: Website test
title_tr: Web sitesi testi
title_en: Website test
description: Tests a live or local website end to end in a real browser (pages, links, forms, sign-up/login, console errors, mobile layout, speed) and writes a bug report with screenshots.
description_tr: Canlı veya yerel bir siteyi gerçek tarayıcıda uçtan uca test eder (sayfalar, bağlantılar, formlar, üyelik/giriş, konsol hataları, mobil görünüm, hız) ve ekran görüntülü hata raporu yazar.
description_en: Tests a live or local website end to end in a real browser (pages, links, forms, sign-up/login, console errors, mobile layout, speed) and writes a bug report with screenshots.
tools: browser_navigate, browser_snapshot, browser_find, browser_click, browser_type, browser_form, browser_key, browser_scroll, browser_wait, browser_tabs, browser_screenshot, browser_inspect, browser_batch, browser_handoff, browser_check, web_screenshot, fetch_url, run, write_file, make_doc, todo
---
Test the site like a QA engineer. Be fast: batch actions with browser_batch, never repeat a check that passed.

## 1. Plan (todo)
List the flows to test from the request: home, navigation, key pages, search, forms, sign-up / login, cart/checkout
(stop before paying), language switch, 404 page. A local project: start it first (start), then test its URL.

## 2. Crawl and check (fast, no browser)
Collect same-site links from the home page and check them in one script (`run` with shell=python, httpx, 10 parallel,
HEAD then GET): status code, redirect chains, response time, missing title/description, broken images.

## 3. Real browser flows
For every flow: browser_navigate, act (browser_form / browser_click / browser_type), then verify the result on the
page (a message, a new URL, an element). After each page read console errors and failed requests with
browser_inspect. Sign-up and login on the user's own site: allowed with the data the user gave (in full access the
password field is filled too). A CAPTCHA: browser_handoff and continue after it is solved. Never pay, never send
real messages to other people.

## 4. Layout and speed
browser_check (or web_screenshot) at desktop 1440 px and mobile 390 px: overflow, overlapping text, unreadable
contrast, buttons out of reach. Measure load time with browser_inspect performance timing.

## 5. Report
make_doc (pdf or html) or a Markdown answer: summary score, a table of bugs (severity, page, steps to reproduce,
expected vs actual, screenshot), passed checks, and concrete fixes. Only report what you saw.
