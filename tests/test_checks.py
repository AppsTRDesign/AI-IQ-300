"""Fast unit checks of the parts that keep weak models honest (no server, no model). Run: python -m pytest tests"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.agents import orchestrator as o  # noqa: E402
from app.agents.stream_parser import extract_inline_calls  # noqa: E402

NAMES = {"write_file", "run", "read_file", "edit_file", "make_doc"}


def test_cli_call_in_fence_is_a_call():
    text = 'Adım 2:\n```powershell\nwrite_file path="a.py" content="print(\\"hi\\")\\nx = 1"\n```\nbitti'
    calls, cleaned = extract_inline_calls(text, NAMES)
    assert [c.name for c in calls] == ["write_file"]
    assert calls[0].arguments == {"path": "a.py", "content": 'print("hi")\nx = 1'}
    assert "write_file" not in cleaned and "```" not in cleaned


def test_function_style_call():
    calls, _ = extract_inline_calls("run(shell='python', command='a.py')", NAMES)
    assert calls and calls[0].arguments == {"shell": "python", "command": "a.py"}


def test_prose_mentions_are_not_calls():
    assert extract_inline_calls("Use write_file to save it, then run the app.", NAMES)[0] == []
    assert extract_inline_calls('print(path="x")', NAMES)[0] == []  # not a tool name


def test_missing_pdf_is_reported(tmp_path):
    t0 = time.time()
    req = "bilgisayarımın donanımını pdf rapor olarak yaz"
    miss = o.missing_deliverables(req, "Rapor hazır: `rapor.pdf` dosyasını açın.", tmp_path, t0)
    assert "*.pdf" in miss and "rapor.pdf" in miss
    (tmp_path / "rapor.pdf").write_bytes(b"%PDF-1.7\n%%EOF")
    assert o.missing_deliverables(req, "Rapor hazır: `rapor.pdf` dosyasını açın.", tmp_path, t0) == []


def test_questions_are_not_checked(tmp_path):
    assert o.missing_deliverables("pdf nasıl oluşturulur?", "rapor.pdf diye kaydedin", tmp_path, time.time()) == []


def test_tool_hint():
    h = o.tool_hint("bu bilgisayarımın donanım özelliklerini bul pdf rapor olarak yaz")
    assert "system_info" in h and "make_doc" in h
    assert o.tool_hint("merhaba") == ""


def test_request_parts_for_an_auto_to_do_list():
    from app.agents.checks import request_parts
    parts = request_parts("PHP ile bir kafe sitesi yap: ana sayfa (hero, menü, galeri), menü sayfası, rezervasyon "
                          "formu ve yönetim paneli. Mobil uyumlu olsun. localhost'ta başlat, tarayıcıda test et, rapor ver.")
    assert parts[0].startswith("PHP ile") and "Ana sayfa (hero, menü, galeri)" in parts and "Yönetim paneli" in parts
    assert parts[-1].startswith("Localhost")
    assert request_parts("merhaba, nasılsın") == []


def test_sqlite_in_a_shell_line_gets_the_script_route():
    from app.agents.checks import error_playbook
    hint = error_playbook('sqlite3 db.sqlite "CREATE TABLE t (id INT)" ParserError: Unexpected token')
    assert "create_db.py" in hint


def test_the_same_error_is_the_same_whatever_temp_script_ran_it():
    from app.agents.orchestrator import failure_signature
    a = ("exit_code=1 state=failed\n[stderr] At C:\\Users\\Onur GamePC\\AppData\\Local\\Temp\\x\\.session\\scripts\\"
         "3e82347a5422.ps1:1 char:35\nThe string is missing the terminator: \".")
    assert failure_signature(a) == failure_signature(a.replace("3e82347a5422", "9bb1c0d4e7f2").replace(":35", ":41"))
    assert failure_signature(a) != failure_signature("exit_code=1\nModuleNotFoundError: No module named 'x'")


def test_older_steps_are_shortened_and_the_latest_stay_whole():
    from app.agents.orchestrator import shrink_old_steps, OLD_STEP_MARK as SHRUNK
    big = "x" * 5000
    msgs = [{"role": "user", "content": "task"}]
    for i in range(6):
        msgs.append({"role": "assistant", "content": "", "tool_calls": [
            {"id": str(i), "name": "write_file", "arguments": {"path": f"f{i}.html", "content": big}}]})
        msgs.append({"role": "tool", "tool_call_id": str(i), "content": big})
    shrink_old_steps(msgs, 1)
    assert SHRUNK in msgs[2]["content"] and SHRUNK in msgs[1]["tool_calls"][0]["arguments"]["content"]
    assert msgs[-1]["content"] == big and msgs[-2]["tool_calls"][0]["arguments"]["content"] == big
    before = [dict(m) for m in msgs]
    shrink_old_steps(msgs, 1)  # stable: nothing changes the second time
    assert [m.get("content") for m in msgs] == [m.get("content") for m in before]


def test_source_files_the_request_names_must_exist(tmp_path):
    from app.agents import checks
    req = "Bir mobil uygulama oluştur. Ürünleri `data/mockProducts.ts` dosyasına, tipleri types/index.ts içine yaz."
    assert checks.missing_deliverables(req, "Bitti.", tmp_path, time.time()) == ["data/mockProducts.ts",
                                                                                   "types/index.ts"]
    (tmp_path / "app" / "data").mkdir(parents=True)  # in a project subfolder counts too
    (tmp_path / "app" / "data" / "mockProducts.ts").write_text("export {}", encoding="utf-8")
    (tmp_path / "types").mkdir()
    (tmp_path / "types" / "index.ts").write_text("export {}", encoding="utf-8")
    assert checks.missing_deliverables(req, "Bitti.", tmp_path, time.time()) == []
    assert checks.missing_deliverables("Node.js ile bir API yaz", "tamam", tmp_path, time.time()) == []


def test_files_listed_for_a_named_folder_go_in_it(tmp_path):
    """eval web_app, evren:auto: "todo/ klasöründe ... index.html, style.css ve app.js" written into the root twice."""
    from app.agents import checks
    req = "todo/ klasöründe küçük bir web uygulaması yap: index.html, style.css ve app.js. Bitince test et."
    for n in ("index.html", "style.css", "app.js"):
        (tmp_path / n).write_text("x", encoding="utf-8")
    assert checks.missing_deliverables(req, "Bitti.", tmp_path, time.time()) == ["todo/index.html", "todo/style.css",
                                                                                   "todo/app.js"]
    (tmp_path / "web" / "todo").mkdir(parents=True)
    for n in ("index.html", "style.css", "app.js"):
        (tmp_path / "web" / "todo" / n).write_text("x", encoding="utf-8")
    assert checks.missing_deliverables(req, "Bitti.", tmp_path, time.time()) == []
    en = "Build a to-do app in the todo/ folder: index.html and app.js."
    assert checks.in_named_folder(en) == ["todo/index.html", "todo/app.js"]
    assert checks.in_named_folder("src/ klasörüne a.py, lib/ klasörüne b.py yaz") == []  # two folders: not said which
    assert checks.in_named_folder("index.html dosyasını düzelt") == []


def test_argv_with_a_shell_command_runs_in_that_shell():
    from app.tools.registry import _shell_join
    assert (_shell_join("powershell", ["Move-Item", "-Path", "app/(tabs)/index.tsx", "-Destination", "a b.tsx"])
            == "Move-Item -Path 'app/(tabs)/index.tsx' -Destination 'a b.tsx'")
    assert _shell_join("bash", ["mv", "app/(tabs)/a.tsx", "b.tsx"]) == "mv 'app/(tabs)/a.tsx' b.tsx"
    assert _shell_join("cmd", ["move", "a (1).txt", "b.txt"]) == 'move "a (1).txt" b.txt'


def test_a_written_file_that_does_not_parse_is_reported(tmp_path):
    import asyncio
    from app.tools.registry import _syntax_note
    bad = tmp_path / "mock.ts"
    bad.write_text("export const P = [\n  { weight: '6'li Paket', price: 1 },\n];\n", encoding="utf-8")
    good = tmp_path / "ok.ts"
    good.write_text("export const P: { w: string }[] = [{ w: \"6'li Paket\" }];\n", encoding="utf-8")
    py = tmp_path / "x.py"
    py.write_text("def f(:\n    pass\n", encoding="utf-8")
    note = asyncio.run(_syntax_note(bad))
    if note:  # the TypeScript grammar may be unavailable offline; Python is always checked
        assert "line 2" in note
    assert asyncio.run(_syntax_note(good)) == ""
    assert "line 1" in asyncio.run(_syntax_note(py))


def test_todo_is_updated_without_retyping_the_list():
    from app.tools.registry import todo_patch
    cur = [{"content": "a", "status": "completed"}, {"content": "b", "status": "in_progress"},
           {"content": "c", "status": "pending"}]
    assert [t["status"] for t in todo_patch(cur, {"advance": True})] == ["completed", "completed", "in_progress"]
    out = todo_patch(cur, {"start": 3, "add": ["fix the bundler"]})
    assert [t["status"] for t in out] == ["completed", "pending", "in_progress", "pending"] and out[3]["content"] == "fix the bundler"
    assert todo_patch(cur, {"items": []}) is None and todo_patch([], {"advance": True}) is None


def test_todo_numbers_in_any_shape():
    from app.tools.registry import todo_patch
    cur = [{"content": str(i), "status": "pending"} for i in range(10)]
    for spec in ({"done": "4,5,6,7,8"}, {"done": "4-8"}, {"done": ["4", 5, "6-8"]}, {"done": "[4, 5, 6, 7, 8]"}):
        out = todo_patch(cur, {**spec, "start": "9"})
        assert [i for i, t in enumerate(out, 1) if t["status"] == "completed"] == [4, 5, 6, 7, 8], spec
        assert out[8]["status"] == "in_progress"


def test_babble_of_tiny_mixed_lines_is_cut():
    bab = "Plan: update ProductCard, then the home page.\n" + "\n".join(
        ["alright. lets go.", "tuplecall.", "LFG.", "BOOM.", "flame.", "flash.", "bang.", "tulcalls.", "fire.", "火.",
         "DISPARAR.", "Ready.", "Fire.", "GO.", "eigentlich... fired."])
    assert o._loop_cut(bab) == "Plan: update ProductCard, then the home page."
    listing = "Result:\n" + "\n".join(f"{i}. Item {i}" for i in range(20)) + "\nAll done and tested."
    assert o._loop_cut(listing) is None
