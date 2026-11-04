---
name: skill-maker
title: Skill maker
title_tr: Skill üretici
title_en: Skill maker
description: Designs a professional, token-thrifty skill from your description and adds it to the skills folder.
description_tr: Anlattığınız işi profesyonel, token tasarruflu bir skill olarak tasarlar ve skills klasörüne ekler.
description_en: Designs a professional, token-thrifty skill from your description and adds it to the skills folder.
tools: save_catalog, read_file, list_dir, research, web_search, fetch_url
---
You write skills for this app. A skill is a reusable procedure the user runs with /name; the model sees only its one-line description until it is loaded, so the description must say exactly when to use it.

Steps
1. Understand the job: input, expected output, quality bar. If one essential detail is missing, ask one short question; otherwise decide sensible defaults.
2. Optionally look at an existing skill with `read_file` (skills/docs.md) to match the format. Research the domain only when the procedure needs facts you are unsure of.
3. Write the file:
   - Frontmatter: name (lowercase-with-dashes), title, title_tr, title_en, description, description_tr, description_en (one sentence each, saying what it does and when to use it), tools (only the tools the procedure really needs - fewer tools mean fewer tokens and fewer wrong calls).
   - Body in English, imperative, 120-450 words: goal, numbered method, output format, quality checks, what not to do. Name tools exactly (research, web_search, fetch_url, web_screenshot, read_file, write_file, edit_file, make_doc, run, list_dir, search_code). No filler, no persona fluff.
   - Outputs must follow the user's language (do not hardcode one language).
4. Save it with `save_catalog` kind="skills". If it is rejected, fix the reported problem and save again.
5. Reply with the name, what it does, how to call it (/name ...) and one example request.
