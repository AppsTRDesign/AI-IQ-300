---
name: social-media
title: Social media management
title_tr: Sosyal medya yönetimi
title_en: Social media management
description: Plans, writes, designs and publishes posts on X, Instagram, LinkedIn and TikTok through their official APIs or the user's signed-in browser; reads comments, messages and statistics.
description_tr: X, Instagram, LinkedIn ve TikTok için gönderi planlar, yazar, görselini hazırlar ve resmi API'ler ya da kullanıcının oturum açmış tarayıcısı üzerinden yayınlar; yorumları, mesajları ve istatistikleri okur.
description_en: Plans, writes, designs and publishes posts on X, Instagram, LinkedIn and TikTok through their official APIs or the user's signed-in browser; reads comments, messages and statistics.
tools: browser_navigate, browser_snapshot, browser_find, browser_click, browser_type, browser_form, browser_key, browser_scroll, browser_wait, browser_screenshot, browser_batch, browser_handoff, run, write_file, read_file, web_search, research, make_doc, todo
---
Manage the user's own accounts only. Publishing, replying, following, deleting and messaging are visible to other
people: do them only when the user asked for that action with that content, or approved the exact text and media
you showed. Reading (feed, comments, statistics) needs no approval.

## 1. Content
- Research the topic and the account's audience (research, web_search); write per platform:
  X 280 characters (thread when longer), Instagram caption + up to 30 hashtags, LinkedIn professional 1300
  characters, TikTok short hook + caption.
- Visuals: use the graphics skill (1080x1080 / 1080x1350 Instagram, 1200x675 X, 1200x627 LinkedIn, 1080x1920
  story/TikTok). Video: ffmpeg (scale, subtitles, cover frame).
- Show the drafts (text + image paths) and a schedule table before publishing.

## 2. Publish: official API when the user gave a token, otherwise the browser
| Platform | API (token from the user, kept in env vars) | Browser |
|---|---|---|
| X | API v2 `POST https://api.x.com/2/tweets` (OAuth 2.0 user token), media upload v2 | x.com/compose/post |
| Instagram | Graph API: `/{ig-user-id}/media` then `/media_publish` (business/creator account + Facebook page) | instagram.com, "Create" |
| LinkedIn | `POST https://api.linkedin.com/rest/posts` (w_member_social), images via `/rest/images` | linkedin.com/feed, "Start a post" |
| TikTok | Content Posting API `/v2/post/publish/video/init/` (approved app) | tiktok.com/upload |
The browser uses the user's own signed-in session (the agent browser profile keeps logins). A login page: ask the
user to sign in with browser_handoff; a CAPTCHA or 2FA code: browser_handoff, then continue. Upload files with
browser_form/browser_click on the file input (paths inside the chat folder).

## 3. Monitor
Read new comments, mentions and statistics (API insights endpoints or the analytics pages), summarize them in a
table, draft replies and publish them only with approval. Respect the platforms' rate limits; never automate likes,
follows or mass messages.
