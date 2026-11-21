"""v0.18.4 fixes: locale-broken time zone names, MCP argument unwrapping, MCP tool picks, todo status words,
the reply-language check on shared words."""
import json

from app.hostinfo import clean_text, tz_name
from app.agents.checks import wrong_language
from app.tools.agent_tools import STATUS_ALIASES


def test_surrogate_time_zone_repaired():
    # Windows gave "Türkiye Standart Saati" back with a lone surrogate after a library changed the locale:
    # every model request carrying it failed with "surrogates not allowed"
    fixed = clean_text("T\udcfcrkiye Standart Saati")
    assert fixed == "Türkiye Standart Saati"
    fixed.encode("utf-8")  # sendable
    assert clean_text("Pacific Standard Time") == "Pacific Standard Time"
    assert tz_name() and not any(0xD800 <= ord(c) <= 0xDFFF for c in tz_name())


def test_turkish_answer_with_shared_words_is_not_foreign():
    text = ("Bugünkü kurlar: Dolar ve Euro para birimi. Kaynaklar doviz.com, internet sitesi, foto ve test de en son "
            "veriler. Para piyasası açık, site güncel.")
    assert not wrong_language(text, "tr")
    fr = ("Voici le rapport des taux de change. Les données sont mises à jour chaque jour pour vous, avec les sources "
          "et les détails dans le document que nous avons préparé pour la banque.")
    assert wrong_language(fr, "tr")
    assert wrong_language("Bugünkü kurlar hazır, dolar 50 TL 左右 seviyesinde.", "tr")


def test_todo_status_words():
    assert STATUS_ALIASES["done"] == "completed"
    assert STATUS_ALIASES["in_progress".replace("_", "")] == "in_progress"


def test_mcp_picked_tools(monkeypatch):
    from app import mcp_client
    monkeypatch.setattr(mcp_client, "servers_cfg", lambda: {"deepwiki": {}})
    assert mcp_client.picked_tools("#time/get_current_time saat kaç") == [("time", "get_current_time")]
    assert mcp_client.picked_tools("time/get_current_time MCP aracını") == [("time", "get_current_time")]
    assert mcp_client.picked_tools("deepwiki/ask_question nedir") == [("deepwiki", "ask_question")]
    assert mcp_client.picked_tools("src/app.py dosyası") == []
    note = mcp_client.prompt_section("#time/get_current_time saat kaç")
    assert "NOT AVAILABLE" in note and "mcp_add" in note  # a ready server the model can connect itself


def test_mcp_arguments_unwrapped(monkeypatch):
    import asyncio
    asyncio.run(_unwrapped(monkeypatch))


async def _unwrapped(monkeypatch):
    from app import mcp_client
    from app.tools import agent_tools
    spec = {"name": "search", "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}
    monkeypatch.setattr(mcp_client, "find_tool", lambda s, t: spec)
    seen = {}

    async def fake_call(server, tool, arguments):
        seen.update(server=server, tool=tool, arguments=arguments)
        return True, "ok"
    monkeypatch.setattr(mcp_client, "call", fake_call)

    class Ctx:
        mode = "full"
    # nemotron wrapped the arguments ({"arguments": {...}}) three times; the server got {} and refused
    body = json.dumps({"arguments": {"query": "C# read file"}})
    res = await agent_tools.mcp(Ctx(), {"server": "ms", "tool": "search"}, body)
    assert seen.get("arguments") == {"query": "C# read file"}, (res, seen)
