"""Selecting a local model whose weights do not fit in the free RAM never loads it (a 21.8 GB CPU model with 17.2 GB
free blue-screened the computer: Ollama reads a CPU model fully into memory). Run: python -m pytest tests/test_ram_guard_select.py"""
import asyncio

from app.llm import memguard, router


def test_short_model_is_never_loaded(monkeypatch):
    events, loads = [], []
    monkeypatch.setattr(router.bus, "publish", lambda topic, state, data: events.append((state, data.get("message"))))

    async def ctx(mid):
        return {"current": 16384, "ram": {"short": True, "weights_gb": 21.8, "free_gb": 13.2, "total_gb": 31.8,
                                          "parallel": 1}}
    monkeypatch.setattr(router, "context_info", ctx)
    monkeypatch.setattr(router, "load_settings", lambda: {"language": "en", "providers": {"ollama": {"local": True,
                                                                                                    "enabled": True}}})
    monkeypatch.setattr(router, "get_provider", lambda name: loads.append(name))
    asyncio.run(router.activate("ollama:big-model:latest"))
    assert not loads and events[-1][0] == "memory" and "21.8" in events[-1][1]


def test_reserve_setting_and_warn_mode(monkeypatch):
    gb = 1024 ** 3
    import psutil
    from types import SimpleNamespace
    monkeypatch.setattr(psutil, "virtual_memory", lambda: SimpleNamespace(total=int(31.8 * gb), available=int(24 * gb)))
    monkeypatch.setattr(memguard, "_sizes", lambda base: {"big": int(21.8 * gb)})
    monkeypatch.setattr(memguard, "free_memory", lambda: int(24.3 * gb))
    monkeypatch.setattr(memguard, "_env", lambda: (1, 2.0))
    # automatic reserve (3.2 GB): 24.3 - 3.2 = 21.1 GB < 21.8 x 1.05: does not fit (the case from the logs)
    monkeypatch.setattr(memguard, "guard_settings", lambda: {})
    assert memguard.reserve(int(31.8 * gb)) == memguard.auto_reserve(int(31.8 * gb))
    assert memguard.safe_window("u", "big", 128 * 1024)["short"] and memguard.load_check() == "block"
    # the user lowers the reserve to 1 GB in Settings: now it fits
    monkeypatch.setattr(memguard, "guard_settings", lambda: {"reserve_gb": 1, "load_check": "warn"})
    r = memguard.safe_window("u", "big", 128 * 1024)
    assert not r["short"] and r["reserve_gb"] == 1.0 and memguard.load_check() == "warn"
    # a nonsense value is kept inside sane bounds (never 0, never more than half the RAM)
    monkeypatch.setattr(memguard, "guard_settings", lambda: {"reserve_gb": 0.1})
    assert memguard.reserve(int(31.8 * gb)) == int(0.5 * gb)


def test_warn_mode_loads_the_short_model(monkeypatch):
    events, loads = [], []
    monkeypatch.setattr(router.bus, "publish", lambda topic, state, data: events.append((state, data.get("message"))))

    async def ctx(mid):
        return {"current": 4096, "ram": {"short": True, "weights_gb": 21.8, "free_gb": 21.1, "total_gb": 31.8,
                                          "parallel": 1}}
    monkeypatch.setattr(router, "context_info", ctx)
    monkeypatch.setattr(memguard, "guard_settings", lambda: {"load_check": "warn"})
    monkeypatch.setattr(router, "load_settings", lambda: {"language": "en", "providers": {"ollama": {"local": True,
                                                                                                    "enabled": True}}})

    def provider(name):
        loads.append(name)
        raise RuntimeError("stop here: the test only checks that loading goes on")
    monkeypatch.setattr(router, "get_provider", provider)
    try:
        asyncio.run(router.activate("ollama:big-model:latest"))
    except RuntimeError:
        pass
    assert events[1][0] == "memory" and "warn only" in events[1][1] and loads  # warned, then went on to load


def test_machine_info_has_the_numbers():
    m = memguard.machine()
    assert m["ram_total_gb"] > 0 and m["reserve_gb"] > 0 and m["threads"] >= 2


def test_guard_works_without_kv_info(monkeypatch):
    gb = 1024 ** 3
    monkeypatch.setattr(memguard, "_sizes", lambda base: {"big": int(21.8 * gb)})
    monkeypatch.setattr(memguard, "free_memory", lambda: int(17.2 * gb))
    r = memguard.safe_window("http://127.0.0.1:11434", "big", None)
    assert r and r["short"]
