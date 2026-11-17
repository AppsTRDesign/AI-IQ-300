---
name: graphics
title: Logo, image and media design
title_tr: Logo, görsel ve medya tasarımı
title_en: Logo, image and media design
description: Designs professional logos, icons, banners, social media visuals and illustrations as SVG and PNG; edits, resizes, traces and compresses images and video quickly with Skia, drawsvg, Pillow, sharp, vtracer and ffmpeg.
description_tr: SVG ve PNG olarak profesyonel logo, ikon, banner, sosyal medya görseli ve illüstrasyon tasarlar; Skia, drawsvg, Pillow, sharp, vtracer ve ffmpeg ile görsel ve videoları hızlıca düzenler, boyutlandırır, vektöre çevirir ve sıkıştırır.
description_en: Designs professional logos, icons, banners, social media visuals and illustrations as SVG and PNG; edits, resizes, traces and compresses images and video quickly with Skia, drawsvg, Pillow, sharp, vtracer and ffmpeg.
tools: run, write_file, read_file, list_dir, browser_check, todo
---
Design like a professional: a clear concept, a limited palette (2-3 colors + neutral), one or two good fonts,
generous spacing, perfect alignment. Deliver vector (SVG) plus raster (PNG) exports and show them.

## Tools (all installed; one python script per step with run, shell=python)
- Logo / icon / vector: **drawsvg** (shapes, paths, gradients, text) -> `d.save_svg("logo.svg")`.
  Text as outlines for a portable logo: Node **opentype.js** (`font.getPath(text, x, y, size).toSVG()`).
- Raster rendering and effects: **skia-python** (anti-aliasing, gradients, shadows, blur, rounded rects, real font
  shaping). SVG -> PNG: `skia.SVGDOM.MakeFromStream(skia.Stream.MakeFromFile("logo.svg"))` then render on a
  surface, or Node **@resvg/resvg-js** (`new Resvg(svg, {fitTo:{mode:"width",value:1024}}).render().asPng()`).
- Photo edits: **Pillow** (crop, resize, text, compose), **opencv** (masks, background removal with grabCut,
  color), **sharp** in Node for very fast resize / convert / WebP / AVIF.
- Raster logo -> vector: **vtracer** (`vtracer.convert_image_to_svg_py(inp, out, colormode="color")`).
- QR code: **qrcode**. GIF / frames: imageio. Video: **ffmpeg** (scale, crop, overlay a logo, text, compress
  with `-c:v libx264 -crf 23 -preset fast`, GIF with palettegen).
- Fonts: matplotlib's DejaVu Sans covers Turkish; system fonts are in C:/Windows/Fonts, /Library/Fonts,
  /usr/share/fonts. Check that every character of the text exists in the font.

## Workflow
1. Brief: name, sector, style words, colors, where it is used. Make 3 distinct concepts as small PNG previews
   in one sheet, choose (or let the user choose), then refine.
2. Final pack in a folder: logo.svg, logo.png (1024 px, transparent), dark/light variants, icon (512 px square),
   favicon.ico (16/32/48), social sizes when asked.
3. Look at the result (read_file the PNG or browser_check the SVG) before saying it is done; fix overlaps,
   cut-off text and low contrast.
