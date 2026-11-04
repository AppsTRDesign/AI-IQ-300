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

from ..llm import router
from ..llm.providers import ProviderError
from ..tools.registry import TOOLS, ToolContext, ToolResult, clip, split_args, tool_schemas

MEMBER_TOOLS = {"read_file", "list_dir", "search_code", "symbols", "impact", "write_file", "edit_file", "run",
                "web_search", "fetch_url", "research", "web_screenshot", "make_doc", "places", "read_document"}
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
    sub = dataclasses.replace(ctx, step=lambda kind, data: None, files_changed=ctx.files_changed, commands=ctx.commands)
    while True:
        if card.get("reserved") and not tried:
            model, why = card.pop("reserved"), ""
        else:
            model, why = await router.pick(m.get("need") or "code", len(m["task"]) // 3 + 6000,
                                           exclude=tried | {c["model"] for c in board if c["state"] == "running"}, tools=True)
        if not model:  # every model busy in this team: share one rather than fail
            model, why = await router.pick(m.get("need") or "code", 6000, exclude=tried, tools=True)
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
        messages = [{"role": "system", "content": system},
                    {"role": "user", "content": m["task"]}]
        try:
            for _ in range(MAX_TURNS):
                if ctx.cancel.is_set():
                    raise asyncio.CancelledError
                if note := shared.inbox(m["title"]):  # teammates' messages ride along with the tool results
                    note = "[Messages from your team]\n" + note
                    if messages[-1]["role"] == "tool":
                        messages[-1] = {**messages[-1], "content": messages[-1]["content"] + "\n\n" + note}
                    else:
                        messages.append({"role": "user", "content": note})
                text, calls, blocks = "", [], None
                async for evt in router.stream_chat(model, messages, {"tools": tool_schemas(MEMBER_TOOLS) + TEAM_TOOLS}, ctx.cancel):
                    if evt["type"] == "text":
                        text += evt["text"]
                    elif evt["type"] == "tool_call":
                        calls.append(evt)
                    elif evt["type"] == "thinking_blocks":
                        blocks = evt["blocks"]
                if not calls:
                    # No written report (some models just stop): say what the member really produced.
                    made = ", ".join(card.get("files", []))
                    card.update(state="done", report=text.strip()[:1500] or (f"Finished; files: {made}" if made else "(no report)"),
                                finished=time.time())
                    for t in shared.tasks:  # the member's own task is finished with it
                        if t["owner"] == m["title"] and t["text"] == m["title"] and t["status"] != "done":
                            t["status"] = "done"
                    push()
                    return
                messages.append({"role": "assistant", "content": text, **({"thinking_blocks": blocks} if blocks else {}),
                                 "tool_calls": [{"id": c["id"], "name": c["name"], "arguments": c["arguments"]} for c in calls]})
                for c in calls:
                    if c["name"] in ("team_message", "team_tasks"):
                        res = shared.handle(m["title"], titles, c["name"], c["arguments"])
                    else:
                        res = await _run_tool(sub, c["name"], c["arguments"])
                    card["steps"] += 1
                    card["last"] = f"{c['name']} {c['arguments'].get('path') or ''}".strip()
                    if res.ok and res.data.get("path") and c["name"] in ("write_file", "edit_file", "make_doc"):
                        card["files"] = sorted(set(card.get("files", [])) | {res.data["path"]})
                    push()
                    messages.append({"role": "tool", "tool_call_id": c["id"], "name": c["name"],
                                     "content": clip(res.output, 4000)})
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


async def _run_tool(ctx: ToolContext, name: str, arguments: dict) -> ToolResult:
    if name not in MEMBER_TOOLS or name not in TOOLS:
        return ToolResult(False, f"Tool {name} is not available to team members.")
    try:
        args, body = split_args(name, arguments)
        return await TOOLS[name].fn(ctx, args, body)
    except KeyError as e:
        return ToolResult(False, f"Missing required argument: {e}")
    except Exception as e:
        return ToolResult(False, f"{type(e).__name__}: {e}")


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
    for m, card in zip(members, board):
        m["title"] = card["title"]
    title = " · ".join(c["title"] for c in board)[:160]
    shared = Shared(board)

    def push():  # updates the team tool's own trace step (one row, titled with the members)
        if ctx.live and ctx.step_id:
            ctx.live("team", title, "running", {"tool": "team", "members": board, "messages": shared.messages[-40:],
                                                 "tasks": shared.tasks}, ctx.step_id)

    taken: set[str] = set()
    for m, card in zip(members, board):  # different models first; a model is shared only when the pool is smaller
        mid, _ = await router.pick(m.get("need") or "code", len(m["task"]) // 3 + 6000, exclude=set(taken), tools=True)
        if mid:
            card["reserved"] = mid
            taken.add(mid)
    push()
    t0 = time.time()
    for stage in sorted({c["stage"] for c in board}):  # a stage starts when the earlier ones are finished
        if ctx.cancel.is_set():
            break
        handover = _handover(board, stage)
        await asyncio.gather(*(_member(ctx, {**m, "task": str(m["task"]) + handover}, board, i, push, shared)
                               for i, m in enumerate(members) if board[i]["stage"] == stage))
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
