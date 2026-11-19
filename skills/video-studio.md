---
name: video-studio
title: Video production & studio editing
title_tr: Video üretimi ve stüdyo düzenleme
title_en: Video production & studio editing
description: Makes professional videos from photos, clips, text, logos, music and voice-over with the edit_video tool (Ken Burns motion, transitions, animated styled text, colour looks, ducked music, neural voices), and changes existing Video Studio projects with small patches.
description_tr: edit_video aracıyla fotoğraf, klip, yazı, logo, müzik ve seslendirmeden profesyonel videolar üretir (Ken Burns hareketi, geçişler, animasyonlu ve stilli yazılar, renk görünümleri, otomatik kısılan müzik, nöral sesler); var olan Video Stüdyosu projelerini küçük yamalarla düzenler.
description_en: Makes professional videos from photos, clips, text, logos, music and voice-over with the edit_video tool (Ken Burns motion, transitions, animated styled text, colour looks, ducked music, neural voices), and changes existing Video Studio projects with small patches.
triggers: videosu|video(yu|ya)? (yap|üret|oluştur|hazırla|düzenle|kurgula|kes|birleştir)|tanıtım videosu|montaj|(make|create|edit|cut|produce) (a|an|the|this|my) [\w ]{0,20}video|video (edit|studio)|slideshow
tools: edit_video, generate_video, animate_image, stock_photo, generate_image, text_to_speech, inspect_media, read_file, list_dir, todo
---
Every video is made by CALLING edit_video (never print its JSON as an answer). Report only what the edit_video
result says (length, scenes, layers, texts, voice, music); the user also sees the preview sheet it returns.

## 1. Plan (one short todo)
- Platform -> aspect: Reels / TikTok / Shorts "9:16", Instagram post "4:5" or "1:1", YouTube / web "16:9".
- Length: 6-15 s for ads and reels (3-5 s per scene), 20-60 s for presentations.
- Story: hook scene with a title -> 1-3 detail scenes with captions -> closing scene (brand, price, call to action).

## 2. Pictures
- Real photos: ONE stock_photo call, count = number of scenes, comma-separated English subjects
  ("coffee shop interior, friends drinking coffee, latte art"). Made-up visuals: generate_image (1280x720 or
  720x1280). Use the paths the tools return; files the user attached are in attachments/.
- Videos: check length and sound with inspect_media first.

## 3. Build it - the simple form is enough for most requests
```json
{"photos": ["images/a.jpg", "images/b.jpg", "images/c.jpg"], "title": "Kahve Dükkanı",
 "subtitle": "Her gün taze", "captions": ["", "Dostlarla bir mola", "Latte 85 TL"],
 "narration": ["Şehrin en sıcak köşesine hoş geldiniz.", "", "Sizi bekliyoruz."],
 "duration": 12, "music": "ambient", "look": "warm", "aspect": "16:9",
 "voice": {"voice": "tr-TR-EmelNeural", "rate": 1.0},
 "logo": {"src": "images/logo.png", "position": "top_right", "size": 0.14},
 "output": "videos/tanitim.mp4"}
```
- "animated, with sound, professional" = this form: motion, transitions, fades, music ducking are automatic.
- music: "ambient" | "upbeat" | "calm" (generated) or an audio file; look: warm | cinematic | vivid | bw | vintage | cool.
- voice: Microsoft neural voices (free), e.g. tr-TR-EmelNeural, tr-TR-AhmetNeural, en-US-JennyNeural,
  en-US-GuyNeural, de-DE-KatjaNeural; narration lines are read at the start of each scene.

## 4. Full control (exact cuts, styled and placed text, layers)
- scenes: [{"src", "dur", "in" (video start), "motion": zoom_in|zoom_out|pan_left|pan_right|pan_up|pan_down|none,
  "transition": fade|dissolve|slideleft|slideup|circleopen|wipeleft|smoothleft|zoomin|radial|fadeblack|cut,
  "fit": cover|blur|contain, "say": "voice line", "title" / "subtitle" / "caption" / "lower_third"}]
- A scene text can be a plain string (house style) or a styled object placed anywhere:
  {"text": "Latte 85 TL", "x": "6%", "y": "74%", "size_pct": 6, "color": "#ffffff", "box": "#E8A33D@0.9",
   "outline": "black", "bold": true, "font": "sans|serif|display|mono|script|condensed", "align": "center",
   "animation": "fade|slide_up|slide_left|pop|none"}  (x / y = top-left in % of the frame, or center / left / right)
- clips: free layers at exact times, drawn above the scenes:
  text {"type": "text", "text", "start", "dur", ...same style fields}; image / logo / sticker {"type": "image",
  "src", "start", "dur", "x", "y", "scale" (share of the frame width), "opacity"}; picture-in-picture
  {"type": "video", "src", "in", "dur", "scale", "x", "y"}; sound effect {"type": "audio", "src", "start", "volume"}.

## 5. Change a video that exists (the Video Studio project)
Every render writes <name>.timeline.json. To change it send ONLY the changes - never rewrite the JSON from memory
(voice lines and titles get lost):
```json
{"base": "videos/tanitim.timeline.json", "scenes": {"2": {"caption": {"text": "Yeni fiyat 79 TL", "color": "#ffd34d"}}},
 "logo": {"src": "images/logo.png", "position": "bottom_right"}, "music": "upbeat",
 "add_clips": [{"type": "text", "text": "%20 indirim", "start": 1, "dur": 4, "x": "60%", "y": "10%",
                "size_pct": 8, "box": "red@0.85", "bold": true, "animation": "pop"}]}
```
Scene numbers start at 1; a field set to null is removed; "remove_scenes": [3] drops a scene. The user watches the
change live in the Video Studio and can fine-tune it there by hand.

## 6. Check before you answer
- The result must show the scenes, layers and texts you meant; "NOT APPLIED" lists fields that were ignored - fix
  them and call again. "black from ..." means a gap: fix the timing.
- Look at the preview sheet (inspect_media on the video for details). Then say in two lines what was made and that
  the user can open it in the Video Studio (the Studio button on the video card) to drag texts and logos, change
  colours, music and voices.
