"""browser_key takes the key from where a weak model puts it (eval web_app, evren:auto: {"key": "F5", "keys": ""})."""
from app.tools import registry  # noqa: F401 - loads the tools in order
from app.tools.browser_tools import key_text


def test_key_aliases():
    assert key_text({"keys": "Enter"}) == "Enter"
    assert key_text({"key": "F5", "keys": ""}) == "F5"
    assert key_text({"ref": "F5", "keys": ""}) == "F5"
    assert key_text({"press": "Escape"}) == "Escape"


def test_element_refs_are_not_keys():
    assert key_text({"ref": "e12"}) == ""
    assert key_text({"ref": "ref_7"}) == ""
