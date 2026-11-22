"""Round 2026-11-22e: real-model GitHub/Google findings."""
from app.agents.checks import GOOGLE_ACT, OWN_DATA
from app.tools.agent_tools import mcp_repair


def test_enum_value_moved_to_its_key():
    schema = {"properties": {"query": {"type": "string"}, "sort": {"enum": ["stars", "updated"]},
                             "order": {"enum": ["asc", "desc"]}}, "required": ["query"]}
    out, fixed = mcp_repair(schema, {"query": "user:x", "order": "updated"})
    assert out == {"query": "user:x", "sort": "updated"}
    assert fixed


def test_enum_left_alone_when_valid_or_ambiguous():
    schema = {"properties": {"a": {"enum": ["x"]}, "b": {"enum": ["y"]}, "c": {"enum": ["y"]}}}
    assert mcp_repair(schema, {"a": "x"})[0] == {"a": "x"}
    assert mcp_repair(schema, {"a": "y"})[0] == {"a": "y"}  # two homes: not guessed


def test_google_act_words():
    for t in ("Kendime 'AI IQ 300 test' konulu kısa bir taslak e-posta hazırla, gönderme",
              "Gmail'de taslak oluştur", "takvime yarın 10'da toplantı ekle", "create a draft email to me"):
        assert GOOGLE_ACT.search(t), t
    for t in ("Python'da dosya nasıl okunur?", "takvim uygulaması yaz", "Google nedir?"):
        assert not GOOGLE_ACT.search(t), t
    assert OWN_DATA.search("GitHub depolarımı listele")
