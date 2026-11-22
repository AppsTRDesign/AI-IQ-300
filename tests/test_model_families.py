"""Model families: the same model behaves the same on every provider (tool calling, reasoning switch, sampling), and
the text-protocol parser reads the tool formats each family writes. Run: python -m pytest tests/test_model_families.py"""
from app.agents.stream_parser import LEAK, StreamSplitter, parse_tool
from app.llm import families


def test_family_lookup_ignores_provider_and_vendor_path():
    assert families.family("evren:deepseek-ai/DeepSeek-V3.2")[0] == "deepseek-v3"
    assert families.family("ollama:qwen3:8b")[0] == "qwen3"
    assert families.family("nvidia:qwen/qwen3-coder-480b-a35b-instruct")[0] == "qwen-coder"
    assert families.family("openrouter:moonshotai/kimi-k2-thinking")[0] == "kimi-thinking"
    assert families.family("ollama:gemma3:12b")[0] == "gemma"
    assert families.family("groq:openai/gpt-oss-120b")[0] == "gpt-oss"
    assert families.family("deepseek:deepseek-r1")[0] == "deepseek-r1"
    assert families.family("something-new")[0] == ""


def test_family_rules():
    assert families.native_ok("gemma3:12b") is False and families.native_ok("deepseek-r1:14b") is False
    assert families.native_ok("qwen3:8b") is True and families.native_ok("unknown-x") is None
    assert families.think_key("deepseek-ai/DeepSeek-V3.2") == "thinking"
    assert families.think_key("Qwen/Qwen3-235B-A22B") == "enable_thinking"
    assert families.always_thinks("gpt-oss:20b") and not families.always_thinks("qwen3:8b")
    assert families.sampling("kimi-k2-instruct") == {"temperature": 0.6}


def test_text_formats_of_each_family():
    names = {"write_file", "web_search"}
    kimi = parse_tool('<|tool_call_begin|>functions.web_search:0<|tool_call_argument_begin|>{"query": "hava"}'
                      '<|tool_call_end|>', names)
    assert kimi and kimi.name == "web_search" and kimi.arguments == {"query": "hava"}
    mm = parse_tool('<invoke name="write_file"><parameter name="path">a.txt</parameter>'
                    '<parameter name="content">hi</parameter></invoke>', names)
    assert mm and mm.name == "write_file" and mm.arguments == {"path": "a.txt", "content": "hi"}
    sp = StreamSplitter(names)
    out = sp.feed('Bakıyorum <minimax:tool_call><invoke name="web_search"><parameter name="query">x</parameter>'
                  '</invoke></minimax:tool_call> tamam') + sp.flush()
    kinds = [k for k, _ in out]
    assert "tool" in kinds and not any(LEAK.search(t) for k, t in out if k == "text")
