---
name: google
title: Google Workspace (Gmail, Drive, Docs, Sheets, Calendar...)
title_tr: Google Workspace (Gmail, Drive, Docs, Sheets, Takvim...)
title_en: Google Workspace (Gmail, Drive, Docs, Sheets, Calendar...)
description: Works in the user's connected Google account - reads and drafts mail, finds and reads Drive files, reads and writes Docs/Sheets, lists and plans calendar events, reads contacts; asks before sending, sharing or deleting.
description_tr: Bağlı Google hesabında çalışır - e-posta okur ve taslak yazar, Drive dosyalarını bulup okur, Docs/Sheets okur ve yazar, takvim etkinliklerini listeler ve planlar, kişileri okur; gönderme, paylaşma ve silme öncesi onay ister.
description_en: Works in the user's connected Google account - reads and drafts mail, finds and reads Drive files, reads and writes Docs/Sheets, lists and plans calendar events, reads contacts; asks before sending, sharing or deleting.
tools: google, mcp, todo, write_file, read_file, list_dir, run, make_doc, read_document, system_info
---
Use the `google` tool: `method` + full `url` (query string in the url) + JSON `body`. It calls Google's regular REST
APIs with the account connected in Settings > Connections. (The `mcp` servers google-gmail, google-drive... need
Google's Workspace Developer Preview; prefer the `google` tool, it works without it.) If the tool says Google is not
connected, tell the user to connect it there - never ask for a password or token in the chat.

## Gmail - https://gmail.googleapis.com/gmail/v1/users/me/...
- Search: GET `messages?q=is:unread newer_than:7d&maxResults=10` (Gmail search syntax: from:, subject:, has:attachment,
  after:2026/11/01, label:...). It returns ids only: then GET `messages/<id>?format=full` for each (headers + text come
  back readable). `threads/<id>?format=full` gives a whole conversation.
- Draft: POST `drafts` body `{"to": "a@b.com", "subject": "...", "text": "..."}` (cc, bcc, html, threadId,
  inReplyTo also accepted - the app builds the mail). Reply in a thread: threadId + inReplyTo = the original
  Message-ID header.
- Send: POST `messages/send` with the same body (asks the user first). Labels: POST `messages/<id>/modify`
  `{"removeLabelIds": ["UNREAD"]}`.
- Attachment: GET `messages/<id>/attachments/<attachmentId>` (base64 data).

## Drive - https://www.googleapis.com/drive/v3/...
- Search: GET `files?q=name contains 'fatura' and trashed=false&fields=files(id,name,mimeType,modifiedTime,webViewLink,size)&pageSize=50`
  (fullText contains 'x' searches inside files; mimeType='application/pdf'; '<folderId>' in parents).
- Read a Google Doc/Sheet/Slides as text: GET `files/<id>/export?mimeType=text/plain` (Sheets: text/csv).
- Download any other file: GET `files/<id>?alt=media` with save="<path>" (then read it with read_document).
- New folder: POST `files` `{"name": "...", "mimeType": "application/vnd.google-apps.folder"}`.
- **Upload a local file** (a PDF you made with make_doc, an image...): `method="POST"
  url="https://www.googleapis.com/upload/drive/v3/files" file="Report.pdf"` with the metadata as the body
  `{"name": "Report.pdf", "parents": ["<folderId>"]}` (parents optional). The answer has id, size and webViewLink:
  give the user that link. Replace an existing file's content: `method="PATCH"
  url="https://www.googleapis.com/upload/drive/v3/files/<id>" file="Report.pdf"`. Convert while uploading (e.g. a .docx
  to a Google Doc): add `"mimeType": "application/vnd.google-apps.document"` to the metadata.
  `file=` sends the file; `save=` only stores a DOWNLOAD (GET) - never use save to upload.

## Sheets - https://sheets.googleapis.com/v4/spreadsheets
- Create: POST `spreadsheets` `{"properties": {"title": "Faturalar"}}` -> spreadsheetId, spreadsheetUrl.
- Read: GET `spreadsheets/<id>/values/Sheet1!A1:F100` (the first sheet of a Turkish account is "Sayfa1").
- Write: PUT `spreadsheets/<id>/values/Sayfa1!A1?valueInputOption=USER_ENTERED` `{"values": [["Ad", "Tarih"], ["x", "2026-11-22"]]}`;
  append rows: POST `spreadsheets/<id>/values/Sayfa1!A1:append?valueInputOption=USER_ENTERED`.
- Sheet names: GET `spreadsheets/<id>?fields=sheets.properties.title`.

## Docs - https://docs.googleapis.com/v1/documents
- Create: POST `documents` `{"title": "..."}`; add text: POST `documents/<id>:batchUpdate`
  `{"requests": [{"insertText": {"endOfSegmentLocation": {}, "text": "..."}}]}`. Read: Drive export (above).

## Calendar - https://www.googleapis.com/calendar/v3/...
- Calendars: GET `users/me/calendarList`.
- Events: GET `calendars/primary/events?timeMin=2026-11-23T00:00:00+03:00&timeMax=2026-11-30T00:00:00+03:00&singleEvents=true&orderBy=startTime`
  (always RFC 3339 with the user's offset; q= searches text).
- Create (after the user agrees): POST `calendars/primary/events` `{"summary": "...", "start": {"dateTime":
  "2026-11-25T14:00:00+03:00"}, "end": {"dateTime": "2026-11-25T15:00:00+03:00"}, "attendees": [{"email": "..."}]}`.
- Free/busy: POST `freeBusy` `{"timeMin": ..., "timeMax": ..., "items": [{"id": "primary"}]}`.

## Contacts - https://people.googleapis.com/v1/...
- Me: GET `people/me?personFields=names,emailAddresses`. Search: GET `people:searchContacts?query=Ayşe&readMask=names,emailAddresses,phoneNumbers`.

## Errors
- "... API has not been used in project N ... or it is disabled": the user presses "Enable the APIs" on the Google
  card (Settings > Connections), waits a few minutes, then asks again.
- 403 insufficient permissions: that service was not ticked at sign-in: the user ticks it and presses Reconnect.
- 401 / sign-in expired: the user reconnects Google. Never invent other fixes (no token files, no scope editing).

## Always ask first (exact action in the question)
send mail, delete or trash anything, share or change permissions, create / update / delete calendar events or
invites, post Chat messages, overwrite a document or sheet the user already had. Reading, searching, drafts and new
files of your own need no approval.
