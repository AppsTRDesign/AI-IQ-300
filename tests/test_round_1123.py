"""Round 2026-11-23: own repo in the identity, near-duplicate search brake, path aliases, glued search results,
no image model for diagrams, drive types per volume, flowchart skill."""
from types import SimpleNamespace

from app.agents import prompts
from app.agents.tooling import near_duplicate_search, path_alias
from app.tools import media_tools, sysinfo
from app.tools.web import tidy_result


def test_identity_knows_repo_and_version():
    text = prompts.SYSTEM_CORE.format(model="m", os_name="Windows")
    assert "github.com/AppsTRDesign/AI-IQ-300" in text
    assert prompts.APP_VERSION and prompts.APP_VERSION != "?"
    assert f"v{prompts.APP_VERSION}" in text
    assert "```mermaid" in text  # diagrams go to Mermaid, not generate_image


def test_near_duplicate_searches_stop_on_third():
    run = SimpleNamespace(queries=[])
    assert near_duplicate_search(run, "AI IQ 300 GitHub") is None
    assert near_duplicate_search(run, "AI IQ 300 model GitHub") is None
    msg = near_duplicate_search(run, "GitHub AI IQ 300 model repository")
    assert msg and "gh search repos" in msg
    # a really different search still goes through
    assert near_duplicate_search(run, "istanbul weather tomorrow") is None


def test_path_alias_for_write_file():
    out = path_alias("write_file", {"file_path": "images/x.py", "content": "print(1)"})
    assert out["path"] == "images/x.py" and "file_path" not in out
    same = {"path": "a.txt", "filename": "b.txt"}
    assert path_alias("write_file", same) is same  # a real path wins
    assert path_alias("web_search", {"filename": "x"}) == {"filename": "x"}  # no path parameter: untouched


def test_glued_results_are_cut():
    r = tidy_result({"url": "https://youtube.com/x",
                     "title": "AI IQ 300 v0.18.5: AI That Writes Code, Tests Apps & Fixes ...assistant-ui · The frontend library",
                     "snippet": "First page text. See full list on github.com Other site text " + "x" * 600})
    assert r["title"].endswith("Fixes…") and "assistant-ui" not in r["title"]
    assert r["snippet"] == "First page text."
    long = tidy_result({"url": "u", "title": "T", "snippet": ("Sentence one is here. " * 40)})
    assert len(long["snippet"]) <= 430 and long["snippet"].endswith("…")


def test_generate_image_refuses_flowcharts():
    assert media_tools.DIAGRAM_PROMPT.search("flowchart AI IQ 300 architecture")
    assert media_tools.DIAGRAM_PROMPT.search("Sistem akış şeması")
    assert not media_tools.DIAGRAM_PROMPT.search("a red sports car at sunset, photo")


def test_volumes_get_their_disk_type():
    out = {"volumes": [{"mount": "C:\\"}, {"mount": "F:\\"}],
           "details": {"letters": [{"Letter": "C", "Disk": "KIOXIA", "MediaType": "SSD", "BusType": "NVMe"},
                                   {"Letter": "F", "Disk": "WDC", "MediaType": "HDD", "BusType": "SATA"}],
                       "cpu": [{"L2CacheSize": 7680, "L3CacheSize": 18432, "MaxClockSpeed": 2500}]}}
    sysinfo._label_volumes(out)
    assert out["volumes"][0]["disk"] == "KIOXIA (SSD, NVMe)"
    assert out["volumes"][1]["disk"] == "WDC (HDD, SATA)"
    cpu = out["details"]["cpu"][0]
    assert cpu["L2CacheSize"] == "7.5 MB" and cpu["L3CacheSize"] == "18 MB"
    assert cpu["BaseClock"].startswith("2.5 GHz") and "letters" not in out["details"]


def test_nemotron_template_tokens_are_hidden():
    from app.agents.stream_parser import StreamSplitter
    sp = StreamSplitter()
    out = []
    for ch in ["Önce raporu okuyorum.\n\n<|close|>think<|sep|>", "<|close|>message<|sep|><|close|>message<|sep|>"]:
        out += [t for k, t in sp.feed(ch) if k == "visible"]
    out += [t for k, t in sp.flush() if k == "visible"] if hasattr(sp, "flush") else []
    text = "".join(out)
    assert "<|" not in text and "message" not in text and "Önce raporu okuyorum." in text


def test_babble_check_leaves_planning_lists_alone():
    from app.agents.guards import _babble_cut
    plan = "Nodes:\n" + "\n".join(f"- {c}: Kullanıcı Mesajı" for c in "ABCDEFGHIJKLMNOPQRST") + "\n" + \
           "\n".join(f"{a} -> {b}" for a, b in zip("ABCDEFGHIJ", "BCDEFGHIJK"))
    assert _babble_cut(plan) is None
    babble = "Tamam.\n" + "\n".join(["BOOM.", "LFG.", "tulcall.", "Evet!", "DISPARAR.", "Go go."] * 3)
    assert _babble_cut(babble) is not None


def test_mcp_tool_called_by_its_own_name(monkeypatch):
    from app import mcp_client
    from app.agents.tooling import mcp_route
    monkeypatch.setattr(mcp_client, "servers_cfg", lambda: {"github": {}})
    name, args, body = mcp_route("github/search_repositories", {"query": "ai iq 300"}, "")
    assert name == "mcp" and args["server"] == "github" and args["tool"] == "search_repositories"
    assert '"ai iq 300"' in args["arguments"]
    assert mcp_route("notion/search", {}, "") is None  # not connected
    assert mcp_route("write_file", {}, "") is None


def test_sysinfo_parts_all_start_with_now(monkeypatch):
    import json
    monkeypatch.setattr(sysinfo, "_details", lambda: {"cpu": [{"Name": "Test CPU", "L2CacheSize": 1024}]})
    sysinfo._cache.clear()
    for part, key in (("summary", "system"), ("hardware", "hardware"), ("mobile", "mobile")):
        data = json.loads(sysinfo.report(part))
        assert "now" in data and data["now"]["date"] and key in data
    assert json.loads(sysinfo.report("summary"))["system"]["cpu"] == "Test CPU"
    sysinfo._cache.clear()


def test_new_system_tools_registered():
    from app.tools.registry import TOOLS
    from app.agents.checks import GROUP_TOOLS
    for t in ("hardware_info", "software_info", "mobile_info", "render_diagram"):
        assert t in TOOLS
    assert {"hardware_info", "software_info", "mobile_info"} <= GROUP_TOOLS["system"]
    assert "render_diagram" in GROUP_TOOLS["docs"]


def test_render_diagram_writes_png_and_svg(tmp_path):
    import asyncio
    from app.tools.diagram import mermaid_of, render
    md = 'Rapor\n```mermaid\nflowchart TD\n  A["Başla"] -->|Evet| B{"Bitti mi?"}\n```\n'
    code = mermaid_of(md)
    assert code.startswith("flowchart TD")
    w, h = asyncio.run(render(code, tmp_path / "d.png"))
    assert (tmp_path / "d.png").stat().st_size > 2000 and w > 50 and h > 50
    asyncio.run(render(code, tmp_path / "d.svg", dark=True))
    assert "<svg" in (tmp_path / "d.svg").read_text(encoding="utf-8")
    import pytest
    with pytest.raises(ValueError):
        asyncio.run(render("flowchart TD\n  A[\"x\" --> ", tmp_path / "bad.png"))


def test_flowchart_skill_exists():
    from pathlib import Path
    text = (Path(__file__).resolve().parents[1] / "skills" / "flowchart.md").read_text(encoding="utf-8")
    assert "name: flowchart" in text and "title_tr:" in text and "description_en:" in text
