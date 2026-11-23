"""Agent teams (cloud multi-model pool): the main agent splits work into parts; each member runs its own tool loop
on a pool model. Members of one stage run at the same time; a later stage (a part that needs an earlier result)
starts when the earlier stages are finished and gets their reports and files. A live task board (one 'team' step)
shows every member's stage, model, state, step count and report."""
from __future__ import annotations

import asyncio
import dataclasses
import json
import re
import time

from ..config import redact
from ..llm import router
from ..llm.providers import ProviderError
from ..tools.browser_tools import BROWSER_TOOLS
from ..tools.registry import TOOLS, ToolContext, ToolResult, clip, split_args, tool_schemas

MEMBER_TOOLS = {"read_file", "list_dir", "search_code", "symbols", "impact", "write_file", "edit_file", "run",
                "web_search", "fetch_url", "research", "web_screenshot", "make_doc", "places", "read_document"} | BROWSER_TOOLS
MAX_MEMBERS = 6
MAX_TURNS = 16
MEMBER_SYSTEM = (
    "You are '{title}', one member of an AI agent team working in parallel in the same folder: {root}\n"
    "Other members handle the other parts at the same time; do ONLY your part and do not touch files outside it.\n"
    "Use the tools to do real work (write/edit files, run commands to check them). Write complete files, never "
    "placeholders. When your part is done, reply with a short report: what you did, which files you changed, "
    "anything left open. Think, write notes and write the report in {language}.\n"
    "The user's whole request (for context; use its exact paths and file names): {goal}\n"
    "Teamwork: your teammates are {mates}. Use team_message to tell them what they need from you (an API shape, a "
    "file name, a finished part) and team_tasks for the shared task list (add extra work you find, claim a task "
    "before doing it, mark it done). Their messages to you arrive together with your tool results.{rules}"
)

# Team-only tools, handled inside the team (not in the main registry).
TEAM_TOOLS = [
    {"name": "team_message", "description": "Send a short message to one teammate (by title) or to all.",
     "parameters": {"type": "object", "properties": {
         "to": {"type": "string", "description": "A teammate's title, or 'all'"},
         "text": {"type": "string", "description": "The message"}}, "required": ["text"]}},
    {"name": "team_tasks", "description": "The team's shared task list: list it, add a task, claim one, or mark one done.",
     "parameters": {"type": "object", "properties": {
         "action": {"type": "string", "enum": ["list", "add", "claim", "done"]},
         "text": {"type": "string", "description": "Task text (add)"},
         "id": {"type": "integer", "description": "Task number (claim / done)"}}, "required": ["action"]}},
]


class Shared:
    """What the members of one team share: messages and a task list (shown live on the task board)."""

    def __init__(self, board: list[dict]):
        self.messages: list[dict] = []
        self.tasks = [{"id": i + 1, "text": c["title"], "owner": c["title"], "status": "in_progress"} for i, c in enumerate(board)]
        self.read: dict[str, int] = {}

    def inbox(self, me: str) -> str:
        start = self.read.get(me, 0)
        self.read[me] = len(self.messages)
        new = [m for m in self.messages[start:] if m["from"] != me and m["to"] in ("all", me)]
        return "\n".join(f"- {m['from']}{'' if m['to'] == 'all' else ' (to you)'}: {m['text']}" for m in new)

    def tasks_text(self) -> str:
        return "\n".join(f"#{t['id']} [{t['status']}] {t['text']}" + (f" ({t['owner']})" if t["owner"] else "") for t in self.tasks)

    def handle(self, me: str, titles: list[str], name: str, args: dict) -> ToolResult:
        if name == "team_message":
            text = str(args.get("text", "")).strip()[:1000]
            to = str(args.get("to") or "all").strip()
            if not text:
                return ToolResult(False, "Empty message.")
            if to != "all" and to not in titles:
                match = next((t for t in titles if t.lower() == to.lower()), None)
                if not match:
                    return ToolResult(False, f"No teammate '{to}'. Teammates: {', '.join(t for t in titles if t != me)} or 'all'.")
                to = match
            self.messages.append({"from": me, "to": to, "text": text, "ts": time.time()})
            return ToolResult(True, f"Message sent to {to}.")
        action = args.get("action", "list")
        if action == "add":
            text = str(args.get("text", "")).strip()[:300]
            if not text:
                return ToolResult(False, "Give the task text.")
            self.tasks.append({"id": len(self.tasks) + 1, "text": text, "owner": "", "status": "open"})
        elif action in ("claim", "done"):
            t = next((t for t in self.tasks if t["id"] == int(args.get("id") or 0)), None)
            if not t:
                return ToolResult(False, "No such task number.\n" + self.tasks_text())
            if action == "claim":
                if t["owner"] and t["owner"] != me and t["status"] != "done":
                    return ToolResult(False, f"Task #{t['id']} belongs to {t['owner']}.")
                t.update(owner=me, status="in_progress")
            else:
                t.update(status="done", owner=t["owner"] or me)
        return ToolResult(True, "Shared tasks:\n" + self.tasks_text())


async def _member(ctx: ToolContext, m: dict, board: list[dict], i: int, push, shared: Shared) -> None:
    card = board[i]
    titles = [c["title"] for c in board]
    tried: set[str] = set()
    log: list[str] = []  # what this member has done so far, whichever model did it (see the switch below)
    sub = dataclasses.replace(ctx, step=lambda kind, data: None, files_changed=ctx.files_changed, commands=ctx.commands)
    while True:
        if card.get("reserved") and not tried:
            model, why = card.pop("reserved"), ""
        else:
            busy = {c["model"] for c in board if c["state"] == "running" and c.get("model")}
            model, why = await router.pick(m.get("need") or "code", len(m["task"]) // 3 + 4000, exclude=tried | busy,
                                           avoid={x.partition(":")[0] for x in busy})
        if not model:  # every model busy in this team: share one rather than fail
            model, why = await router.pick(m.get("need") or "code", 6000, exclude=tried)
        if not model:
            card.update(state="error", report=f"No pool model available ({why}).")
            push()
            return
        tried.add(model)
        card.update(model=model, state="running", started=time.time())
        push()
        sub.model = model
        rules = ""
        if ctx.project:
            from .. import workspace
            if r := workspace.read_rules(ctx.project).strip():
                rules = "\n\nProject rules:\n" + r[:3000]
        mates = ", ".join(t for t in titles if t != m["title"]) or "none"
        from .orchestrator import LANG_NAMES
        system = MEMBER_SYSTEM.format(title=m["title"], root=ctx.root, rules=rules, mates=mates,
                                      language=LANG_NAMES.get(ctx.lang, ctx.lang), goal=ctx.goal or "(not given)")
        plan = "\n".join(f"- {c['title']} (stage {c['stage']}{', running now in parallel with you' if c['stage'] == card['stage'] else ''}): "
                         f"{c['task'][:220]}" for c in board if c["title"] != m["title"])
        team_note = (f"\n\n[Team plan - your teammates and their parts. Do only YOUR part; do not redo theirs. Members of "
                     f"your stage work at the same time: agree on shared names (files, functions) with team_message "
                     f"right away when your parts touch, and read their messages.]\n{plan}") if plan else ""
        if (role := str(m.get("role") or m.get("agent") or "").lstrip("@").strip()):
            # The lead model chose a specialist for this part (team member role=NAME): its instructions go along.
            from . import catalog
            if (spec := catalog.agents().get(role)) and spec.get("prompt"):
                system += f"\n\n# You act as the specialist @{role}\n" + spec["prompt"][:6000]
        native = router.native_tools(model, await router.context_info(model))
        if not native:
            # This model has no function calling: it writes tool calls as tags (parsed below like the main task).
            from ..tools.registry import tools_prompt
            system += ("\n\n# Tool protocol\nCall tools by writing tags; their results arrive in the next message.\n"
                       + tools_prompt(MEMBER_TOOLS, True)
                       + '\n- <tool name="team_message" to="all">text</tool>\n  Message a teammate (by title) or all.')
        progress = ""
        if log or card.get("files"):
            # This part was started on another model (it failed or ran out of quota) or in a task that was
            # interrupted: the new model gets the exact record and goes on from there. Starting the part from
            # scratch wrote the same files again and ran the same commands twice.
            progress = ("\n\n[App record - this part was already started; what is listed is DONE and stays valid]\n"
                        + (f"Files written (they exist; read one only if you must change it, then edit_file): "
                           f"{', '.join(card.get('files') or [])}\n" if card.get("files") else "")
                        + ("Steps already made:\n" + "\n".join(f"- {x}" for x in log[-40:]) + "\n" if log else "")
                        + "Do not write, read or run any of it again. Continue with what is still missing, then report.")
        messages = [{"role": "system", "content": system},
                    {"role": "user", "content": m["task"] + team_note + progress}]
        retries = 0
        try:
            for _ in range(MAX_TURNS):
                if ctx.cancel.is_set():
                    raise asyncio.CancelledError
                # A long member task stays inside its model's window: old file bodies and long results shrink
                # (the files are on disk), the task and the latest steps stay verbatim.
                from .orchestrator import estimate_tokens, shrink_messages
                info = await router.context_info(model)
                if estimate_tokens(messages) > info["max"] * 0.6:
                    shrink_messages(messages, keep_last=4)
                if note := shared.inbox(m["title"]):  # teammates' messages ride along with the tool results
                    note = "[Messages from your team]\n" + note
                    if messages[-1]["role"] == "tool":
                        messages[-1] = {**messages[-1], "content": messages[-1]["content"] + "\n\n" + note}
                    else:
                        messages.append({"role": "user", "content": note})
                text, calls, blocks, think = "", [], None, ""
                try:
                    stream = [e async for e in router.stream_chat(
                        model, messages, {"tools": tool_schemas(MEMBER_TOOLS, True) + TEAM_TOOLS} if native else {}, ctx.cancel)]
                except ProviderError as e:
                    # A busy or briefly failing provider: wait and retry the same model (its conversation is kept)
                    # before switching; quota/auth errors switch at once.
                    if e.code in ("timeout", "unavailable", "server", "bad_gateway", "overloaded", "rate_limit", "network") and retries < 3:
                        retries += 1
                        wait = min(60, (e.retry_at - time.time()) if e.retry_at else 5 * 2 ** retries)
                        card.update(note=f"{model}: {e.code}, retry {retries} in {int(max(1, wait))} s")
                        push()
                        await asyncio.sleep(max(1, wait))
                        continue
                    raise
                retries = 0
                for evt in stream:
                    if evt["type"] == "text":
                        text += evt["text"]
                    elif evt["type"] == "thinking":
                        think += evt["text"]
                    elif evt["type"] == "tool_call":
                        calls.append(evt)
                    elif evt["type"] == "thinking_blocks":
                        blocks = evt["blocks"]
                    elif evt["type"] == "usage" and (evt.get("input") or evt.get("output")):
                        # Each member's own context and token use, from the provider's real counts (its model's
                        # quota and rate limits are recorded by the router under the same model).
                        card["context"] = (evt.get("input") or 0) + (evt.get("output") or 0)
                        card["tokens"] = card.get("tokens", 0) + card["context"]
                text, tag_calls = _visible_and_calls(text, think)
                if not calls and tag_calls:  # written as text or inside the reasoning (GLM): still a real call
                    calls = tag_calls
                if not calls:
                    # No written report (some models just stop): say what the member really produced.
                    made = ", ".join(card.get("files", []))
                    card.update(state="done", report=text.strip()[:1500] or (f"Finished; files: {made}" if made else "(no report)"),
                                finished=time.time())
                    for t in shared.tasks:  # the member's tasks are finished with it (also added / claimed ones)
                        if t["owner"] == m["title"] and t["status"] != "done":
                            t["status"] = "done"
                    push()
                    return
                if native:
                    messages.append({"role": "assistant", "content": text, **({"thinking_blocks": blocks} if blocks else {}),
                                     "tool_calls": [{"id": c["id"], "name": c["name"], "arguments": c["arguments"], **({"extra": c["extra"]} if c.get("extra") else {})} for c in calls]})
                else:
                    messages.append({"role": "assistant", "content": text or "(tool calls)"})
                tag_results: list[str] = []
                # Lookups of one turn run together (as in the main task); changes run in order.
                from .orchestrator import PARALLEL_SAFE
                from ..config import load_settings
                par = (load_settings().get("agent") or {}).get("parallel_tools", True)
                pre: dict[int, ToolResult] = {}
                if par and sum(c["name"] in PARALLEL_SAFE for c in calls) > 1:
                    idx = [k for k, c in enumerate(calls) if c["name"] in PARALLEL_SAFE]
                    got = await asyncio.gather(*(_run_tool(sub, calls[k]["name"], calls[k]["arguments"]) for k in idx))
                    pre = dict(zip(idx, got))
                for k, c in enumerate(calls):
                    if c["name"] in ("team_message", "team_tasks"):
                        res = shared.handle(m["title"], titles, c["name"], c["arguments"])
                    else:
                        res = pre.get(k) or await _run_tool(sub, c["name"], c["arguments"])
                    card["steps"] += 1
                    card["last"] = f"{c['name']} {c['arguments'].get('path') or ''}".strip()
                    a = c["arguments"] if isinstance(c.get("arguments"), dict) else {}
                    what = a.get("path") or a.get("url") or a.get("query") or a.get("command") or ""
                    log.append(f"{c['name']} {str(what)[:100]} -> {'ok' if res.ok else 'FAILED: ' + res.output[:120]}".strip())
                    if res.ok and res.data.get("path") and c["name"] in ("write_file", "edit_file", "make_doc"):
                        card["files"] = sorted(set(card.get("files", [])) | {res.data["path"]})
                    push()
                    if native:
                        messages.append({"role": "tool", "tool_call_id": c["id"], "name": c["name"],
                                         "content": clip(res.output, 4000)})
                    else:
                        tag_results.append(f'<result tool="{c["name"]}" ok="{str(res.ok).lower()}">\n{clip(res.output, 4000)}\n</result>')
                if tag_results:
                    messages.append({"role": "user", "content": "Tool results:\n" + "\n".join(tag_results)})
            card.update(state="done", report=(text.strip() or "Stopped after the step limit.")[:1500], finished=time.time())
            push()
            return
        except ProviderError as e:
            if len(tried) >= 3:
                card.update(state="error", report=f"{model}: {str(e)[:300]}")
                push()
                return
            card.update(note=f"{model} failed ({e.code}); switching")
            push()


def _visible_and_calls(text: str, think: str) -> tuple[str, list[dict]]:
    """A member's reply without reasoning tags or raw tool syntax (the report is shown to the user), plus tool calls
    written as text or inside the reasoning (models that do not send them natively)."""
    from .stream_parser import StreamSplitter, parse_tool
    out, blocks = [], []
    for source in (text, think):
        sp = StreamSplitter(frozenset(MEMBER_TOOLS))
        for kind, part in sp.feed(source) + sp.flush():
            if kind == "retract":
                out.clear()
            elif kind == "visible" and source is text:
                out.append(part)
            elif kind in ("tool", "tool_incomplete"):
                blocks.append(part)
        if blocks:
            break
    calls = []
    for b in blocks:
        if (c := parse_tool(b, frozenset(MEMBER_TOOLS))) and c.name:
            args = c.arguments if c.arguments is not None else {**c.args, **({"content": c.body} if c.body else {})}
            calls.append({"id": f"t{len(calls)}", "name": c.name, "arguments": args})
    return "".join(out), calls


async def _run_tool(ctx: ToolContext, name: str, arguments: dict) -> ToolResult:
    if name not in MEMBER_TOOLS or name not in TOOLS:
        return ToolResult(False, f"Tool {name} is not available to team members.")
    try:
        from .tooling import path_alias
        args, body = split_args(name, path_alias(name, arguments))
        res = await TOOLS[name].fn(ctx, args, body)
    except PermissionError as e:
        res = ToolResult(False, f"DENIED: {e}")
    except KeyError as e:
        res = ToolResult(False, f"Missing required argument: {e}")
    except Exception as e:
        res = ToolResult(False, f"{type(e).__name__}: {e}")
    res.output = redact(res.output)  # stored API keys never reach a member's model
    return res


def _stage(m: dict) -> int:
    try:
        return max(1, min(6, int(m.get("stage") or 1)))
    except (TypeError, ValueError):
        return 1


# A part whose task builds on another part's result ("analyze the HTML from team 1", "write the analysis into Word").
DEPENDS = re.compile(r"önceki|\b[1-6]\. ?(takım|grup|ekip|üye|aşama)|ilk (takım|grup|ekip)|(takım|grup|ekip)(ın|in|un|ün)? "
                     r"(çıktı|sonuc|sonuç|analiz|kod|dosya)|(gelen|ürettiği|yazdığı|oluşturduğu|hazırladığı|üretilen|"
                     r"yazılan|oluşturulan|hazırlanan) |\bprevious\b|\b(team|group|part|stage) ?[1-6]\b|"
                     r"\b(first|other) (team|group|part)\b|\boutput of\b|\bproduced by\b|\bwritten by\b|\bfrom the (first|previous)\b",
                     re.I)


def infer_stages(members: list[dict]) -> bool:
    """No stages given, but a later part clearly builds on an earlier one (it names it, or says "from team 1", "the
    analysis written by..."): run the parts one after another instead of all at once. Returns True when it did."""
    if len(members) < 2 or any("stage" in m for m in members):
        return False
    titles = [str(m.get("title") or "").strip().lower() for m in members]
    for i, m in enumerate(members[1:], 1):
        task = str(m.get("task", "")).lower()
        if DEPENDS.search(task) or any(t and len(t) > 3 and t in task for t in titles[:i]):
            for k, x in enumerate(members):
                x["stage"] = k + 1
            return True
    return False


def _handover(board: list[dict], stage: int) -> str:
    """What a later stage gets from the earlier ones: each finished member's model, files and report."""
    done = [c for c in board if c["stage"] < stage]
    if not done:
        return ""
    return "\n\nResults of the earlier stages (build on them; read their files when you need the details):\n" + "\n".join(
        f"- {c['title']} ({c['model'] or 'no model'}, {c['state']})"
        + (f", files: {', '.join(c.get('files', []))}" if c.get("files") else "") + f": {c['report'][:1500]}" for c in done)


async def run_team(ctx: ToolContext, members: list[dict]) -> ToolResult:
    members = [m for m in members if isinstance(m, dict) and str(m.get("task", "")).strip()][:MAX_MEMBERS]
    if not members:  # one part is fine too: it runs on a pool model
        return ToolResult(False, 'Give 1-6 parts as {"members": [{"title": ..., "task": ..., "stage": 1}, ...]}.')
    if not router.pool():
        return ToolResult(False, "No multi-model pool is set up; do the work yourself.")
    inferred = infer_stages(members)
    # Stages are renumbered 1..n in order, so a lone "stage": 2 is simply the first stage.
    order = {s: i + 1 for i, s in enumerate(sorted({_stage(m) for m in members}))}
    board = [{"title": str(m.get("title") or f"#{i + 1}")[:60], "task": str(m["task"])[:400], "model": "", "state": "queued",
              "steps": 0, "last": "", "report": "", "stage": order[_stage(m)]} for i, m in enumerate(members)]
    for m, card in zip(members, board, strict=True):
        m["title"] = card["title"]
    # A task that resumes an interrupted one (power cut, crash, a provider that kept failing, the stop button): the
    # parts that had finished are taken over as they are - model, files and report - and are not run again; a part
    # that was cut off continues from the files it had written.
    prior = {str(c.get("title")): c for c in (ctx.team_prior or []) if isinstance(c, dict)}
    for card in board:
        old = prior.get(card["title"])
        if not old:
            continue
        if old.get("state") == "done":
            card.update(state="done", model=old.get("model") or "", report=old.get("report") or "(finished earlier)",
                        files=list(old.get("files") or []), steps=old.get("steps", 0), resumed=True)
        elif old.get("files"):
            card["files"] = list(old["files"])
    title = " · ".join(c["title"] for c in board)[:160]
    shared = Shared(board)

    def push():  # updates the team tool's own trace step (one row, titled with the members)
        if ctx.live and ctx.step_id:
            ctx.live("team", title, "running", {"tool": "team", "members": board, "messages": shared.messages[-40:],
                                                 "tasks": shared.tasks}, ctx.step_id)

    # Models are reserved per stage (members of one stage run at the same time; a later stage can reuse them):
    # different models first, and spread over different providers, so parallel members do not queue on one
    # provider's per-minute limit. A model is shared only when the pool is smaller than the stage.
    taken: dict[int, set[str]] = {}
    for m, card in zip(members, board, strict=True):
        if card["state"] == "done":
            continue  # finished in the interrupted task: no model needed
        mine = taken.setdefault(card["stage"], set())
        mid, _ = await router.pick(m.get("need") or "code", len(m["task"]) // 3 + 4000, exclude=set(mine),
                                   avoid={x.partition(":")[0] for x in mine})
        if mid:
            card["reserved"] = mid
            mine.add(mid)
    push()
    t0 = time.time()
    for stage in sorted({c["stage"] for c in board}):  # a stage starts when the earlier ones are finished
        if ctx.cancel.is_set():
            break
        handover = _handover(board, stage)
        await asyncio.gather(*(_member(ctx, {**m, "task": str(m["task"]) + handover}, board, i, push, shared)
                               for i, m in enumerate(members) if board[i]["stage"] == stage and board[i]["state"] != "done"))
    done_members = {c["title"] for c in board if c["state"] == "done"}
    for t in shared.tasks:  # a task whose owner finished (or that nobody took, with the whole team done) is closed
        if t["status"] != "done" and (t["owner"] in done_members or (not t["owner"] and len(done_members) == len(board))):
            t["status"] = "done"
    push()
    from .orchestrator import ui_text
    lang = ctx.lang
    lines = [ui_text(lang, "ai_team_finished", "Team finished in {s} s:", s=f"{time.time() - t0:.0f}")]
    if inferred:
        lines.append("(The parts depend on each other, so they ran one after another, each with the earlier results.)")
    for c in board:
        lines.append(f"\n## {c['title']} [{c['state']}] (stage {c['stage']}, model {c['model'] or 'none'}, {c['steps']} steps)"
                     + (f"\n{ui_text(lang, 'ai_team_files', 'Files')}: {', '.join(c.get('files', []))}" if c.get("files") else "")
                     + f"\n{c['report']}")
    if shared.messages:
        lines.append(f"\n## {ui_text(lang, 'ai_team_messages', 'Team messages')} ({len(shared.messages)})\n" + "\n".join(
            f"- {x['from']} -> {x['to']}: {x['text'][:200]}" for x in shared.messages[-12:]))
    if len(shared.tasks) > len(board):
        lines.append(f"\n## {ui_text(lang, 'ai_team_tasks', 'Shared tasks')}\n" + shared.tasks_text())
    lines.append("\nIn your answer, say which model did each part, exactly as listed above (stage, model).")
    ok = any(c["state"] == "done" for c in board)
    return ToolResult(ok, clip("\n".join(lines), 8000), {"members": board, "messages": shared.messages[-40:], "tasks": shared.tasks})


def parse_members(raw) -> list[dict]:
    if isinstance(raw, list):
        return raw
    try:
        v = json.loads(raw or "[]")
        return v if isinstance(v, list) else []
    except (TypeError, json.JSONDecodeError):
        return []
