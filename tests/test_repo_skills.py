"""Skills repositories ('npx skills add owner/repo'): spec parsing and import, GitHub faked."""
import asyncio

import pytest

from app.agents import catalog


def test_repo_spec():
    s = catalog.repo_spec("npx -y skills add google/skills --skill gcloud,firebase")
    assert s == {"owner": "google", "repo": "skills", "ref": "", "sub": "", "only": ["gcloud", "firebase"]}
    assert catalog.repo_spec("owner/repo")["repo"] == "repo"
    t = catalog.repo_spec("https://github.com/google/skills/tree/main/skills/ads")
    assert (t["ref"], t["sub"]) == ("main", "skills/ads")
    for bad in ("Python nedir?", "https://github.com/x/y/blob/main/a.md", "npx -y @modelcontextprotocol/server-memory",
                "a/b/c"):
        assert catalog.repo_spec(bad) is None, bad


def test_skill_source_kinds():
    assert catalog.skill_source("hf skills add")["only"] == ["hf-cli"]
    assert catalog.skill_source("hf skills add huggingface-gradio --global")["only"] == ["huggingface-gradio"]
    assert catalog.skill_source("hf skills add --dest ~/x huggingface-papers")["only"] == ["huggingface-papers"]
    assert catalog.skill_source("gradio skills add --cursor") == {"kind": "gradio", "label": "Gradio", "space": ""}
    assert catalog.skill_source("gradio skills add abidlabs/en2fr --claude")["space"] == "abidlabs/en2fr"
    assert catalog.skill_source("npx skills add o/r")["kind"] == "github"
    assert catalog.skill_source("pip install x") is None
    with pytest.raises(Exception):
        catalog.skill_source("gradio skills add not-a-space")


def test_hf_and_gradio_import(skills_dir, monkeypatch):
    async def market():
        return [{"name": "hf-cli", "source": "skills/hf-cli", "description": "HF CLI"}]
    monkeypatch.setattr(catalog, "_hf_market_cache", None, raising=False)
    monkeypatch.setattr(catalog, "_hf_marketplace", market)
    monkeypatch.setattr(catalog, "_hf_files", lambda prefix: [prefix + "/SKILL.md", prefix + "/references/a.md"])
    lst = asyncio.run(catalog.repo_skills("hf skills add"))
    assert lst["skills"][0]["picked"] and lst["skills"][0]["name"] == "hf-cli"
    names = asyncio.run(catalog.import_repo_skills("hf skills add", ["hf-cli"]))
    assert names == ["hf-cli"]
    txt = (skills_dir / "hf-cli.md").read_text(encoding="utf-8")
    assert "source: hf:huggingface/skills/skills/hf-cli" in txt and "references/a.md: https://huggingface.co/buckets/" in txt
    monkeypatch.setattr(catalog, "space_skill_md", lambda s: "---\nname: abidlabs-en2fr\ndescription: d\n---\n" + "Call it. " * 20)
    assert asyncio.run(catalog.import_repo_skills("gradio skills add abidlabs/en2fr", ["space:abidlabs/en2fr"])) == ["abidlabs-en2fr"]


def test_yaml_block_description():
    meta = catalog._parse_text("---\nname: gcloud\nmetadata:\n  version: \"1\"\ndescription: >-\n  Line one\n  line two.\n"
                               "title: G\n---\nbody")
    assert meta["description"] == "Line one line two." and meta["title"] == "G" and meta["prompt"] == "body"


class FakeResp:
    def __init__(self, code, data=None, text=""):
        self.status_code, self._d, self.text = code, data, text

    def json(self):
        return self._d


class FakeClient:
    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url, params=None):
        if url.endswith("/repos/o/r"):
            return FakeResp(200, {"default_branch": "main"})
        if "/git/trees/" in url:
            return FakeResp(200, {"tree": [
                {"type": "blob", "path": "skills/a/gmail/SKILL.md", "size": 300},
                {"type": "blob", "path": "skills/a/gmail/references/x.md", "size": 10},
                {"type": "blob", "path": "skills/b/google/SKILL.md", "size": 300},
                {"type": "blob", "path": "README.md", "size": 5}]})
        if url.endswith("gmail/SKILL.md"):
            return FakeResp(200, text="---\nname: gmail\ndescription: Gmail tips\n---\n" + "Use the API well. " * 10)
        if url.endswith("hf-cli/SKILL.md"):
            return FakeResp(200, text="---\nname: hf-cli\ndescription: HF CLI\n---\n" + "Use hf. " * 20)
        if url.endswith("google/SKILL.md"):
            return FakeResp(200, text="---\nname: google\ndescription: Other google\n---\n" + "Steps here. " * 15)
        return FakeResp(404)


@pytest.fixture
def skills_dir(tmp_path, monkeypatch):
    monkeypatch.setitem(catalog.DIRS, "skills", tmp_path)
    monkeypatch.setattr(catalog, "SKILLS_DIR", tmp_path)
    monkeypatch.setattr(catalog.httpx, "AsyncClient", FakeClient)
    (tmp_path / "google.md").write_text("---\nname: google\ntitle: Google\ndescription: built-in\n---\nbody\n", encoding="utf-8")
    return tmp_path


def test_list_and_import(skills_dir):
    r = asyncio.run(catalog.repo_skills("npx skills add o/r"))
    assert [s["name"] for s in r["skills"]] == ["gmail", "google"]
    names = asyncio.run(catalog.import_repo_skills("o/r", ["skills/a/gmail/SKILL.md", "skills/b/google/SKILL.md"]))
    assert names == ["gmail", "o-google"]  # the built-in google skill is kept
    assert "built-in" in (skills_dir / "google.md").read_text(encoding="utf-8")
    g = (skills_dir / "gmail.md").read_text(encoding="utf-8")
    assert "source: o/r/skills/a/gmail/SKILL.md" in g and "title: Gmail" in g
    assert "references/x.md: https://raw.githubusercontent.com/o/r/main/skills/a/gmail/references/x.md" in g
    # importing again updates the same files, no copies
    assert asyncio.run(catalog.import_repo_skills("o/r", ["skills/a/gmail/SKILL.md"])) == ["gmail"]
    assert asyncio.run(catalog.repo_skills("o/r"))["skills"][0]["installed"] is True
