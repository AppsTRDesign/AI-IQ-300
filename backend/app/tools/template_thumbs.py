"""Gallery thumbnails of spreadsheet and slide templates: each layout drawn as what it really makes (a dashboard with
KPI cards and a chart, a budget with a total row, a year calendar, a Gantt plan, a pipeline; title slides in their
own look), in the template's colours. PDF / Word thumbnails are real pages (doc_templates._real_page)."""
from __future__ import annotations

import html


def _head(font: str) -> str:
    return ("<!doctype html><html><head><meta charset='utf-8'><style>html,body{margin:0;height:100%;overflow:hidden;"
            f"font-family:{font};-webkit-font-smoothing:antialiased;background:#e9ebef}}*{{box-sizing:border-box}}"
            ".sheet{position:absolute;left:7%;right:7%;top:9%;bottom:0;background:#fff;box-shadow:0 6px 18px #0002;"
            "border-radius:4px 4px 0 0;overflow:hidden;font-size:7px;color:#1f2933}"
            ".band{padding:6px 8px;font-weight:700;font-size:11px;color:#fff}.sub{padding:2px 8px 4px;color:#64748b;font-size:6px}"
            "table{border-collapse:collapse;width:100%}td,th{border-bottom:1px solid #eef1f5;padding:2px 4px;text-align:left;"
            "white-space:nowrap;overflow:hidden}th{font-weight:700}")


def xlsx_thumb(t: dict, name: str, lang: str) -> str:
    from .xlsx_design import LAYOUT_OF, MONTHS
    a, d, tint = t["colors"]
    lay = t.get("xlsx_layout") or LAYOUT_OF.get(t["id"], "dashboard")
    dark = t.get("cover") == "dark"
    band = "#0b1220" if dark else d
    bg, fg = ("#0b1220", "#e2e8f0") if dark else ("#fff", "#1f2933")
    nm = html.escape(name)
    tr = lang == "tr"
    th = (f"background:#fff;color:{d};border-bottom:2px solid {d}" if t.get("table") == "lines" else
          f"background:{tint};color:{d}" if t.get("table") == "soft" else f"background:{band if dark else a};color:#fff")
    css = _head('"Segoe UI",Arial,sans-serif') + (
        f".sheet{{background:{bg};color:{fg}}}.band{{background:{band}}}th{{{th}}}"
        f".kp{{display:flex;gap:5px;padding:5px 8px}}.k{{flex:1;border:1px solid {'#1e293b' if dark else '#e2e8f0'};"
        f"border-top:2px solid {a};border-radius:3px;padding:3px 5px;background:{'#111a2e' if dark else tint}}}"
        f".k span{{display:block;font-size:5.5px;opacity:.7;text-transform:uppercase}}.k b{{font-size:12px;color:{'#fff' if dark else a}}}"
        f".chip{{display:inline-block;padding:0 4px;border-radius:6px;font-size:6px}}</style></head><body><div class='sheet'>")
    end = "</div></body></html>"
    if lay == "dashboard":
        pts = "0,30 20,26 40,20 60,23 80,12 100,8 120,4"
        rows = "".join(f"<tr><td>{m}</td><td>{v:,}</td><td>{v // 7:,}</td></tr>" for m, v in
                       zip(MONTHS["tr" if tr else "en"][:6], [3100, 3500, 4200, 3900, 4800, 5300]))
        return (css + f"<div class='band'>{nm}</div><div class='kp'><div class='k'><span>{'Ziyaretçi' if tr else 'Visitors'}</span>"
                f"<b>31,500</b></div><div class='k'><span>{'Kayıt' if tr else 'Sign-ups'}</span><b>4,480</b></div>"
                f"<div class='k'><span>{'Gelir' if tr else 'Revenue'}</span><b>$403,700</b></div></div>"
                f"<svg viewBox='0 0 120 34' style='width:92%;margin:0 4%;height:38px'><polyline points='{pts}' fill='none' "
                f"stroke='{a}' stroke-width='2'/><polygon points='{pts} 120,34 0,34' fill='{a}' opacity='.15'/></svg>"
                f"<table><tr><th>{'Ay' if tr else 'Month'}</th><th>{'Ziyaretçi' if tr else 'Visitors'}</th><th>{'Kayıt' if tr else 'Sign-ups'}</th></tr>{rows}</table>" + end)
    if lay == "budget":
        rows = "".join(f"<tr><td>{k}</td><td>{x:,}</td><td>{y:,}</td><td>{z:,}</td></tr>" for k, x, y, z in
                       [("Gelir" if tr else "Revenue", 120000, 128000, 135000), ("Personel" if tr else "Payroll", -60000, -60000, -62000),
                        ("Pazarlama" if tr else "Marketing", -15000, -18000, -14000), ("Kira" if tr else "Rent", -12000, -12000, -12000)])
        bars = "".join(f"<i style='display:inline-block;width:9px;margin:0 3px;height:{h}px;background:{a}'></i>" for h in (18, 24, 30, 22, 34, 28))
        return (css + f"<div class='band'>{nm}</div><div class='sub'>{'Özet' if tr else 'Summary'}</div>"
                f"<div class='kp'><div class='k'><span>{'Net' if tr else 'Net'}</span><b>$26,114</b></div>"
                f"<div class='k'><span>FY</span><b>$21,500</b></div></div><table><tr><th>{'Kalem' if tr else 'Item'}</th>"
                f"<th>Q1</th><th>Q2</th><th>Q3</th></tr>{rows}<tr><td><b>{'Toplam' if tr else 'Total'}</b></td><td><b>33,000</b></td>"
                f"<td><b>38,000</b></td><td><b>47,000</b></td></tr></table><div style='padding:6px 8px;display:flex;align-items:flex-end;"
                f"height:42px'>{bars}</div>" + end)
    if lay == "calendar":
        months = MONTHS["tr" if tr else "en"]
        cal = ""
        for m in range(6):
            cells = "".join(f"<td style='{'background:' + a + ';color:#fff' if (m * 7 + i) % 9 == 3 else ''}'>{i + 1}</td>"
                            + ("</tr><tr>" if (i + 1) % 7 == 0 else "") for i in range(28))
            cal += (f"<div style='width:31%;display:inline-block;margin:0 1% 5px;vertical-align:top'><div style='background:{d};"
                    f"color:#fff;font-weight:700;text-align:center;font-size:7px;padding:1px'>{months[m]}</div>"
                    f"<table style='font-size:5.5px'><tr>{cells}</tr></table></div>")
        return css + f"<div class='band' style='background:{a}'>{nm}</div><div style='padding:5px 4px'>{cal}</div>" + end
    if lay == "tracker":
        tasks = [("Analiz" if tr else "Discovery", 0, 3, "#16a34a"), ("Tasarım" if tr else "Design", 2, 5, "#f59e0b"),
                 ("Geliştirme" if tr else "Build", 4, 9, "#f59e0b"), ("Test", 8, 11, "#dc2626"), ("Yayın" if tr else "Launch", 10, 12, "#64748b")]
        rows = "".join(f"<tr><td>{n}</td><td><span class='chip' style='background:{c}22;color:{c}'>●</span></td>"
                       + "".join(f"<td style='padding:0;width:6px;background:{a if s <= w < e else 'transparent'}'></td>" for w in range(12))
                       + "</tr>" for n, s, e, c in tasks)
        return (css + f"<div class='band'>{nm}</div><div class='sub'>{'Haftalık plan' if tr else 'Weekly plan'}</div>"
                f"<table><tr><th>{'Görev' if tr else 'Task'}</th><th></th>" + "".join(f"<th style='padding:0'></th>" for _ in range(12))
                + f"</tr>{rows}</table>" + end)
    if lay == "pipeline":
        rows = "".join(f"<tr><td>{c}</td><td><span class='chip' style='background:{col}22;color:{col}'>{s}</span></td><td>${v:,}</td></tr>"
                       for c, s, v, col in [("Acme", "Teklif" if tr else "Proposal", 120000, "#f59e0b"), ("Beta", "Kazanıldı" if tr else "Won", 80000, "#16a34a"),
                                            ("Gama", "Görüşme" if tr else "Meeting", 45000, "#2563eb"), ("Delta", "Kaybedildi" if tr else "Lost", 30000, "#dc2626")])
        return (css + f"<div class='band'>{nm}</div><div class='kp'><div class='k' style='text-align:center'><span>"
                f"{'Toplam huni' if tr else 'Total pipeline'}</span><b style='font-size:15px'>$11,850,000</b></div><div class='k' "
                f"style='text-align:center'><span>{'Kazanma oranı' if tr else 'Win rate'}</span><b style='font-size:15px'>67%</b></div></div>"
                f"<table><tr><th>{'Müşteri' if tr else 'Company'}</th><th>{'Aşama' if tr else 'Stage'}</th><th>{'Tutar' if tr else 'Value'}</th></tr>{rows}</table>" + end)
    if lay == "scorecard":
        rows = "".join(f"<tr><td>{g}</td><td>{h}</td><td>{v}</td><td><span style='color:{c};font-size:10px'>●</span></td></tr>"
                       for g, h, v, c in [("Ciro" if tr else "Revenue", "1.000", "1.080", "#16a34a"), ("NPS", "60", "57", "#f59e0b"),
                                          ("Teslim" if tr else "On time", "95%", "80%", "#dc2626"), ("Maliyet" if tr else "Cost", "500", "470", "#16a34a")])
        return (css + f"<div class='band'>{nm}</div><div class='sub'>{'Hedef / gerçekleşen' if tr else 'Target / actual'}</div>"
                f"<table><tr><th>{'Gösterge' if tr else 'Metric'}</th><th>{'Hedef' if tr else 'Target'}</th><th>{'Gerçek' if tr else 'Actual'}</th><th></th></tr>{rows}</table>" + end)
    rows = "".join(f"<tr style='{'background:#fee2e2;color:#991b1b;font-weight:700' if low else ''}'><td>{u}</td><td>{s}</td><td>{k}</td></tr>"
                   for u, s, k, low in [("Kablo" if tr else "Cable", 120, 50, False), ("Adaptör" if tr else "Adapter", 12, 20, True),
                                        ("Mouse", 40, 15, False), ("Klavye" if tr else "Keyboard", 8, 10, True), ("Monitör" if tr else "Monitor", 25, 5, False)])
    return (css + f"<div class='band'>{nm}</div><div class='sub'>{'Kritik seviyedekiler kırmızı' if tr else 'Below reorder level in red'}</div>"
            f"<table><tr><th>{'Ürün' if tr else 'Item'}</th><th>{'Stok' if tr else 'Stock'}</th><th>{'Kritik' if tr else 'Reorder'}</th></tr>{rows}</table>" + end)


def pptx_thumb(t: dict, name: str, outline: list[str], lang: str) -> str:
    """A title slide in the template's own look, two slides stacked behind it (like a deck)."""
    a, d, tint = t["colors"]
    look = t.get("cover") or "dark"
    nm = html.escape(name)
    sub = html.escape(" · ".join(outline[1:4]))
    if look in ("split",):
        inner = (f"<div style='position:absolute;left:0;top:0;bottom:0;width:36%;background:{a}'></div>"
                 f"<div style='position:absolute;left:36%;top:0;bottom:0;width:1.2%;background:{d}'></div>"
                 f"<div style='position:absolute;left:43%;right:6%;top:30%;color:{d}'><div style='font-size:15px;font-weight:700;"
                 f"line-height:1.1'>{nm}</div><div style='font-size:7px;color:#64748b;margin-top:5px'>{sub}</div></div>")
        bg = "#fff"
    elif look in ("minimal", "editorial"):
        inner = (f"<div style='position:absolute;left:8%;top:22%;width:16%;height:3px;background:{a}'></div>"
                 f"<div style='position:absolute;left:8%;right:8%;top:30%;color:#0f172a'><div style='font-size:16px;"
                 f"font-weight:{300 if look == 'minimal' else 700};line-height:1.1'>{nm}</div><div style='font-size:7px;color:#64748b;"
                 f"margin-top:6px'>{sub}</div></div>")
        bg = "#fff"
    elif look == "corner":
        inner = (f"<div style='position:absolute;right:0;top:0;width:30%;height:52%;background:linear-gradient(225deg,{d} 0 50%,"
                 f"transparent 50%)'></div><div style='position:absolute;left:8%;bottom:16%;width:14%;height:3px;background:{a}'></div>"
                 f"<div style='position:absolute;left:8%;right:30%;top:34%;color:{d}'><div style='font-size:15px;"
                 f"font-weight:700;line-height:1.1'>{nm}</div><div style='font-size:7px;color:#64748b;margin-top:5px'>{sub}</div></div>")
        bg = "#fff"
    else:
        bg = (f"linear-gradient(135deg,{d},{a})" if look == "hero" else "#0b1220" if look == "dark" else d)
        inner = (f"<div style='position:absolute;right:-12%;top:-30%;width:58%;height:110%;border-radius:50%;background:{a};opacity:.35'></div>"
                 if look not in ("hero",) else "") + (
            f"<div style='position:absolute;left:8%;bottom:16%;width:14%;height:3px;background:{a if look != 'hero' else '#fff'}'></div>"
            f"<div style='position:absolute;left:8%;right:10%;top:28%;color:#fff'><div style='font-size:7px;opacity:.8;letter-spacing:.1em'>2026</div>"
            f"<div style='font-size:16px;font-weight:700;line-height:1.1;margin-top:3px'>{nm}</div><div style='font-size:7px;"
            f"opacity:.75;margin-top:5px'>{sub}</div></div>")
    return ("<!doctype html><html><head><meta charset='utf-8'><style>html,body{margin:0;height:100%;overflow:hidden;"
            "font-family:'Segoe UI',Arial,sans-serif;background:#e9ebef}.s{position:absolute;left:10%;right:10%;aspect-ratio:16/9;"
            "border-radius:6px}</style></head><body>"
            "<div class='s' style='top:8%;background:#bfc3c9;transform:scale(.86)'></div>"
            "<div class='s' style='top:13%;background:#9ea3aa;transform:scale(.93)'></div>"
            f"<div class='s' style='top:19%;background:{bg};box-shadow:0 8px 22px #0003;overflow:hidden'>{inner}</div></body></html>")
