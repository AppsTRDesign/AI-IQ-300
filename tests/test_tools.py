"""File tools answer with paths a model can use as they are; skills load by their trigger words.
Run: python -m pytest tests/test_tools.py"""
import asyncio
from pathlib import Path

from app.agents import catalog
from app.tools.registry import TOOLS, ToolContext


def _ctx(root: Path) -> ToolContext:
    return ToolContext("t", root, "full", asyncio.Event())


def _call(name, root, **args):
    return asyncio.run(TOOLS[name].fn(_ctx(root), args, ""))


def _project(tmp_path):
    (tmp_path / "app" / "app-main" / "public").mkdir(parents=True)
    (tmp_path / "app" / "app-main" / "config.php").write_text("<?php return [];", encoding="utf-8")
    (tmp_path / "app" / "app-main" / "public" / "index.php").write_text("<?php echo 1;", encoding="utf-8")
    return tmp_path


def test_list_dir_paths_start_at_the_working_folder(tmp_path):
    r = _call("list_dir", _project(tmp_path), path="app")
    assert r.ok and "app/app-main/config.php" in r.output


def test_missing_folder_is_an_error_with_the_real_place(tmp_path):
    r = _call("list_dir", _project(tmp_path), path="app-main")
    assert not r.ok and "app/app-main" in r.output


def test_missing_file_names_where_it_is(tmp_path):
    r = _call("read_file", _project(tmp_path), path="app/config.php")
    assert not r.ok and "app/app-main/config.php" in r.output


def test_reading_a_folder_says_so(tmp_path):
    r = _call("read_file", _project(tmp_path), path="app")
    assert not r.ok and "folder" in r.output


def test_reading_a_repository_file_by_file_is_turned_into_one_download(tmp_path, monkeypatch):
    from app.tools import registry, web

    async def fake_fetch(url, *a, **k):
        return {"ok": True, "url": url, "title": "x", "text": "content", "via": "http"}
    monkeypatch.setattr(web, "fetch", fake_fetch)

    async def no_gate(ctx, op):
        return None
    monkeypatch.setattr(registry, "_network_gate", no_gate)
    ctx = _ctx(tmp_path)
    urls = [f"https://api.github.com/repos/me/app/contents/{p}" for p in ("", "app", "routes", "config")]
    results = [asyncio.run(TOOLS["fetch_url"].fn(ctx, {"url": u}, "")) for u in urls]
    assert all(r.ok for r in results[:3])
    assert not results[3].ok and "archive/HEAD.zip" in results[3].output
    assert registry._github_repo("https://github.com/me/app/blob/main/x.php") == "me/app"
    assert registry._github_repo("https://github.com/me/app") == ""


def test_cd_accepts_task_folder_paths_and_the_folder_it_is_in(tmp_path):
    root = _project(tmp_path)
    ctx = _ctx(root)
    run = lambda cmd: asyncio.run(TOOLS["run"].fn(ctx, {"shell": "powershell"}, cmd))  # noqa: E731
    assert run("cd app/app-main").ok
    again = run("cd app/app-main")  # a path from the task folder while already inside it
    assert again.ok
    same = run("cd app-main")  # the folder we are in
    assert same.ok and "app/app-main" in same.output
    assert run("cd public").ok
    assert not run("cd nowhere").ok


def test_pip_always_installs_into_the_app_python():
    from app.tools.registry import PYTHON, venv_pip
    assert venv_pip("pip install python-pptx", "powershell").endswith(f'"{PYTHON}" -m pip install python-pptx')
    assert venv_pip("cd a && py -m pip install x", "cmd").count(PYTHON) == 1
    assert venv_pip("pipenv install", "powershell") == "pipenv install"
    assert venv_pip(".venv/Scripts/python -m pip install x", "bash") == ".venv/Scripts/python -m pip install x"


def test_server_ports_are_read_from_the_command():
    from app.tools.registry import _port_of
    assert _port_of("php -S localhost:8000") == 8000
    assert _port_of("php artisan serve --port=8001") == 8001
    assert _port_of("dotnet run --urls http://127.0.0.1:5000") == 5000
    assert _port_of("npm run dev -- -p 5173") == 5173
    assert _port_of("npm run dev") is None


def test_known_failures_get_their_real_alternatives():
    from app.agents.checks import error_playbook
    assert "fetch_url" in error_playbook("wget : The term 'wget' is not recognized as the name of a cmdlet")
    assert "list_dir" in error_playbook("Expand-Archive : The path 'main.zip' either does not exist")
    assert "another free port" in error_playbook("Error: listen EADDRINUSE: address already in use :::3000")
    assert error_playbook("everything worked") == ""


def test_document_placeholders_are_refused_but_real_text_and_links_pass():
    from app.tools.registry import placeholder_marks
    assert placeholder_marks("\\\\pdfiçeriği \\\\pdfbaşlığı")
    assert placeholder_marks("Bu sunum [Dükkan Adı] için. {{title}}")
    assert placeholder_marks("Kaynak: [Wikipedia](https://tr.wikipedia.org) ve $\\frac{a}{b}$, dipnot [1]") == []


def test_photo_file_names_keep_turkish_words_readable():
    from app.tools.stock import _slug
    assert _slug("iç mekan") == "ic-mekan" and _slug("Müşteriler") == "musteriler"


def test_numbered_requests_get_the_todo_hint():
    from app.agents.checks import tool_hint
    assert "todo" in tool_hint("Şunu yap: 1) dosya oluştur 2) çalıştır 3) sonucu yaz")
    assert tool_hint("merhaba") == ""


def test_slide_layout_has_pictures_and_positions(tmp_path):
    from pptx import Presentation
    from pptx.util import Inches
    from PIL import Image
    from app.tools.slides_view import slides
    img = tmp_path / "p.png"
    Image.new("RGB", (40, 30), "red").save(img)
    prs = Presentation()
    s = prs.slides.add_slide(prs.slide_layouts[1])
    s.shapes.title.text = "Başlık"
    s.placeholders[1].text = "Madde"
    s.shapes.add_picture(str(img), Inches(5), Inches(2), Inches(3))
    prs.save(tmp_path / "d.pptx")
    d = slides(tmp_path / "d.pptx")
    kinds = [x["kind"] for x in d["slides"][0]["shapes"]]
    assert "image" in kinds and kinds.count("text") >= 2
    assert d["slides"][0]["title"] == "Başlık"


def test_a_written_plan_becomes_the_todo_list():
    from app.agents.checks import plan_steps
    plan = "Plan:\n1. **Veritabanı:** tablo\n2. **API:** uç\n3) Arayüz\n   * alt madde\n4. **Takvim Modülü:** aylık"
    assert plan_steps(plan) == ["Veritabanı", "API", "Arayüz", "Takvim Modülü"]
    assert plan_steps("Tek satır, plan yok.") == []


def test_tag_attributes_in_single_quotes_are_read():
    from app.agents.stream_parser import attrs
    a = attrs("name=\"mcp\" server=\"deepwiki\" arguments='{\"repoName\": \"facebook/react\"}'")
    assert a["arguments"] == '{"repoName": "facebook/react"}' and a["server"] == "deepwiki"


def test_html_tags_are_not_placeholders():
    from app.tools.registry import placeholder_marks
    assert placeholder_marks("<html><head><title>Rapor</title></head><body><h1>X</h1></body></html>") == []


def test_localhost_requests_match_the_localhost_skill():
    for text in ("GitHub'dan bir PHP projesi bul, localhost'ta kur ve test et", "Laravel projemi kurup çalıştır",
                 "clone and run this repo", "start the dev server and test the app"):
        assert catalog.matching_skills(text)[:1] == ["localhost-project"], text
    assert catalog.matching_skills("merhaba, nasılsın?") == []
    assert catalog.matching_skills("bir kahve videosu yap") == ["video-studio"]


def test_browser_batch_takes_the_names_models_use():
    from app.tools.browser_tools import _batch_step
    assert _batch_step({"action": "js", "code": "1"}) == {"action": "inspect", "what": "js", "code": "1"}
    assert _batch_step({"action": "select", "ref": "e3", "value": "Orta"})["fields"] == [{"ref": "e3", "value": "Orta"}]
    assert _batch_step({"action": "fill", "ref": "e2", "value": "x"})["text"] == "x"
    assert _batch_step({"action": "hover", "text": "Menü"})["hover"] == "true"


def test_browser_steps_name_their_element_under_other_keys():
    from app.tools.browser_tools import _batch_step
    assert _batch_step({"action": "click", "element": "e4"})["ref"] == "e4"
    assert _batch_step({"action": "type", "target": "E-posta", "text": "a@b.c"})["label"] == "E-posta"
    assert _batch_step({"action": "click", "locator": "#save"})["selector"] == "#save"


def test_a_cd_line_with_more_commands_is_not_a_lone_cd():
    from app.tools.registry import CD_ONLY
    assert CD_ONLY.fullmatch("cd app\nnpm install") is None
    assert CD_ONLY.fullmatch("cd app\n").group(2) == "app"


def test_a_script_name_alone_runs_with_its_interpreter(tmp_path):
    import asyncio
    from app.tools.registry import TOOLS, ToolContext
    (tmp_path / "make.py").write_text("print('tables made')", encoding="utf-8")
    ctx = ToolContext("t", tmp_path, "full", asyncio.Event())
    res = asyncio.run(TOOLS["run"].fn(ctx, {}, "make.py"))
    assert res.ok and "tables made" in res.output


def test_reading_an_sqlite_file_names_its_tables(tmp_path):
    import asyncio
    import sqlite3
    from app.tools.registry import TOOLS, ToolContext
    con = sqlite3.connect(tmp_path / "k.db")
    con.execute("CREATE TABLE menu (id INTEGER)")
    con.execute("INSERT INTO menu VALUES (1)")
    con.commit()
    con.close()
    ctx = ToolContext("t", tmp_path, "full", asyncio.Event())
    res = asyncio.run(TOOLS["read_file"].fn(ctx, {"path": "k.db"}, ""))
    assert "SQLite database" in res.output and "menu: 1 rows" in res.output


def test_a_dead_localhost_address_opens_the_pages_own_file(tmp_path):
    import asyncio
    from app.tools.registry import ToolContext, local_page_instead
    (tmp_path / "services.html").write_text("<h1>x</h1>", encoding="utf-8")
    ctx = ToolContext("t", tmp_path, "full", asyncio.Event())
    url, note = local_page_instead(ctx, "http://localhost:59173/services.html")
    assert url.startswith("file:") and url.endswith("services.html") and "59173" in note
    assert local_page_instead(ctx, "https://example.com/") == ("https://example.com/", "")


def test_every_tool_runs_its_own_function():
    # a helper placed between a @tool(...) decorator and its function was registered as that tool (web_screenshot)
    from app.tools.registry import TOOLS
    assert [n for n, t in TOOLS.items() if t.fn.__name__ != n] == []


def test_the_apps_shortening_note_is_never_written_into_a_file(tmp_path):
    import asyncio
    from app.tools.registry import TOOLS, ToolContext
    ctx = ToolContext("t", tmp_path, "full", asyncio.Event())
    res = asyncio.run(TOOLS["write_file"].fn(ctx, {"path": "menu.php"},
                                            "[1202 characters omitted to save context; read_file shows the current file]"))
    assert not res.ok and "read_file menu.php" in res.output and not (tmp_path / "menu.php").exists()


def test_a_page_showing_an_error_keeps_the_task_open():
    from app.agents.orchestrator import page_state
    from app.tools.registry import ToolResult
    bad = ToolResult(True, "opened http://127.0.0.1:8000/menu.php\nFatal error: Uncaught Exception: Unable to open database")
    held = page_state("browser_navigate", bad, "")
    assert held.startswith("[page error]")
    assert page_state("browser_navigate", ToolResult(True, "opened http://127.0.0.1:8000/menu.php\n- heading Menu"), held) == ""
