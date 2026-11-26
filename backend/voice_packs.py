"""Install local Turkish voice packs from the command line (installer.py and install.bat / install.sh use it).

    python backend/voice_packs.py --list                  # every pack, its size, licence and whether it fits here
    python backend/voice_packs.py light                   # a whole tier: light | medium | gpu | all
    python backend/voice_packs.py seda pocket xtts        # chosen packs
    python backend/voice_packs.py --remove xtts

Packs that cannot run on this computer (an NVIDIA GPU pack without one) are skipped with the reason. Each pack
prints PROGRESS lines; a failed pack is a warning, the others go on."""
import asyncio
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from app.voice import packs  # noqa: E402


def pick(args: list[str]) -> list[str]:
    out: list[str] = []
    for a in args:
        if a == "all":
            out += list(packs.PACKS)
        elif a in packs.TIERS:
            out += [e for e, p in packs.PACKS.items() if p["tier"] == a]
        elif a in packs.PACKS:
            out.append(a)
        else:
            raise SystemExit(f"unknown pack or tier: {a} (use --list)")
    return list(dict.fromkeys(out))


async def main() -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    args = sys.argv[1:]
    if not args or args[0] == "--list":
        hw = packs.hardware()
        print(f"computer: {'NVIDIA ' + str(hw['vram_gb']) + ' GB' if hw['cuda'] else 'Apple GPU' if hw['mps'] else 'CPU only'}")
        for e, p in packs.PACKS.items():
            f = packs.fit(e)
            print(f"  {p['tier']:6} {e:10} {p['name']:20} {p['mb']:>6} MB  {p['license']:20} "
                  f"{'' if p['commercial'] else 'non-commercial '}{'installed' if packs.installed(e) else ''}"
                  f"{'' if f['state'] == 'ok' else ' [' + f['state'] + ': ' + f.get('reason', '') + ']'}")
        return 0
    if args[0] == "--json":
        print(json.dumps({e: {"installed": packs.installed(e), "fit": packs.fit(e)} for e in packs.PACKS}))
        return 0
    if args[0] == "--measure":  # voices installed without a measured gender: measure them now
        from app.voice import catalog
        for e in pick(args[1:] or ["all"]):
            facts = packs.info(e)
            if not facts:
                continue
            todo = [v["name"] for v in facts.get("voices", []) if not v.get("gender")]
            for i, name in enumerate(todo):
                try:
                    await asyncio.to_thread(packs.synth, e, name, catalog.SAMPLE["tr"], {})
                    print(f"PROGRESS {(i + 1) / len(todo):.4f} {e} {name}", flush=True)
                except Exception as ex:  # noqa: BLE001
                    print(f"[WARN] {e} {name}: {str(ex)[-200:]}", flush=True)
            packs.worker(e).stop()
            left = [v["name"] for v in (packs.info(e) or {}).get("voices", []) if not v.get("gender")]
            print(f"  - {e}: {len(todo) - len(left)} measured, {len(left)} left", flush=True)
        return 0
    if args[0] == "--remove":
        for e in pick(args[1:]):
            packs.remove(e)
            print("  -", e, "removed")
        return 0
    force = "--force" in args  # also packs this computer cannot run well (a GPU pack on the CPU: very slow)
    asked = pick([a for a in args if a != "--force"])
    todo = []
    for e in asked:  # what is already there or cannot run here is said once, up front, and left out of the bar
        p = packs.PACKS[e]
        f = packs.fit(e)
        if packs.installed(e):
            print(f"  - {p['name']} already installed, skipped", flush=True)
        elif f["state"] == "no" and not force:
            print(f"[SKIP] {p['name']}: this computer has no NVIDIA GPU with {p.get('vram', 0)} GB "
                  f"({f.get('reason')})", flush=True)
        else:
            todo.append(e)
    total = sum(packs.PACKS[e]["mb"] for e in todo) or 1
    print(f"{len(todo)} voice pack(s) to install, ~{total / 1000:.1f} GB", flush=True)
    failed = 0
    done_mb = 0.0  # progress by size: a 13 GB pack moves the bar (and the time left) more than a 120 MB one
    for e in todo:
        p = packs.PACKS[e]
        print(f"== {p['name']} ({p['mb']} MB, {p['license']})", flush=True)

        last = [-1.0]

        def on(frac: float, name=p["name"], mb=p["mb"], base=done_mb, last=last) -> None:
            if frac - last[0] >= 0.005 or frac >= 1:  # only when it moved: no wall of identical lines
                last[0] = frac
                print(f"PROGRESS {(base + frac * mb) / total:.4f} {name}", flush=True)
        where = packs.catalog.ROOT
        while not where.exists() and where != where.parent:
            where = where.parent
        free_mb = shutil.disk_usage(where).free / 1e6
        if free_mb < p["mb"] * 1.3 + 1000:
            failed += 1
            done_mb += p["mb"]
            print(f"[SKIP] {p['name']}: not enough disk space ({free_mb / 1000:.1f} GB free, "
                  f"~{p['mb'] * 1.3 / 1000:.1f} GB needed)", flush=True)
            continue
        for attempt in (1, 2):  # a dropped download or a busy mirror: once more before giving up
            try:
                facts = await packs.install(e, on, force=force)
                names = ", ".join(f"{v['name']} ({v.get('gender') or '?'})" for v in facts["voices"][:8])
                print(f"  - {p['name']} ok on {facts.get('device')}: {names}", flush=True)
                break
            except Exception as ex:  # noqa: BLE001
                lasting = any(s in str(ex) for s in ("No solution found", "does not match given name",
                                                     "cannot run on this computer"))
                packs.worker(e).stop()  # the failed try's model must not hold the memory of the next one
                lasting = lasting or "not enough free memory" in str(ex)
                if attempt == 1 and not lasting and not isinstance(ex, (ValueError, MemoryError)):
                    print(f"  ~ {p['name']}: {str(ex)[-200:]} - trying once more", flush=True)
                    continue
                failed += 1
                print(f"[WARN] {p['name']}: {str(ex)[-600:]}", flush=True)
        packs.worker(e).stop()  # one model in memory at a time: big packs one after another, never together
        done_mb += p["mb"]
        print(f"PROGRESS {done_mb / total:.4f} {p['name']}", flush=True)
    print(f"PROGRESS 1.0000 {len(todo) - failed}/{len(todo)}", flush=True)
    for w in packs.WORKERS.values():
        w.stop()
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
