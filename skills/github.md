---
name: github
title: GitHub work (issues, branches, pull requests)
title_tr: GitHub çalışması (issue, dal, pull request)
title_en: GitHub work (issues, branches, pull requests)
description: Works on GitHub through the connected GitHub MCP server, like Codex: reads issues, fixes them on a new branch, runs the tests, opens a pull request and answers review comments; asks before pushing, merging or deleting.
description_tr: Bağlı GitHub MCP sunucusu ile Codex gibi çalışır: issue'ları okur, yeni bir dalda düzeltir, testleri çalıştırır, pull request açar ve inceleme yorumlarını yanıtlar; push, merge ve silme öncesi onay ister.
description_en: Works on GitHub through the connected GitHub MCP server, like Codex: reads issues, fixes them on a new branch, runs the tests, opens a pull request and answers review comments; asks before pushing, merging or deleting.
tools: mcp, run, read_file, write_file, edit_file, list_dir, search_code, todo
---
GitHub is reached through the `mcp` tool, server `github` (set up in Settings > Connections; if it is missing, tell
the user to connect GitHub there - never ask for a token in the chat). Local work happens in the project folder with
git (`run`, shell="exec").

## Find out where you are
- `git remote get-url origin` gives owner/repo; `git status`, `git branch --show-current`.
- mcp github `get_me` (who is signed in), `list_issues` / `issue_read`, `list_pull_requests` / `pull_request_read`,
  `search_code` for the remote side.

## Work on an issue or a change (the Codex flow)
1. Read the issue (issue_read) and the code it touches; write the plan with todo.
2. Start from an up-to-date default branch: `git fetch origin`, `git switch -c aiiq/<short-topic> origin/<default>`.
   Never work directly on main/master.
3. Make the change, run the project's tests / build and fix until they pass.
4. `git add -A`, `git commit -m "<what and why>"` (mention `Fixes #<n>` for an issue).
5. Ask the user before `git push -u origin <branch>`; after the yes push it and open the PR with mcp github
   `create_pull_request` (title, body: what changed, how it was tested, `Fixes #<n>`; draft when unsure).
6. Review comments: `pull_request_read` (comments / reviews), fix, commit, push to the same branch, answer with
   `add_reply_to_pull_request_comment`.

## Always ask first (exact action in the question)
push, create/merge/close a pull request, create/delete a branch or repository, delete_file, push_files,
update_pull_request_branch, write comments or issues in the user's name. Reading, searching and local commits need
no approval. Never force-push, never rewrite published history, never merge your own PR without an explicit yes.
