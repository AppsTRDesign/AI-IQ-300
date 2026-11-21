"""Ready-made MCP servers (Settings > MCP > Catalog): one click adds one, switched on.

Each entry is a server that works as written: hosted ones (http) answer at their URL, local ones (stdio) start with
npx / uvx. "auth" says what the user still has to do after adding it:
  ""       nothing (public),
  "oauth"  sign in from the server row (browser sign-in, the app keeps the token),
  "header" an API key / token as a header (the form opens with `hint` filled in).
Descriptions live in languages/*.json as mcp_p_<id>; categories as mcp_cat_<category>.
"""

CATALOG: list[dict] = [
    # documentation and knowledge
    {"id": "deepwiki", "label": "DeepWiki", "category": "docs", "transport": "http", "url": "https://mcp.deepwiki.com/mcp"},
    {"id": "context7", "label": "Context7", "category": "docs", "transport": "http", "url": "https://mcp.context7.com/mcp"},
    {"id": "microsoft-learn", "label": "Microsoft Learn", "category": "docs", "transport": "http",
     "url": "https://learn.microsoft.com/api/mcp"},
    {"id": "cloudflare-docs", "label": "Cloudflare Docs", "category": "docs", "transport": "http",
     "url": "https://docs.mcp.cloudflare.com/mcp"},
    {"id": "huggingface", "label": "Hugging Face", "category": "ai", "transport": "http", "url": "https://huggingface.co/mcp"},
    # development
    {"id": "github", "label": "GitHub", "category": "dev", "transport": "http", "url": "https://api.githubcopilot.com/mcp/",
     "auth": "header", "hint": "Authorization=Bearer <GitHub token>"},
    {"id": "sentry", "label": "Sentry", "category": "dev", "transport": "http", "url": "https://mcp.sentry.dev/mcp", "auth": "oauth"},
    {"id": "git", "label": "Git", "category": "dev", "transport": "stdio", "command": "uvx", "args": "mcp-server-git"},
    {"id": "playwright", "label": "Playwright", "category": "dev", "transport": "stdio", "command": "npx",
     "args": "-y @playwright/mcp@latest"},
    # productivity
    {"id": "notion", "label": "Notion", "category": "work", "transport": "http", "url": "https://mcp.notion.com/mcp", "auth": "oauth"},
    {"id": "linear", "label": "Linear", "category": "work", "transport": "http", "url": "https://mcp.linear.app/mcp", "auth": "oauth"},
    # utilities
    {"id": "fetch", "label": "Fetch", "category": "tools", "transport": "stdio", "command": "uvx", "args": "mcp-server-fetch"},
    {"id": "time", "label": "Time", "category": "tools", "transport": "stdio", "command": "uvx", "args": "mcp-server-time"},
    {"id": "memory", "label": "Memory", "category": "tools", "transport": "stdio", "command": "npx",
     "args": "-y @modelcontextprotocol/server-memory"},
    {"id": "sequential-thinking", "label": "Sequential Thinking", "category": "tools", "transport": "stdio", "command": "npx",
     "args": "-y @modelcontextprotocol/server-sequential-thinking"},
    {"id": "everything", "label": "Everything (test)", "category": "tools", "transport": "stdio", "command": "npx",
     "args": "-y @modelcontextprotocol/server-everything"},
]

CATEGORIES = ["docs", "dev", "work", "ai", "tools"]


def catalog() -> dict:
    return {"categories": CATEGORIES,
            "servers": [{"auth": "", "url": "", "command": "", "args": "", "hint": "", **x, "note": f"mcp_p_{x['id']}"}
                        for x in CATALOG]}
