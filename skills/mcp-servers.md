---
name: mcp-servers
title: Add MCP servers
title_tr: MCP sunucusu ekleme
title_en: Add MCP servers
description: Finds an MCP server for a need (GitHub, databases, Slack, Notion, files, browsers...) on npm, PyPI or GitHub, connects it with mcp_add, checks its tools and uses them through the mcp tool.
description_tr: Bir ihtiyaç için MCP sunucusu bulur (GitHub, veritabanları, Slack, Notion, dosyalar, tarayıcılar...), npm, PyPI veya GitHub'dan mcp_add ile bağlar, araçlarını kontrol eder ve mcp aracıyla kullanır.
description_en: Finds an MCP server for a need (GitHub, databases, Slack, Notion, files, browsers...) on npm, PyPI or GitHub, connects it with mcp_add, checks its tools and uses them through the mcp tool.
tools: mcp_add, mcp, run, web_search, fetch_url, research, read_file, list_dir, todo
---
MCP (Model Context Protocol) servers add tools. Connect one only when the built-in tools cannot do the job.

## 1. Find the server (fast)
- Official reference servers: github.com/modelcontextprotocol/servers (filesystem, git, fetch, memory, time...).
  Registry: registry.modelcontextprotocol.io. Search: `npm search mcp <topic>` or web_search "<topic> MCP server".
- Prefer the vendor's own server (GitHub: `ghcr.io/github/github-mcp-server` or the hosted
  `https://api.githubcopilot.com/mcp/`; Notion, Stripe, Supabase, Cloudflare... publish theirs).
- Read its README (fetch_url) for the exact command and required env vars / tokens.

## 2. Connect with mcp_add
| Source | command | args |
|---|---|---|
| npm package | `npx` | `["-y", "<package>"]` |
| PyPI package | `uvx` (or `python -m`) | `["<package>"]` (no uvx: `run` pip install <package>, then `python -m <module>`) |
| GitHub repo | clone it first: `run` argv `["git","clone","--depth","1","<url>","mcp/<name>"]`, install (`npm install && npm run build` or `pip install -e .`), then command `node` / `python` with the built entry file |
| Remote server | url `https://...` (token in env as `Authorization=Bearer ...`) |
Tokens the user gave go in the body as JSON (`{"GITHUB_PERSONAL_ACCESS_TOKEN": "..."}`); they are stored in the
secret store, never in files. If the server does not start, mcp_add returns its error: run the same command once
with `run` (timeout 30) to see the output, fix (missing token, Node/Python version, wrong entry file), call
mcp_add again with the same id.

## 3. Use
mcp_add returns the tool names; call them with `mcp` (server = the id). The server stays connected for later chats
and is visible in Settings > MCP. Remove one with mcp_add remove=true.
