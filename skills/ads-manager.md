---
name: ads-manager
title: Ads management (Meta, Google, Yandex)
title_tr: Reklam yönetimi (Meta, Google, Yandex)
title_en: Ads management (Meta, Google, Yandex)
description: Analyzes and manages ad accounts on Meta (Facebook/Instagram), Google Ads and Yandex Direct through their APIs or Ads Manager in the browser; reports performance and prepares campaigns, changing budgets only with approval.
description_tr: Meta (Facebook/Instagram), Google Ads ve Yandex Direct reklam hesaplarını API'leri veya tarayıcıdaki reklam yöneticisi üzerinden analiz eder ve yönetir; performans raporlar, kampanya hazırlar, bütçeyi yalnızca onayla değiştirir.
description_en: Analyzes and manages ad accounts on Meta (Facebook/Instagram), Google Ads and Yandex Direct through their APIs or Ads Manager in the browser; reports performance and prepares campaigns, changing budgets only with approval.
tools: browser_navigate, browser_snapshot, browser_find, browser_click, browser_type, browser_form, browser_scroll, browser_wait, browser_screenshot, browser_batch, browser_handoff, run, write_file, read_file, research, web_search, make_doc, todo
---
Money is spent by these actions. Creating or enabling campaigns, changing budgets or bids and adding payment methods
happen only after the user approved the exact change (campaign, amount, currency, dates). New campaigns are
created PAUSED; the user turns them on or approves turning them on. Reading and reporting need no approval.
Never enter card or bank details.

## Access (token / IDs from the user, in env vars of one run call, never written to files)
| Platform | API | Browser |
|---|---|---|
| Meta | Marketing API `https://graph.facebook.com/v23.0/act_<AD_ACCOUNT_ID>/insights` (fields: spend, impressions, clicks, ctr, cpc, actions), `/campaigns`, `/adsets`, `/ads` | adsmanager.facebook.com |
| Google Ads | Google Ads API (`google-ads` Python package: developer token + OAuth + customer id), GAQL: `SELECT campaign.name, metrics.cost_micros, metrics.clicks, metrics.conversions FROM campaign WHERE segments.date DURING LAST_30_DAYS` | ads.google.com |
| Yandex Direct | API v5 `https://api.direct.yandex.com/json/v5/` (campaigns, ads, keywords) and Reports service | direct.yandex.com |
Install a client library only when needed (`pip install google-ads`). Without API access use the signed-in browser
(login or 2FA: browser_handoff).

## Work
1. Report: spend, impressions, clicks, CTR, CPC, conversions, CPA, ROAS per campaign / ad set / ad for the period;
   charts (matplotlib) and a make_doc report with clear findings (wasted spend, best creatives, audiences).
2. Optimize: concrete proposals (pause, budget shift with amounts, new keywords / negatives, audience, creative
   tests) as a table; apply only the approved ones and verify them on the platform afterwards.
3. New campaign: objective, audience, budget, schedule, ad texts and visuals (graphics skill) as a draft first.
