"""Round 2026-11-22h: a question about work already done ("test ettin?") was taken for a run request and the finished
answer was thrown away with "you only printed the code"."""
from app.agents.checks import asks_for, printed_code, WORK, CHANGE_REQUEST
from app.agents.tooling import RUN_ASK


def test_past_tense_is_not_a_request():
    for q in ("ai iq 300 de kullanamaz mısın sen? yani bu sistemde çalışıyor test ettin",
              "kodu çalıştırdın mı?", "dosya oluşturuldu mu", "bunu test edildi mi", "did you run it?",
              "have you tested the script?", "çalıştırmış mıydın"):
        assert not asks_for(RUN_ASK, q), q
    assert not asks_for(WORK, "yani bu sistemde çalışıyor test ettin")
    assert not asks_for(WORK, "onu yaptın mı?")


def test_requests_still_count():
    for q in ("bunu çalıştır", "kodu çalıştırır mısın", "test et", "scripti test eder misin", "run it", "please run main.py",
              "çalıştırın", "çalıştırabilir misin", "tested it, now run it again"):
        assert asks_for(RUN_ASK, q), q
    for q in ("bir site oluştur", "pdf hazırla", "yapar mısın", "create a file", "dosyayı kaydet"):
        assert asks_for(WORK, q), q
    assert asks_for(CHANGE_REQUEST, "dosyayı değiştir") or not CHANGE_REQUEST.search("dosyayı değiştir")


def test_printed_code_ignores_pasted_output():
    report = "Kurulum yaptım. Çıktı:\n```\nruflo v3.0 ok\n```\nTest:\n```text\nall green\n```"
    assert not printed_code(report)
    assert not printed_code("```bash\nruflo doctor: OK (3 checks)\n```")
    assert printed_code("```python\nprint('hi')\n```")
    assert printed_code("```bash\nnpm install -g ruflo\n```")
    assert printed_code("```\n$ python app.py\n```")
