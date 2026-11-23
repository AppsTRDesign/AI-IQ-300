"""Charts for the evaluation report: SVG files that report.md embeds, and a self-contained report.html.

Three views, each also given as a table (the numbers are never colour-only):
  scores   three measures per model (per task, per check, fully passed) as grouped bars
  heatmap  task x model, each cell the task's pass share (one-hue blue ramp) with "passed/total" written in it
  time     where each task's time went (provider wait, generation, tools, wait after errors, app) as stacked bars

Colours follow a validated palette (categorical slots in fixed order, a single-hue sequential ramp, light and dark
steps chosen separately); text is always in ink colours, never in a series colour.
"""
from __future__ import annotations

import html
import json

# --------------------------------------------------------------------------------------------- palette (light / dark)
SERIES = [("#2a78d6", "#3987e5"), ("#eb6834", "#d95926"), ("#1baf7a", "#199e70"), ("#eda100", "#c98500"),
          ("#e87ba4", "#d55181")]
RAMP = ["#cde2fb", "#b7d3f6", "#9ec5f4", "#86b6ef", "#6da7ec", "#5598e7", "#3987e5", "#2a78d6", "#256abf",
        "#1c5cab", "#184f95", "#104281", "#0d366b"]
STYLE = """<style>
.v{--surface:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--muted:#898781;--grid:#e1e0d9;--base:#c3c2b7;--empty:#f0efec;
%LIGHT%font-family:system-ui,-apple-system,"Segoe UI",sans-serif}
@media (prefers-color-scheme:dark){.v{--surface:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--muted:#898781;--grid:#2c2c2a;
--base:#383835;--empty:#2c2c2a;%DARK%}}
.v .bg{fill:var(--surface)} .v text{fill:var(--ink2);font-size:12px} .v .t{fill:var(--ink);font-size:14px;font-weight:600}
.v .ink{fill:var(--ink)} .v .mut{fill:var(--muted);font-size:11px} .v .grid{stroke:var(--grid);stroke-width:1}
.v .base{stroke:var(--base);stroke-width:1} .v .on{fill:#ffffff} .v .off{fill:#0b0b0b}
.v [data-tip]:hover{opacity:.85}
</style>"""


def _style() -> str:
    light = "".join(f"--s{i + 1}:{c[0]};" for i, c in enumerate(SERIES))
    dark = "".join(f"--s{i + 1}:{c[1]};" for i, c in enumerate(SERIES))
    return STYLE.replace("%LIGHT%", light).replace("%DARK%", dark)


def _e(s) -> str:
    return html.escape(str(s), quote=True)


def _short(s: str, n: int) -> str:
    return s if len(s) <= n else s[: n - 1] + "…"


def _svg(w: int, h: int, body: list[str], label: str) -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" class="v" viewBox="0 0 {w} {h}" width="{w}" height="{h}" '
            f'role="img" aria-label="{_e(label)}">{_style()}<rect class="bg" width="{w}" height="{h}" rx="8"/>'
            + "".join(body) + "</svg>")


def _bar(x: float, y: float, w: float, h: float, fill: str, tip: str, round_end: bool = True) -> str:
    """A horizontal or vertical bar segment; the data end is rounded 4 px, the baseline end stays square."""
    if w <= 0 or h <= 0:
        return ""
    t = f"<title>{_e(tip)}</title>"
    if not round_end:
        return f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" fill="{fill}" data-tip="{_e(tip)}">{t}</rect>'
    r = min(4, w / 2, h / 2)
    return (f'<path d="M{x:.1f},{y:.1f} h{w - r:.1f} a{r},{r} 0 0 1 {r},{r} v{h - 2 * r:.1f} a{r},{r} 0 0 1 -{r},{r} '
            f'h-{w - r:.1f} z" fill="{fill}" data-tip="{_e(tip)}">{t}</path>')


def _vbar(x: float, base: float, w: float, h: float, fill: str, tip: str) -> str:
    if h <= 0:
        return ""
    r = min(4, w / 2, h)
    return (f'<path d="M{x:.1f},{base:.1f} v-{h - r:.1f} a{r},{r} 0 0 1 {r},-{r} h{w - 2 * r:.1f} a{r},{r} 0 0 1 {r},{r} '
            f'v{h - r:.1f} z" fill="{fill}" data-tip="{_e(tip)}"><title>{_e(tip)}</title></path>')


def _legend(items: list[tuple[str, str]], x: float, y: float) -> list[str]:
    out, cx = [], x
    for name, color in items:
        out.append(f'<rect x="{cx:.0f}" y="{y - 9:.0f}" width="10" height="10" rx="2" fill="{color}"/>'
                   f'<text x="{cx + 15:.0f}" y="{y:.0f}">{_e(name)}</text>')
        cx += 15 + len(name) * 6.6 + 18
    return out


# --------------------------------------------------------------------------------------------- 1. three scores
def scores_svg(models: list[str], scores: dict, t: dict) -> str:
    metrics = [("by_task", t["by_task"]), ("by_check", t["by_check"]), ("full_pass_rate", t["passed"])]
    left, top, ph = 48, 84, 200
    group = max(150, 3 * 34 + 40)
    w = max(560, left + group * len(models) + 24)
    h = top + ph + 54
    body = [f'<text class="t" x="20" y="28">{_e(t["chart_scores"])}</text>']
    body += _legend([(n, f"var(--s{i + 1})") for i, (_, n) in enumerate(metrics)], 20, 50)
    base = top + ph
    for p in (0, 25, 50, 75, 100):
        y = base - ph * p / 100
        body.append(f'<line class="{"base" if p == 0 else "grid"}" x1="{left}" x2="{w - 16}" y1="{y:.1f}" y2="{y:.1f}"/>'
                    f'<text class="mut" x="{left - 8}" y="{y + 4:.1f}" text-anchor="end">{p}%</text>')
    for gi, m in enumerate(models):
        s = scores[m]
        gx = left + 20 + gi * group
        for i, (k, name) in enumerate(metrics):
            v = s[k]
            x = gx + i * 34
            extra = {"by_task": "", "by_check": f" ({s['checks_passed']}/{s['checks']})",
                     "full_pass_rate": f" ({s['full_passed']}/{s['tasks']})"}[k]
            body.append(_vbar(x, base, 30, ph * v, f"var(--s{i + 1})", f"{m} · {name}: {v:.1%}{extra}"))
            body.append(f'<text class="ink" x="{x + 15}" y="{base - ph * v - 6:.1f}" text-anchor="middle" '
                        f'style="font-size:11px">{v:.0%}</text>')
        body.append(f'<text x="{gx + 49}" y="{base + 20}" text-anchor="middle">{_e(_short(m, 24))}<title>{_e(m)}</title></text>')
    return _svg(w, h, body, t["chart_scores"])


# --------------------------------------------------------------------------------------------- 2. heatmap
def heatmap_svg(results: list[dict], models: list[str], tasks: list[tuple[str, str]], t: dict) -> str:
    left, top, cw, ch = 210, 76, 132, 34
    w = max(560, left + cw * len(models) + 20)
    h = top + ch * len(tasks) + 44
    body = [f'<text class="t" x="20" y="28">{_e(t["chart_heat"])}</text>',
            f'<text class="mut" x="20" y="46">{_e(t["chart_heat_note"])}</text>']
    by = {(r["model"], r["task"]): r for r in results}
    for j, m in enumerate(models):
        prov, _, name = m.partition(":")
        x = left + j * cw + cw / 2
        body.append(f'<text class="ink" x="{x:.0f}" y="{top - 20}" text-anchor="middle" style="font-size:11px">'
                    f'{_e(_short(prov, 18))}<title>{_e(m)}</title></text>'
                    f'<text class="mut" x="{x:.0f}" y="{top - 7}" text-anchor="middle">{_e(_short(name.rsplit("/", 1)[-1], 20))}</text>')
    for i, (tid, title) in enumerate(tasks):
        y = top + i * ch
        body.append(f'<text x="{left - 10}" y="{y + ch / 2 + 4:.0f}" text-anchor="end">{_e(_short(title, 30))}</text>')
        for j, m in enumerate(models):
            x = left + j * cw
            r = by.get((m, tid))
            if not r:
                body.append(f'<rect x="{x + 1}" y="{y + 1}" width="{cw - 2}" height="{ch - 2}" rx="4" fill="var(--empty)"/>')
                continue
            v = r["passed"] / max(1, r["total"])
            step = RAMP[min(len(RAMP) - 1, int(round(v * (len(RAMP) - 1))))]
            dark_cell = RAMP.index(step) >= 6
            tip = f"{m} · {title}: {r['passed']}/{r['total']} ({v:.0%}), {r['status']}, {r['seconds']:.0f} s"
            mark = " ✓" if r["full_pass"] else ""
            body.append(f'<rect x="{x + 1}" y="{y + 1}" width="{cw - 2}" height="{ch - 2}" rx="4" fill="{step}" '
                        f'data-tip="{_e(tip)}"><title>{_e(tip)}</title></rect>'
                        f'<text class="{"on" if dark_cell else "off"}" x="{x + cw / 2:.0f}" y="{y + ch / 2 + 4:.0f}" '
                        f'text-anchor="middle" style="font-size:12px;font-weight:600;pointer-events:none">'
                        f'{r["passed"]}/{r["total"]}{mark}</text>')
    return _svg(w, h, body, t["chart_heat"])


# --------------------------------------------------------------------------------------------- 3. time split
PARTS = [("wait_s", "wait"), ("gen_s", "gen"), ("tools_s", "tools_t"), ("retry_s", "retry_t"), ("app_s", "app_t")]


def time_svg(results: list[dict], models: list[str], t: dict) -> str:
    left, top, bh, gap, w = 210, 70, 18, 10, 760
    rows: list[tuple[str, dict | None]] = []
    for m in models:
        rows.append((m, None))
        rows += [(m, r) for r in results if r["model"] == m]
    total = lambda r: sum((r.get("time_split") or {}).get(k) or 0 for k, _ in PARTS)  # noqa: E731
    raw = max([total(r) for _, r in rows if r] + [1])
    step = next((s for s in (1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 900, 1800, 3600, 7200) if raw / s <= 5), 7200)
    ticks = max(1, -(-int(raw) // step))
    mx = step * ticks
    plot = w - left - 70
    h = top + sum(22 if r is None else bh + gap for _, r in rows) + 30
    body = [f'<text class="t" x="20" y="28">{_e(t["where"])}</text>']
    body += _legend([(t[n], f"var(--s{i + 1})") for i, (_, n) in enumerate(PARTS)], 20, 52)
    y = top
    for p in range(0, ticks + 1):
        x = left + plot * p / ticks
        v = step * p
        label = f"{v} s" if step < 60 else f"{v // 60} min"
        body.append(f'<line class="{"base" if p == 0 else "grid"}" x1="{x:.1f}" x2="{x:.1f}" y1="{top}" y2="{h - 26}"/>'
                    f'<text class="mut" x="{x:.1f}" y="{h - 10}" text-anchor="middle">{label}</text>')
    for m, r in rows:
        if r is None:
            body.append(f'<text class="ink" x="20" y="{y + 15}" style="font-weight:600">{_e(_short(m, 60))}</text>')
            y += 22
            continue
        body.append(f'<text x="{left - 10}" y="{y + bh - 4}" text-anchor="end">{_e(_short(r["title"], 30))}</text>')
        x = left
        x_split = r.get("time_split") or {}
        segs = [(k, n, i, x_split.get(k) or 0) for i, (k, n) in enumerate(PARTS) if (x_split.get(k) or 0) > 0]
        for si, (k, n, i, v) in enumerate(segs):
            seg_w = plot * v / mx
            last = si == len(segs) - 1
            tip = f"{m} · {r['title']} · {t[n]}: {v:.0f} s ({v / max(1e-9, total(r)):.0%})"
            if k == "wait_s" and x_split.get("max_wait_s"):
                tip += f" · {t['max_wait']} {x_split['max_wait_s']:.0f} s"
            body.append(_bar(x, y, max(0.0, seg_w - (0 if last else 2)), bh, f"var(--s{i + 1})", tip, round_end=last))
            x += seg_w
        tip = f"{m} · {r['title']}: {total(r):.0f} s, {t['max_wait']} {x_split.get('max_wait_s') or 0:.0f} s"
        body.append(f'<text class="mut" x="{x + 6:.1f}" y="{y + bh - 4}" data-tip="{_e(tip)}">{total(r):.0f} s'
                    f'<title>{_e(tip)}</title></text>')
        y += bh + gap
    return _svg(w, h, body, t["where"])


# --------------------------------------------------------------------------------------------- report.html
PAGE = """<!doctype html><html lang="%LANG%"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>%TITLE%</title><style>
:root{--page:#f9f9f7;--card:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--muted:#898781;--line:#e1e0d9;--good:#006300;--bad:#d03b3b}
@media (prefers-color-scheme:dark){:root{--page:#0d0d0d;--card:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--line:#2c2c2a;
--good:#0ca30c;--bad:#e66767}}
*{box-sizing:border-box}body{margin:0;background:var(--page);color:var(--ink);font:14px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:1000px;margin:0 auto;padding:24px 16px 64px}h1{font-size:24px;margin:0 0 4px}h2{font-size:17px;margin:32px 0 10px}
.sub{color:var(--ink2);margin:0 0 20px}.note{color:var(--muted);font-size:12.5px;margin:8px 0 0}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px}
.tile{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px}
.tile .m{font-size:12px;color:var(--ink2);word-break:break-all}.tile .row{display:flex;gap:16px;margin-top:8px;flex-wrap:wrap}
.tile b{display:block;font-size:26px;line-height:1.1}.tile span{font-size:12px;color:var(--ink2)}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:8px;overflow-x:auto}
.card svg{display:block;max-width:100%;height:auto}.verdict{padding:12px 16px}.verdict ul{margin:0;padding-left:18px}
.verdict li{margin:4px 0}
table{border-collapse:collapse;width:100%;font-size:13px;font-variant-numeric:tabular-nums}
th,td{text-align:left;padding:6px 8px;border-bottom:1px solid var(--line);vertical-align:top}th{color:var(--ink2);font-weight:600}
.ok{color:var(--good);font-weight:600}.no{color:var(--bad);font-weight:600}details{margin:6px 0}summary{cursor:pointer}
code{font-size:12.5px}#tip{position:fixed;pointer-events:none;background:var(--card);color:var(--ink);border:1px solid var(--line);
border-radius:6px;padding:6px 9px;font-size:12.5px;box-shadow:0 4px 14px rgba(0,0,0,.15);display:none;max-width:340px;z-index:9}
</style></head><body><main>%BODY%</main><div id="tip"></div><script>
const tip=document.getElementById('tip');
document.addEventListener('mousemove',e=>{const el=e.target.closest('[data-tip]');
if(!el){tip.style.display='none';return}tip.textContent=el.getAttribute('data-tip');tip.style.display='block';
const x=Math.min(e.clientX+14,innerWidth-tip.offsetWidth-8),y=Math.min(e.clientY+14,innerHeight-tip.offsetHeight-8);
tip.style.left=x+'px';tip.style.top=y+'px'});
document.querySelectorAll('svg title').forEach(t=>t.remove());
</script></body></html>"""


def _table(head: list[str], rows: list[list[str]]) -> str:
    return ("<div class=\"card\"><table><thead><tr>" + "".join(f"<th>{_e(h)}</th>" for h in head) + "</tr></thead><tbody>"
            + "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows) + "</tbody></table></div>")


def page(data: dict, t: dict, charts: dict[str, str]) -> str:
    results, scores = data["results"], data["scores"]
    models = list(scores)
    tiles = []
    for m in models:
        s = scores[m]
        tiles.append(f'<div class="tile"><div class="m"><code>{_e(m)}</code></div><div class="row">'
                     f'<div><b>{s["by_task"]:.1%}</b><span>{_e(t["by_task"])}</span></div>'
                     f'<div><b>{s["by_check"]:.1%}</b><span>{_e(t["by_check"])} · {s["checks_passed"]}/{s["checks"]}</span></div>'
                     f'<div><b>{s["full_pass_rate"]:.0%}</b><span>{_e(t["passed"])} · {s["full_passed"]}/{s["tasks"]}</span></div>'
                     "</div></div>")
    rows = []
    for r in results:
        x = r.get("time_split") or {}
        f = lambda k: f"{x[k]:.0f} s" if isinstance(x.get(k), (int, float)) else "—"  # noqa: E731
        cls = "ok" if r["full_pass"] else "no"
        rows.append([f"<code>{_e(r['model'])}</code>", _e(r["title"]), f'<span class="{cls}">{r["passed"]}/{r["total"]}</span>',
                     _e(r["status"]), f"{r['seconds']:.0f} s", str(r["turns"] or 0), f"{r['out_tokens'] or 0:,}",
                     f"{r['tool_calls'] or 0} ({r['tool_errors'] or 0})", f("wait_s"), f("gen_s"), f("tools_s"), f("max_wait_s")])
    checks = []
    for r in results:
        items = "".join(f'<li><span class="{"ok" if c["ok"] else "no"}">{"✓" if c["ok"] else "✗"}</span> {_e(c["name"])}'
                        + (f' <span class="note">— {_e(c["info"])}</span>' if c["info"] else "") + "</li>" for c in r["checks"])
        items += "".join(f'<li><span class="note">ℹ {"✓" if c["ok"] else "–"}</span> {_e(c["name"])}'
                         + (f' <span class="note">— {_e(c["info"])}</span>' if c["info"] else "") + "</li>"
                         for c in r.get("notes") or [])
        checks.append(f"<details{'' if r['full_pass'] else ' open'}><summary><code>{_e(r['model'])}</code> · {_e(r['title'])} "
                      f"({r['passed']}/{r['total']})</summary><ul>{items}</ul></details>")
    body = (f"<h1>{_e(t['title'])}</h1><p class=\"sub\">{_e(t['version'])}: {_e(data['version'])} · {_e(t['date'])}: "
            f"{_e(data['date'])} · {_e(t['lang'])}: {_e(data['lang'])}</p>"
            f"<div class=\"tiles\">{''.join(tiles)}</div><p class=\"note\">{_e(t['scores_note'])}</p>"
            + (f"<h2>{_e(t['verdict'])}</h2><div class=\"card verdict\"><ul>"
               + "".join(f"<li>{_e(x)}</li>" for x in data["verdict"])
               + f"</ul><p class=\"note\">{_e(t['verdict_note'])}</p></div>" if data.get("verdict") else "")
            + f""
            f"<h2>{_e(t['chart_scores'])}</h2><div class=\"card\">{charts['scores']}</div>"
            f"<h2>{_e(t['chart_heat'])}</h2><div class=\"card\">{charts['heatmap']}</div>"
            f"<h2>{_e(t['where'])}</h2><div class=\"card\">{charts['time']}</div><p class=\"note\">{_e(t['where_note'])}</p>"
            f"<h2>{_e(t['table'])}</h2>"
            + _table([t["model"], t["task"], t["score"], t["status"], t["time"], t["turns"], t["tokens"], t["tools"],
                      t["wait"], t["gen"], t["tools_t"], t["max_wait"]], rows)
            + f"<h2>{_e(t['checks'])}</h2>" + "".join(checks)
            + f"<p class=\"note\">{_e(t['note'])}</p>")
    return PAGE.replace("%LANG%", data["lang"]).replace("%TITLE%", _e(t["title"])).replace("%BODY%", body)


def write(out, data: dict, t: dict) -> dict[str, str]:
    """Writes charts/*.svg and report.html next to report.md; returns the chart file names for the Markdown."""
    results = data["results"]
    models = list(data["scores"])
    tasks = list(dict.fromkeys((r["task"], r["title"]) for r in results))
    charts = {"scores": scores_svg(models, data["scores"], t), "heatmap": heatmap_svg(results, models, tasks, t),
              "time": time_svg(results, models, t)}
    (out / "charts").mkdir(exist_ok=True)
    for k, svg in charts.items():
        (out / "charts" / f"{k}.svg").write_text(svg, encoding="utf-8")
    (out / "report.html").write_text(page(data, t, charts), encoding="utf-8")
    return {k: f"charts/{k}.svg" for k in charts}


if __name__ == "__main__":  # re-draw an existing report: python charts.py eval/reports/<run>
    import sys
    from pathlib import Path

    from run_eval import T, scores
    d = Path(sys.argv[1])
    data = json.loads((d / "report.json").read_text(encoding="utf-8"))
    if "scores" not in data:  # a report from before v0.20.1
        ms = dict.fromkeys(r["model"] for r in data["results"])
        data["scores"] = {m: scores([r for r in data["results"] if r["model"] == m]) for m in ms}
    print(write(d, data, T[data.get("lang", "tr")]))
