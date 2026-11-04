"""Token counting with a real BPE tokenizer (o200k, bundled in app/tokenizer, works offline).

Providers report the exact count after each model turn (that number wins); this one counts everything in between:
the prompt before a turn, the live meter while the model writes, and what the next turn will carry. Until the
tokenizer has loaded (a fraction of a second at start) or if tiktoken is missing, ~3 characters per token is used."""
from __future__ import annotations

import os
import threading
from pathlib import Path

_DIR = Path(__file__).parent / "tokenizer"
_enc = None
_cache: dict[tuple[int, int], int] = {}  # (hash, length) -> tokens: history messages are counted once


def _load() -> None:
    global _enc
    old = os.environ.get("TIKTOKEN_CACHE_DIR")
    os.environ["TIKTOKEN_CACHE_DIR"] = str(_DIR)  # the bundled vocabulary: no download
    try:
        import tiktoken
        _enc = tiktoken.get_encoding("o200k_base")
    except Exception:  # noqa: BLE001 - missing package or file: keep the character estimate
        _enc = None
    finally:
        if old is None:
            os.environ.pop("TIKTOKEN_CACHE_DIR", None)
        else:
            os.environ["TIKTOKEN_CACHE_DIR"] = old


threading.Thread(target=_load, daemon=True, name="tokenizer").start()


def exact() -> bool:
    return _enc is not None


def count(text: str) -> int:
    if not text:
        return 0
    if _enc is None:
        return len(text) // 3 + 1
    key = (hash(text), len(text))
    if (n := _cache.get(key)) is None:
        n = len(_enc.encode(text, disallowed_special=()))
        if len(_cache) > 20_000:
            _cache.clear()
        _cache[key] = n
    return n
