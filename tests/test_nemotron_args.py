"""Nemotron 3.5 Super's typed argument blocks (seen live on NVIDIA, brackets lost on the way): parsed as calls, and
caught as a leak when no call can be built."""
from app.agents.stream_parser import LEAK, extract_inline_calls

STRIPPED = ('argument key="path" type="string".argumentargument key="command" type="string"git initargument<|call>|'
            'argument key="name" type="string"runargumentargument key="arguments" type="array"'
            '[{"key":"shell","type":"string","value":"powershell"},{"key":"command","type":"string","value":"git init"}]'
            'argumentcalltools')


def test_stripped_brackets_become_a_run_call():
    calls, rest = extract_inline_calls(STRIPPED, {"run"})
    assert [(c.name, c.arguments) for c in calls] == [("run", {"shell": "powershell", "command": "git init"})]
    assert rest == ""


def test_tagged_flat_arguments():
    text = ('Yazıyorum.\n<argument key="name" type="string">write_file</argument><argument key="path" type="string">'
            'a.md</argument><argument key="content" type="string"># Başlık</argument><|call|>')
    calls, rest = extract_inline_calls(text, {"write_file"})
    assert calls[0].name == "write_file" and calls[0].arguments == {"path": "a.md", "content": "# Başlık"}
    assert rest == "Yazıyorum."


def test_unknown_tool_is_left_and_flagged_as_leak():
    text = 'argument key="name" type="string"nosuchargument'
    calls, rest = extract_inline_calls(text, {"run"})
    assert not calls and rest == text
    assert LEAK.search(text)
