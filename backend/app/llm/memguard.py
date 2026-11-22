"""RAM and VRAM guard for local models (Ollama).

A local model needs its weights plus a KV cache of num_ctx x parallel slots x bytes per token. On a CPU machine all
of it is system RAM: a 22 GB model with a large window and OLLAMA_NUM_PARALLEL=4 asked for more than the computer
had, Windows paged until it froze or crashed (blue screen). With a GPU the same memory sits (partly) in VRAM, and a
full VRAM spills into shared memory (slow) or fails.

Before a request, the window is capped to what fits in the free memory (with a reserve for the system), and a model
whose weights alone do not fit is not loaded at all.

While the app runs, a watchdog keeps the computer responsive WITHOUT closing the model in use and without losing
anything of a chat (messages, summary and task progress live in the app, not in the model):
  1. low memory: the app's own caches are released (speech model, file-text cache, token cache, an idle browser) and
     local models nothing uses are unloaded;
  2. still critical: the window of the model in use is made smaller (16K -> 8K). Its KV cache shrinks with it; the
     running task summarizes its own progress, continues in the smaller window and keeps its checkpoint;
  3. only when the user allowed it (Settings > Security > emergency unload) and nothing else is left, the model
     itself is unloaded; the task then stops with its checkpoint and "continue" resumes it.
"""
from __future__ import annotations

import sys
import time

import httpx

GB = 1024 ** 3
RESERVE = 3 * GB  # default; see reserve(): it follows the size of the machine


def auto_reserve(total: int) -> int:
    """Memory left to the system, the browser and this app: a tenth of the RAM, at least 1.5 GB and at most 4 GB
    (3 GB of an 8 GB laptop was more than a third of it; on a 64 GB workstation 3 GB was too little)."""
    return int(max(1.5 * GB, min(4 * GB, total * 0.10)))


def guard_settings() -> dict:
    try:
        from ..config import load_settings
        return load_settings().get("local_guard") or {}
    except Exception:  # noqa: BLE001
        return {}


def reserve(total: int) -> int:
    """The reserve in use: Settings > local model memory (reserve_gb, at least 0.5 GB), else the automatic one."""
    try:
        gb = float(guard_settings().get("reserve_gb") or 0)
    except (TypeError, ValueError):
        gb = 0
    return int(max(0.5, min(gb, total / GB / 2)) * GB) if gb > 0 else auto_reserve(total)


def load_check() -> str:
    """'block' (default): a model whose weights do not fit is not loaded; 'warn': loaded anyway, with a warning."""
    return "warn" if guard_settings().get("load_check") == "warn" else "block"


def machine() -> dict:
    """What the guard works with, for Settings: RAM, the Windows commit headroom (RAM + page file), dedicated VRAM,
    the reserve and the CPU threads a local model gets. Blocking (VRAM query): call it from a worker thread."""
    import psutil
    vm = psutil.virtual_memory()
    c = commit_free()
    v = vram()
    gb = lambda b: round(b / GB, 1) if b is not None else None  # noqa: E731
    try:
        swap = psutil.swap_memory().total
    except Exception:  # noqa: BLE001
        swap = None
    return {"ram_total_gb": gb(vm.total), "ram_free_gb": gb(vm.available), "commit_free_gb": gb(c),
            "usable_gb": gb(free_memory()), "page_file_gb": gb(swap),
            "vram_total_gb": gb(v["total"]) if v else None,
            "vram_free_gb": gb(v.get("free")) if v and v.get("free") is not None else None,
            "vram_source": v.get("source") if v else None,
            "reserve_gb": gb(reserve(vm.total)), "reserve_auto_gb": gb(auto_reserve(vm.total)),
            "threads": threads(), "cores": psutil.cpu_count(logical=False), "logical": psutil.cpu_count()}


def limits(total: int, low_pct: float = 12, critical_pct: float = 6) -> tuple[int, int]:
    """(low, critical) free-memory limits in bytes for a machine with `total` bytes. A share of the total, kept
    inside absolute bounds: 12% of 128 GB (15 GB free!) would trigger all the time, 6% of 8 GB (0.5 GB) too late."""
    low = max(1.0 * GB, min(total * low_pct / 100, 4 * GB))
    crit = max(0.6 * GB, min(total * critical_pct / 100, 2 * GB))
    return int(low), int(min(crit, low * 0.75))


def vram_limits(total: int) -> tuple[int, int]:
    """The same for dedicated GPU memory (a GPU is meant to be nearly full, so the limits are tighter)."""
    return int(max(256 * 1024 ** 2, min(total * 0.06, 1 * GB))), int(max(128 * 1024 ** 2, min(total * 0.03, 0.5 * GB)))
_SIZES: tuple[float, dict[str, int]] = (0.0, {})
KV_BYTES = {"q8_0": 1.0, "q4_0": 0.5}  # per element; f16 (Ollama's default) is 2
FLOOR = 8192  # the guard never makes a window smaller than this (the instructions and one reply must still fit)

# model name -> window the guard allows now (set under memory pressure, lifted when memory is comfortable again)
_CAPS: dict[str, int] = {}
# model name -> (window in use, time): the window stays the same between requests, so the server does not reload the
# model because free RAM moved by a few megabytes (every other num_ctx is a full reload: tens of seconds on a CPU)
_STEADY: dict[str, int] = {}
# model name -> time the guard asked the running task to give memory back (see pressure())
_PRESSURE: dict[str, float] = {}
_ACKED: dict[str, float] = {}


def kv_per_token(model_info: dict) -> int | None:
    """Bytes of KV cache one token takes at f16, from the GGUF metadata Ollama's /api/show returns."""
    def get(suffix: str):
        return next((v for k, v in model_info.items() if k.endswith(suffix)), None)
    layers, kv_heads = get(".block_count"), get(".attention.head_count_kv")
    k_len = get(".attention.key_length")
    v_len = get(".attention.value_length")
    if not (k_len and v_len):
        emb, heads = get(".embedding_length"), get(".attention.head_count")
        if emb and heads:
            k_len = v_len = emb // heads
    if isinstance(kv_heads, list):  # per-layer counts (some architectures)
        kv_heads = max(kv_heads) if kv_heads else None
    if not (layers and kv_heads and k_len and v_len):
        return None
    return int(layers * kv_heads * (k_len + v_len) * 2)


def _env() -> tuple[int, float]:
    """Parallel slots and bytes per KV element from the Ollama settings (Settings > Providers > Ollama)."""
    try:
        from .local_runtime import read_vars
        v = read_vars()
    except Exception:
        v = {}
    try:
        parallel = max(1, int(v.get("OLLAMA_NUM_PARALLEL") or 1))
    except ValueError:
        parallel = 1
    kv = KV_BYTES.get((v.get("OLLAMA_KV_CACHE_TYPE") or "").lower(), 2.0)
    # A quantized KV cache needs flash attention in Ollama; without it the cache stays f16.
    if kv < 2 and str(v.get("OLLAMA_FLASH_ATTENTION") or "") not in ("1", "true"):
        kv = 2.0
    return parallel, kv


def _sizes(base_url: str) -> dict[str, int]:
    """Model file sizes (/api/tags), the memory of loaded models (/api/ps) and their VRAM part, cached for 20 s."""
    global _SIZES
    if time.monotonic() - _SIZES[0] < 20:
        return _SIZES[1]
    out: dict[str, int] = {}
    try:
        for m in httpx.get(f"{base_url}/api/tags", timeout=3).json().get("models", []):
            out[m["name"]] = int(m.get("size") or 0)
        for m in httpx.get(f"{base_url}/api/ps", timeout=3).json().get("models", []):
            out["loaded:" + m["name"]] = int(m.get("size") or 0)
            out["vram:" + m["name"]] = int(m.get("size_vram") or 0)
    except (httpx.HTTPError, ValueError):
        pass
    _SIZES = (time.monotonic(), out)
    return out


def commit_free() -> int | None:
    """Windows: bytes that can still be committed (RAM + page file) before the system runs out of memory. A 32 GB
    machine with a 5 GB page file crashed while 'available RAM' still looked fine: a loaded model, the browser and the
    KV cache had used up the commit limit. None on other systems."""
    if sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes

    class PerfInfo(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("CommitTotal", ctypes.c_size_t), ("CommitLimit", ctypes.c_size_t),
                    ("CommitPeak", ctypes.c_size_t), ("PhysicalTotal", ctypes.c_size_t),
                    ("PhysicalAvailable", ctypes.c_size_t), ("SystemCache", ctypes.c_size_t),
                    ("KernelTotal", ctypes.c_size_t), ("KernelPaged", ctypes.c_size_t),
                    ("KernelNonpaged", ctypes.c_size_t), ("PageSize", ctypes.c_size_t),
                    ("HandleCount", wintypes.DWORD), ("ProcessCount", wintypes.DWORD), ("ThreadCount", wintypes.DWORD)]
    pi = PerfInfo()
    pi.cb = ctypes.sizeof(pi)
    try:
        if not ctypes.windll.psapi.GetPerformanceInfo(ctypes.byref(pi), pi.cb):
            return None
    except (AttributeError, OSError):
        return None
    return (pi.CommitLimit - pi.CommitTotal) * pi.PageSize


def free_memory() -> int:
    """What a new allocation can really use: free RAM, and on Windows no more than the commit headroom."""
    import psutil
    free = psutil.virtual_memory().available
    c = commit_free()
    return min(free, c) if c is not None else free


def threads() -> int:
    """CPU threads for a local model: physical cores minus one (at least 2). All cores at 100% for minutes made the
    machine hot and unresponsive (and can shut it down); one core stays for the system and the app."""
    import psutil
    return max(2, (psutil.cpu_count(logical=False) or 4) - 1)


def _forget_sizes() -> None:
    global _SIZES
    _SIZES = (0.0, {})


# ---------------------------------------------------------------- VRAM
_VRAM: tuple[float, dict | None] = (0.0, None)
_NO_WINDOW = 0x08000000


def _vram_nvidia() -> dict | None:
    import shutil
    import subprocess
    exe = shutil.which("nvidia-smi")
    if not exe:
        return None
    try:
        out = subprocess.run([exe, "--query-gpu=memory.total,memory.used", "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=4,
                             creationflags=_NO_WINDOW if sys.platform == "win32" else 0).stdout
        total = used = 0
        for line in out.strip().splitlines():
            t, u = (int(float(x)) for x in line.split(","))
            total, used = total + t, used + u
        return {"total": total * 1024 ** 2, "used": used * 1024 ** 2, "source": "nvidia-smi"} if total else None
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def _vram_sysfs() -> dict | None:
    """Linux (amdgpu and others that export it): /sys/class/drm/card*/device/mem_info_vram_*."""
    from pathlib import Path
    best = None
    for dev in Path("/sys/class/drm").glob("card[0-9]/device"):
        try:
            total = int((dev / "mem_info_vram_total").read_text())
            used = int((dev / "mem_info_vram_used").read_text())
        except (OSError, ValueError):
            continue
        if total and (best is None or total > best["total"]):
            best = {"total": total, "used": used, "source": "sysfs"}
    return best


def _vram_windows() -> dict | None:
    """Any GPU on Windows (AMD, Intel, NVIDIA without nvidia-smi): the dedicated memory size from the display class
    in the registry and the dedicated usage from the 'GPU Adapter Memory' performance counter (asked by its English
    name, so it works on every Windows language)."""
    import ctypes
    import winreg
    from ctypes import wintypes
    total = 0
    cls = r"SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}"
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, cls) as root:
            for i in range(32):
                try:
                    name = winreg.EnumKey(root, i)
                except OSError:
                    break
                try:
                    with winreg.OpenKey(root, name) as k:
                        v = winreg.QueryValueEx(k, "HardwareInformation.qwMemorySize")[0]
                        v = int.from_bytes(v, "little") if isinstance(v, bytes) else int(v)
                        total = max(total, v)
                except OSError:
                    continue
    except OSError:
        return None
    if total < 512 * 1024 ** 2:  # no dedicated GPU memory worth guarding (integrated graphics)
        return None
    used = None
    try:
        pdh = ctypes.windll.pdh
        pdh.PdhOpenQueryW.argtypes = [wintypes.LPCWSTR, ctypes.c_void_p, ctypes.POINTER(wintypes.HANDLE)]
        pdh.PdhAddEnglishCounterW.argtypes = [wintypes.HANDLE, wintypes.LPCWSTR, ctypes.c_void_p,
                                              ctypes.POINTER(wintypes.HANDLE)]
        pdh.PdhCollectQueryData.argtypes = [wintypes.HANDLE]
        pdh.PdhGetFormattedCounterArrayW.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
                                                     ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
        pdh.PdhCloseQuery.argtypes = [wintypes.HANDLE]

        class Value(ctypes.Structure):
            _fields_ = [("CStatus", wintypes.DWORD), ("large", ctypes.c_longlong)]

        class Item(ctypes.Structure):
            _fields_ = [("name", wintypes.LPWSTR), ("value", Value)]

        query, counter = wintypes.HANDLE(), wintypes.HANDLE()
        if pdh.PdhOpenQueryW(None, None, ctypes.byref(query)) == 0:
            try:
                if pdh.PdhAddEnglishCounterW(query, r"\GPU Adapter Memory(*)\Dedicated Usage", None,
                                             ctypes.byref(counter)) == 0 and pdh.PdhCollectQueryData(query) == 0:
                    size, count = wintypes.DWORD(0), wintypes.DWORD(0)
                    pdh.PdhGetFormattedCounterArrayW(counter, 0x400, ctypes.byref(size), ctypes.byref(count), None)
                    if size.value:
                        buf = ctypes.create_string_buffer(size.value)
                        if pdh.PdhGetFormattedCounterArrayW(counter, 0x400, ctypes.byref(size), ctypes.byref(count),
                                                            buf) == 0:
                            items = ctypes.cast(buf, ctypes.POINTER(Item))
                            used = max((items[i].value.large for i in range(count.value)), default=None)
            finally:
                pdh.PdhCloseQuery(query)
    except (AttributeError, OSError, ValueError):
        used = None
    return {"total": total, "used": used, "source": "windows"}


def vram() -> dict | None:
    """{"total", "used" (None when it cannot be read), "free", "source"} of the dedicated GPU memory, or None when the
    computer has none. Cached for 5 s (blocking: call it from a worker thread)."""
    global _VRAM
    if time.monotonic() - _VRAM[0] < 5:
        return _VRAM[1]
    info = None
    try:
        info = _vram_nvidia() or (_vram_windows() if sys.platform == "win32" else _vram_sysfs())
    except Exception:  # noqa: BLE001 - a broken driver query never stops a task
        info = None
    if info:
        info["free"] = max(0, info["total"] - info["used"]) if info.get("used") is not None else None
    _VRAM = (time.monotonic(), info)
    return info


# ---------------------------------------------------------------- windows the guard manages
def cap(model: str) -> int | None:
    """The window the guard allows for this model right now (None: no limit from the guard)."""
    return _CAPS.get(model)


def shrink(model: str, current: int) -> int | None:
    """Halves the model's window (never below FLOOR) and remembers it as the guard's cap. None when it cannot get
    smaller. The model reloads once at the new size; its smaller KV cache is the memory given back."""
    new = max(FLOOR, (int(current) // 2) // 1024 * 1024)
    if new >= current:
        return None
    _CAPS[model] = new
    _STEADY[model] = new
    _forget_sizes()
    return new


def forget_steady(model: str) -> None:
    """The task asked for another window size (growth): the next context_info takes the new one."""
    _STEADY.pop(model, None)


def steady(model: str, current: int, fits: int | None, binding: bool = True) -> int:
    """The window to use for this request: the one already in use while it still fits (within 10%), so small moves
    of free RAM never change num_ctx (and reload the model) between two requests. Only while the free memory is what
    limits the window (binding): a size the user chose is always taken as it is. It follows `current` when memory
    fell so far that the old one no longer fits, or rose enough for a clearly larger one."""
    last = _STEADY.get(model)
    if not binding:
        _STEADY[model] = current
        return current
    if last and fits is not None and last < current and last <= fits * 1.1 and current < last * 1.5:
        return last  # the cap moved a little above the window in use: keep it
    if last and fits is not None and current < last <= fits * 1.1 and current >= last * 0.9 and model not in _CAPS:
        return last  # ...or a little below it, and the old one still (almost) fits
    _STEADY[model] = current
    return current


def pressure(model: str) -> bool:
    """True while the guard wants the task running on this model to give memory back (stop the request, summarize,
    continue in a smaller window). Read by the task loop; answered with ack()."""
    return model in _PRESSURE


def ack(model: str) -> None:
    _PRESSURE.pop(model, None)
    _ACKED[model] = time.monotonic()


def status() -> dict:
    return {"caps": dict(_CAPS), "pressure": sorted(_PRESSURE)}


def release_app_memory() -> int:
    """The app's own reclaimable memory: caches that are rebuilt on demand. Returns the bytes the process gave back
    (0 when unknown). Nothing a chat needs is touched."""
    import gc
    try:
        import psutil
        proc = psutil.Process()
        before = proc.memory_info().rss
    except Exception:  # noqa: BLE001
        proc, before = None, 0
    try:  # the speech-to-text model (~150-500 MB) is loaded again when needed
        from ..tools import speech
        speech._MODELS.clear()
    except Exception:  # noqa: BLE001
        pass
    try:  # texts of working folders kept for the changes card (up to tens of MB per folder)
        from .. import changes
        changes._TEXTS.clear()
    except Exception:  # noqa: BLE001
        pass
    try:
        from .. import tokens
        tokens._cache.clear()
    except Exception:  # noqa: BLE001
        pass
    gc.collect()
    if sys.platform == "win32":
        try:  # pages the app does not use right now go back to the system (they return on first use)
            import ctypes
            ctypes.windll.kernel32.GetCurrentProcess.restype = ctypes.c_void_p
            ctypes.windll.psapi.EmptyWorkingSet.argtypes = [ctypes.c_void_p]
            ctypes.windll.psapi.EmptyWorkingSet(ctypes.windll.kernel32.GetCurrentProcess())
        except (AttributeError, OSError):
            pass
    try:
        return max(0, before - proc.memory_info().rss) if proc else 0
    except Exception:  # noqa: BLE001
        return 0


async def watchdog(state, busy, notify, relief=None, other_local=None) -> None:
    """Background guard (every 2 s). state() -> {"base_url", "active" (Ollama name of the chosen model), "enabled",
    "emergency_unload", "low", "critical"}; busy(name) -> a task is running on that model; notify(kind, **info)
    tells the user; relief() is the app's own extra cleanup (an idle browser)."""
    import asyncio
    try:
        import psutil
    except ImportError:
        return
    last_app_relief = 0.0
    comfortable_since = 0.0
    warned = 0.0
    while True:
        await asyncio.sleep(2)
        try:
            st = state()
            if not st.get("enabled", True):
                continue
            vm = psutil.virtual_memory()
            free_now = free_memory()
            share = free_now / vm.total
            low_b, crit_b = limits(vm.total, st.get("low", 12), st.get("critical", 6))
            base = st.get("base_url") or ""
            loaded: list[dict] = []
            v = None
            if base and (share <= 0.35 or _CAPS):
                try:
                    async with httpx.AsyncClient(timeout=5) as c:
                        loaded = (await c.get(f"{base}/api/ps")).json().get("models", [])
                except (httpx.HTTPError, ValueError):
                    loaded = []
            on_gpu = [m for m in loaded if (m.get("size_vram") or 0) > 0]
            if on_gpu or free_now <= low_b:
                v = await asyncio.to_thread(vram)
            # VRAM pressure counts only for models that really sit in VRAM (a model on the CPU is not helped by
            # freeing GPU memory); on machines with unified memory (Apple Silicon) the RAM limits cover both.
            vfree = v["free"] if v and on_gpu and v.get("free") is not None and v["total"] else None
            vshare = (vfree / v["total"]) if vfree is not None else None
            vlow, vcrit = vram_limits(v["total"]) if vfree is not None else (0, 0)
            tight = free_now <= low_b or (vfree is not None and vfree <= vlow)
            crit = free_now <= crit_b or (vfree is not None and vfree <= vcrit)
            now = time.monotonic()
            if not tight:
                # Memory is comfortable again for two minutes: the guard's caps are lifted (the next task gets the
                # full window back; a running one keeps its size until it ends).
                if share > 0.30 and (vshare is None or vshare > 0.15):
                    comfortable_since = comfortable_since or now
                    if _CAPS and now - comfortable_since > 120 and not any(busy(n) for n in _CAPS):
                        _CAPS.clear()
                else:
                    comfortable_since = 0.0
                continue
            comfortable_since = 0.0
            free_gb, total_gb = round(vm.available / 1024 ** 3, 1), round(vm.total / 1024 ** 3, 1)
            what = "vram" if (vfree is not None and vfree <= vlow and free_now > low_b) else "ram"
            # 1. the app's own memory first (at most twice a minute)
            if now - last_app_relief > 30:
                last_app_relief = now
                freed = await asyncio.to_thread(release_app_memory)
                if relief:
                    try:
                        await relief()
                    except Exception:  # noqa: BLE001
                        pass
                if freed > 64 * 1024 ** 2:
                    notify("app", free=free_gb, total=total_gb, freed=round(freed / 1024 ** 2), what=what)
            if crit and other_local:
                # Local servers that are not Ollama (LM Studio): the chosen model keeps running in a smaller window
                # (loaded again at that size) or, while a task streams on it, the task gives memory back itself.
                try:
                    await other_local(free=free_gb, total=total_gb, what=what, now=now)
                except Exception:  # noqa: BLE001
                    pass
            if not base or not loaded:
                continue
            active = st.get("active") or ""
            async with httpx.AsyncClient(timeout=30) as c:
                # 2. models nobody uses and that are not the chosen one
                dropped = False
                for m in loaded:
                    name = m["name"]
                    if busy(name) or name == active:
                        continue
                    await c.post(f"{base}/api/generate", json={"model": name, "keep_alive": 0})
                    _forget_sizes()
                    dropped = True
                    notify("idle", model=name, free=free_gb, total=total_gb, what=what)
                if dropped or not crit:
                    continue
                # 3. critical: the model in use keeps running in a smaller window
                for m in loaded:
                    name = m["name"]
                    ctx = int(m.get("context_length") or _STEADY.get(name) or 0)
                    if busy(name):
                        if name not in _PRESSURE and now - _ACKED.get(name, 0.0) > 60:
                            _PRESSURE[name] = now  # the task loop does the rest (see orchestrator)
                        continue
                    new = shrink(name, ctx) if ctx else None
                    if new:
                        body = {"model": name, "keep_alive": "10m", "options": {"num_ctx": new, "num_thread": threads()}}
                        await c.post(f"{base}/api/generate", json=body, timeout=600)
                        notify("shrunk", model=name, old=ctx, new=new, free=free_gb, total=total_gb, what=what)
                    elif st.get("emergency_unload"):
                        await c.post(f"{base}/api/generate", json={"model": name, "keep_alive": 0})
                        _forget_sizes()
                        notify("unloaded", model=name, free=free_gb, total=total_gb, what=what, busy=False)
                    elif now - warned > 120:
                        warned = now
                        notify("floor", model=name, free=free_gb, total=total_gb, what=what)
                # A task that did not react within 90 s (a tool running for minutes): the last resort, if allowed.
                for name, since in list(_PRESSURE.items()):
                    if now - since > 90 and st.get("emergency_unload") and busy(name):
                        await c.post(f"{base}/api/generate", json={"model": name, "keep_alive": 0})
                        _forget_sizes()
                        _PRESSURE.pop(name, None)
                        notify("unloaded", model=name, free=free_gb, total=total_gb, what=what, busy=True)
        except asyncio.CancelledError:
            raise
        except Exception:  # Ollama not running, a timeout...: try again next round
            continue


def safe_window(base_url: str, model: str, kv_tok: int | None) -> dict | None:
    """{"max": tokens that fit, "short": weights alone do not fit, ...} or None when it cannot be told."""
    try:
        import psutil
    except ImportError:
        return None
    sizes = _sizes(base_url)
    weights = sizes.get(model)
    if not weights:
        return None
    if not kv_tok:
        # The model does not say its KV size: a cautious estimate from its file size (a 20 GB model ~200 KB per
        # token in f16), so the guard still works - before, no estimate meant no guard at all
        kv_tok = max(128 * 1024, weights // 100_000)
    vm = psutil.virtual_memory()
    # Memory of loaded local models comes back when they are unloaded (the app unloads others before a switch).
    loaded = sum(v for k, v in sizes.items() if k.startswith("loaded:"))
    in_vram = sum(v for k, v in sizes.items() if k.startswith("vram:"))
    free = free_memory() + (loaded - in_vram) - reserve(vm.total)  # commit headroom on Windows (RAM + page file)
    gpu = None
    if sizes.get("vram:" + model):
        # This model runs (partly) on the GPU: the free dedicated VRAM, plus what loaded models hold there now, is
        # room too. Without a loaded copy the split is not known yet, so only RAM is counted (the safe side).
        gpu = vram()
        if gpu and gpu.get("free") is not None:
            free += max(0, gpu["free"] + in_vram - 512 * 1024 ** 2)
        else:
            free += in_vram
    parallel, kv_bytes = _env()
    per_token = kv_tok * kv_bytes / 2 * parallel
    room = free - weights * 1.05
    fit = int(room / per_token) // 1024 * 1024 if room > 0 else 0
    return {"max": fit, "short": fit < 2048, "parallel": parallel, "weights_gb": round(weights / 1024 ** 3, 1),
            "reserve_gb": round(reserve(vm.total) / GB, 1),
            "free_gb": round(free / 1024 ** 3, 1), "total_gb": round(vm.total / 1024 ** 3, 1),
            "cap": _CAPS.get(model),
            "vram_gb": round(gpu["total"] / 1024 ** 3, 1) if gpu else None,
            "vram_free_gb": round(gpu["free"] / 1024 ** 3, 1) if gpu and gpu.get("free") is not None else None}
