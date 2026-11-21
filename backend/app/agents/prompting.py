"""The system prompt of a task: rules, capabilities, tools, skills and agents to choose from, the chat's opened abilities, and @mentions.

Split out of orchestrator.py (round 2026-11-20); every name here is re-exported there."""
from __future__ import annotations

import asyncio
import base64
import itertools
import hashlib
import json
import re
import time
import uuid
from collections import deque
from pathlib import Path
from dataclasses import dataclass, field

from .. import approvals, db, sessions, tokens, workspace
from ..config import load_settings, redact
from ..process_manager import manager as proc_manager
from ..events import bus
from ..llm import memguard, modelstats, router
from ..llm.usage import cooldown as usage_cooldown
from ..llm.providers import ProviderError
from ..tools.symbols import project_map
from ..tools.registry import figures as registry_figures
from ..tools.registry import READ_ONLY, TOOLS, ToolContext, ToolResult, clip, split_args, todo_patch, tool_schemas, tools_prompt
from ..tools.browser_tools import BROWSER_TOOLS, label as _browser_label
from . import catalog
from .stream_parser import LEAK, THINK_OPENERS, StreamSplitter, ToolCall, attrs, extract_inline_calls, parse_tool

# Prompt texts and the intent/check rules live in their own modules; their names are re-exported here.
from .prompts import *  # noqa: F401,F403
from .checks import *  # noqa: F401,F403
from .prompts import HISTORY_MESSAGES, LOCAL_HISTORY, OS_NAME, SHELLS, SUMMARY_TAG, DEFAULT_ROLE, SYSTEM_CORE, CAP_HEAD, CAPABILITIES, WORK_TOOLS, WORK_RULES_LEAN, CAP_HEAD_LEAN, CAPABILITIES_LEAN, CHAT_NOTE, ABILITY_ASK, RULE_TOPICS_LEAN, BROWSER_GUIDE_LEAN, WEB_TOOLS, WORK_RULES, RULE_TOPICS, SCREENSHOT_RULE, ENV_SECTION, rule_topics, WEB_RULES, TAG_PROTOCOL  # noqa: F401
from .checks import plan_steps, request_steps, request_parts, error_playbook, NOT_FOUND, LANG_NAMES, SCRIPTS, TR_CHARS, TR_WORDS, EN_WORDS, _CJK, _load_intents, INTENTS, intent_alt, _extend, _lang_rx, LANG_WORD_RX, _lang_counts, reply_language, SMALL_TALK, ACTION, WORK, QUESTION, CORE_TOOLS, WEB_WORDS, GROUP_TOOLS, GROUPED, GROUP_WORDS, tool_groups, STRONG_BROWSER, BROWSER_WORDS, CODE_NOT_RUN, HOWTO, SHELL_FENCES, FENCE, CMD_START, fenced_commands, is_small_talk, FILE_NAME, _unread_files, CURRENT_INFO, needs_research, is_knowledge_question, ANNOUNCE, PROMISE, VISUAL_ASK, is_promise, is_announcement, FILE_CLAIM, ACTION_ECHO, CHANGE_REQUEST, CHANGE_CLAIM, FILE_EDIT_ASK, FILE_REF, DELIVER_VERB, DELIVERABLES, CLAIMED_FILE, _shown_files, tool_hint, missing_deliverables, FOREIGN_SCRIPT, TRANSLATE_HINT, LATIN_LANGS, CONTINUE_WORDS, wrong_language, _LANG_FILES, ui_text, think_reply_reminder, language_rule  # noqa: F401
from .continuity import _short_desc  # noqa: F401


# What a chat has opened and used so far (tool groups, skills), kept in its record: the next task of the same chat
# starts with them, so the model does not spend a round trip opening the same group or loading the same skill again.
ABILITIES = "abilities.json"


ABILITY_TASKS = 6  # a group not used for this many tasks closes again (its definitions cost tokens every turn)


def _abilities_load(session_id: str) -> dict:
    try:
        d = json.loads((sessions.path(session_id, create=False) / ABILITIES).read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _abilities_open(mem: dict) -> dict:
    """{"groups": [...], "skills": [...]} still fresh for the next task."""
    n = int(mem.get("task") or 0)
    groups = [g for g, at in (mem.get("groups") or {}).items() if g in GROUP_TOOLS and n - int(at) < ABILITY_TASKS]
    return {"groups": groups, "skills": [k for k in (mem.get("skills") or [])][-6:]}


def _abilities_save(run: "Run") -> None:
    try:
        mem = _abilities_load(run.session["id"])
        n = int(mem.get("task") or 0) + 1
        used = {(s.get("data") or {}).get("tool") for s in run.steps if s.get("status") == "done"}
        groups = dict(mem.get("groups") or {})
        for g, names in GROUP_TOOLS.items():
            if g in ("project", "mcp"):
                continue  # always on when available
            if names & used:  # really used (opened but never called does not stay open)
                groups[g] = n
        skills = [k for k in (mem.get("skills") or [])]
        for st in run.steps:
            if st.get("kind") == "skill" and st.get("status") == "done" and st.get("title") and st["title"] not in skills:
                skills.append(str(st["title"])[:60])
        from ..config import atomic_write
        atomic_write(sessions.path(run.session["id"]) / ABILITIES,
                     json.dumps({"task": n, "groups": {g: at for g, at in groups.items() if n - int(at) < ABILITY_TASKS},
                                 "skills": skills[-12:]}, ensure_ascii=False))
    except (OSError, ValueError, TypeError):
        pass


def _parse_mentions(text: str) -> tuple[str | None, list[str], str]:
    """'@tester' selects an agent role, '/webapp' loads a skill. Unknown names are left in the text. Several agents
    ("@coder write it, @debugger check it"): the first is the role, the others' instructions join in (see
    _extra_agents)."""
    agents, skills = catalog.agents(), catalog.skills()
    found = list(dict.fromkeys(m for m in re.findall(r"(?<!\S)@([\w-]+)", text) if m in agents))
    role = found[0] if found else None
    used = list(dict.fromkeys(m for m in re.findall(r"(?<!\S)/([\w-]+)", text) if m in skills))
    names = [*found, *used]
    clean = re.sub(r"(?<!\S)[@/](%s)(?![\w-])" % "|".join(map(re.escape, names)), "", text) if names else text
    return role, used, clean.strip() or text


BROWSER_GUIDE = (
    "# Browser agent\n"
    "browser_* tools open a real, visible browser window (its own profile keeps the user's sign-ins between tasks) "
    "to act on a website like a person: browser_navigate opens a page and returns it as a tree of elements with "
    "refs ([e12]); browser_click/browser_type/browser_key/browser_form act on a ref; browser_snapshot/browser_find "
    "read the page again (always re-read after an action that changes the page, never assume it worked); "
    "browser_batch runs several predictable steps at once. Use them to test a site or local app as a real user "
    "would (fill a form, click through, check the result), or to work inside an app the user is signed into. Never "
    "try to solve a CAPTCHA or bot check: call browser_handoff - the user solves it in the window and the task "
    "continues by itself as soon as it is done. Never type a card number on a real site. Passwords and risky buttons "
    "(send/delete/publish/sign up): on the site the user's request names in Full access mode (e.g. 'sign me up on "
    "mysite.com with password X') do it directly with the details the user gave; elsewhere call browser_handoff "
    "and let the user do that part, then continue. Pop-ups and cookie banners are closed automatically (the page "
    "says '[Closed automatically: ...]'); if one still blocks the page, close it yourself with its close/X button "
    "or browser_key Escape (cookie banners: always the reject / necessary-only choice) and go on. For plain information (facts, prices, a page's text) prefer "
    "research/fetch_url/web_search; use browser_* only when the task needs real interaction with a page.")


TEAM_GUIDE = (
    "# Multi-model teamwork\n"
    "Other cloud models of the pool can work for you: {models}.\n"
    "- When the user asks for a team, group, several agents or several models (takım, ekip, grup, çoklu ajan, "
    "çoklu model...), use the team tool: every member is a real agent on its own model with file, command and "
    "document tools. Parts that need an earlier part's result get a later stage (stage 2, 3...); they receive the "
    "earlier reports and file names. Put the whole pipeline in ONE team call.\n"
    "- ask_model is only for a text answer from one other model (a review, an analysis, a second opinion).\n"
    "- Call other models only when the user asks for it (a team, several agents or models, parallel work, another "
    "model's opinion); otherwise do the task yourself. When a team is done YOU check its results (read the files, "
    "run the tests), merge or compare them and write the final answer.\n"
    "- Never do the members' parts yourself and call it teamwork. When you report, say which model did which "
    "part exactly as the tool results (and the [Tool actions ...] notes of earlier turns) list them.")


def _system_prompt(role: str, root, session_id: str, project: dict | None, skill_names: list[str],
                   plan: str | None, native: bool, model: str = "", lang: str = "tr",
                   tools: set[str] | None = None, compact: bool = False,
                   extra_agents: list[str] | tuple = (), topics: frozenset = frozenset(), lean: bool = False,
                   request: str = "", chat_memory: dict | None = None) -> tuple[str, dict]:
    """tools: names offered this turn (None = all, empty = none). compact: short tool texts (small windows).
    lean: the short prompt for slow models (see WORK_RULES_LEAN). The order is: what never changes in a chat first
    (identity, rules, the capability index, the core tools), then what can change (tools of opened groups, the
    environment, state), so a local server re-reads only the tail when a group opens."""
    agents = catalog.agents()
    sizes: dict[str, int] = {}
    from .. import hostinfo
    # Static part first (the same for every chat on this model): identity, rules, capability map.
    parts = [SYSTEM_CORE.format(model=model, os_name=OS_NAME)]
    if tools is None or tools & WORK_TOOLS:
        parts.append(WORK_RULES_LEAN if lean else WORK_RULES)
        split = int((load_settings().get("agent") or {}).get("split_write_chars") or 0)
        if split > 0:  # Settings > Agent: the user wants very large files written in parts
            parts.append(f"- Files longer than ~{split:,} characters: write the first part with write_file, then each "
                         "next part with write_file append=true (continue exactly where the previous part ended).")
        parts += [(RULE_TOPICS_LEAN.get(k) if lean else None) or RULE_TOPICS[k][1] for k in sorted(topics) if k in RULE_TOPICS]
    if tools is None or tools & WEB_TOOLS:
        parts.append(WEB_RULES)
    if (tools is None or "web_screenshot" in tools) and not lean:
        parts.append(SCREENSHOT_RULE)
    asks_abilities = bool(ABILITY_ASK.search(request or ""))
    if tools is None or "need_tools" in tools:
        parts.append(CAPABILITIES_LEAN if lean else CAPABILITIES)
    elif not tools and lean and not asks_abilities:
        parts.append(CHAT_NOTE)  # a greeting does not need the whole map; "what can you do?" gets it (below)
    elif not tools:
        # A conversation turn has no tools, but the model must know everything it can do (and say so when asked:
        # "neler yapabilirsin?" got a generic answer, and later requests were refused as impossible).
        parts.append(CAPABILITIES.replace(CAP_HEAD, "# What you can do (no tools in this reply; when the user asks "
                                          "for any of this, it is done with tools in the next request)"))
    # The specialist agents (roles): the user calls them with @name; team members can take these roles.
    roles = {k: v for k, v in agents.items() if k != DEFAULT_ROLE}
    if roles and (tools is None or not tools or "need_tools" in tools):
        # Listed always (not only when the request says "agent"): the model itself may pick the specialist a part
        # of the job needs (team tool, role=name); the user can force one with @name.
        parts.append("# Agents (the user calls one with @name; you may give a part of the job to the specialist it "
                     "needs with the team tool, role=NAME - only when it clearly fits): "
                     + "; ".join(f"@{k} ({v.get('title_en') or v['title']})" for k, v in roles.items()))
    role_prompt = agents.get(role, agents.get(DEFAULT_ROLE, {})).get("prompt")
    if role_prompt:
        parts.append("# Instructions\n" + role_prompt)
    sizes["system"] = sum(map(tokens.count, parts))
    if tools is not None and not tools:
        sizes["tools"] = 0
    elif not native:
        # The core tools here (the same in every turn of a chat); tools of opened groups go to the end of the prompt.
        core = None if tools is None else (tools & CORE_TOOLS) or tools
        extra_tools = set() if tools is None else tools - core
        parts.append(TAG_PROTOCOL.format(tools=tools_prompt(core, compact or lean, lean)))
        sizes["tools"] = tokens.count(parts[-1])
    else:
        sizes["tools"] = 0  # native tool definitions travel beside the prompt: counted once per turn
    if tools is None or "mcp" in tools:
        from .. import mcp_client
        if section := mcp_client.prompt_section(request):
            parts.append(section)
            sizes["tools"] = sizes.get("tools", 0) + tokens.count(section)
    if tools is None or "team" in tools:
        pool = [e["model"] for e in router.pool() if e["model"].partition(":")[2] != model][:12]
        if pool:
            parts.append(TEAM_GUIDE.format(models=", ".join(pool)))
            sizes["tools"] = sizes.get("tools", 0) + tokens.count(parts[-1])
    tail: list[str] = []  # what can change while a chat goes on: after everything static
    if not native and tools and extra_tools:
        tail.append("# More tools (opened for this request)\n" + tools_prompt(extra_tools, compact or lean, lean))
        sizes["tools"] = sizes.get("tools", 0) + tokens.count(tail[-1])
    if tools is None or tools & BROWSER_TOOLS:  # only when at least one browser_* tool is actually offered
        tail.append(BROWSER_GUIDE_LEAN if lean else BROWSER_GUIDE)
        sizes["tools"] = sizes.get("tools", 0) + tokens.count(tail[-1])
    # Skill discovery: the model sees every skill's purpose and loads a matching one with use_skill.
    available = {k: v for k, v in catalog.skills().items() if k not in skill_names}
    # Skill choice is the model's: every skill with its purpose, and the rule to load one only when the request's
    # GOAL needs it (trigger words loaded unrelated skills - a PDF about Android loaded mobile-app-test).
    choose = ("# Skills - you choose: if the request's goal clearly needs one, call use_skill NAME first and follow "
              "it; if none fits, use none (a word in the request is not a reason). The user can also force one with "
              "/name.\n")
    if available and lean and (tools is None or "use_skill" in tools):
        parts.append(choose + "; ".join(f"{k}: {_short_desc(v, 70)}" for k, v in available.items()))
        sizes["skills"] = tokens.count(parts[-1])
    elif available and not lean and (tools is None or "use_skill" in tools or not tools):
        parts.append(choose + "\n".join(f"- {k}: {_short_desc(v, 160)}" for k, v in available.items()))
        sizes["skills"] = tokens.count(parts[-1])
    parts += tail
    mem = chat_memory or {}
    if mem.get("groups") or mem.get("skills"):
        # What this chat already opened and used: the model does not ask for it again (no need_tools round trip).
        parts.append("# Already open in this chat\n"
                     + (f"Tool groups: {', '.join(sorted(mem['groups']))} (their tools are callable now). " if mem.get("groups") else "")
                     + (f"Skills used earlier: {', '.join(mem['skills'])} (load one again only if you need its text)."
                        if mem.get("skills") else ""))
        sizes["system"] += tokens.count(parts[-1])
    # Per chat / per day from here on.
    parts.append(ENV_SECTION.format(os_line=hostinfo.os_line(), root=root, date=hostinfo.clean_text(time.strftime("%Y-%m-%d %H:%M (%A)")) + f", time zone {hostinfo.tz_name()} - this is the real current date and time of this computer; never guess another year",
                                    project=f"\nProject: {project['name']}" if project else ""))
    if tools is None or tools & {"run", "start"}:  # the real OS build, shells and tool versions
        parts.append(hostinfo.prompt_section(short=lean))
    sizes["system"] += sum(map(tokens.count, parts[-2:])) if tools is None or tools & {"run", "start"} else tokens.count(parts[-1])
    # The user's lasting rules: global ones (Settings) and the project's AIIQ.md. Read once per task (stable prompt).
    # Headings inside the rule texts are flattened, so they cannot break the prompt's own sections.
    flat = lambda text: re.sub(r"(?m)^#+[ \t]*", "", text).strip()  # noqa: E731
    global_rules = flat(load_settings().get("rules") or "")
    project_rules = flat(workspace.read_rules(project))
    if global_rules or project_rules:
        parts.append("# Rules from the user (always follow them; they override the defaults above)"
                     + (f"\n## For every chat\n{global_rules[:workspace.RULES_MAX]}" if global_rules else "")
                     + (f"\n## For this project ({workspace.RULES_FILE})\n{project_rules}" if project_rules else ""))
        sizes["project" if project_rules else "system"] = sizes.get("project" if project_rules else "system", 0) + tokens.count(parts[-1])
    if project:
        parts.append("# Project files\n" + workspace.summarize_tree(root, 30 if lean else 60))
        code_map = "" if lean else project_map(root)  # lean: the symbols / search_code tools answer the same on demand
        if code_map:  # where things are defined: search_code / symbols / read_file lines=... go straight there
            parts[-1] += "\n\n# Code map (definitions per file)\n" + code_map
        sizes["project"] = sizes.get("project", 0) + tokens.count(parts[-1])
    state = sessions.state_file(session_id)
    if state.exists():
        parts.append("# Session state\n" + state.read_text(encoding="utf-8", errors="replace")[:900 if lean else 2000])
        sizes["state"] = tokens.count(parts[-1])
    skills = catalog.skills()
    skill_parts = [f"# Active skill /{s}: {skills[s]['title']} (the user invoked it for the latest request; "
                   f"apply these instructions to that request)\n{skills[s]['prompt']}" for s in skill_names if s in skills]
    skill_parts += [f"# Also invoked agents\n## @{a}: {agents[a]['title']} (do its part of the latest request)\n"
                    f"{agents[a]['prompt']}" for a in extra_agents if a in agents]
    parts += skill_parts
    sizes["skills"] = sizes.get("skills", 0) + sum(map(tokens.count, skill_parts))
    if plan:
        parts.append("# Plan to follow\n" + plan)
        sizes["plan"] = tokens.count(parts[-1])
    parts.append(language_rule(lang, lean))  # last, so it carries the most weight
    sizes["system"] += tokens.count(parts[-1])
    return "\n\n".join(parts), sizes
