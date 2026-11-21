"""Spreadsheet templates as real designs, not only colours: each template has a sheet layout.

dashboard - title band, KPI boxes (live =SUM / =AVERAGE formulas), the table, a line chart
budget    - title band, summary boxes, the table with a bold total row (=SUM), a column chart
pipeline  - title band, big KPI numbers, the table, a bar chart, stage colours
tracker   - title band, status colours, data bars on percent columns, a weekly Gantt (from start / end dates)
calendar  - title band, the table, plus a year calendar sheet (12 months) with the table's dates marked
scorecard - title band, the table with target / actual traffic lights (green / amber / red)
inventory - title band, the table, low-stock rows in red (stock <= reorder level)

The workbook is first written by docs_gen._xlsx (rows, number formats, header look); apply() frames it."""
from __future__ import annotations

import calendar
import datetime as dt
import re

LAYOUT_OF = {"analytics_dashboard": "dashboard", "financial_budget": "budget", "personal_budget": "budget",
             "operating_calendar": "calendar", "project_tracker": "tracker", "sales_pipeline": "pipeline",
             "kpi_scorecard": "scorecard", "inventory": "inventory"}
MONTHS = {"tr": ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"],
          "en": list(calendar.month_name)[1:]}
DAYS = {"tr": ["Pt", "Sa", "Ça", "Pe", "Cu", "Ct", "Pz"], "en": ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]}
LABEL = {"total": {"tr": "Toplam", "en": "Total"}, "avg": {"tr": "Ortalama", "en": "Average"},
         "calendar": {"tr": "Takvim", "en": "Calendar"}, "gantt": {"tr": "Haftalık plan", "en": "Weekly plan"}}


def _lbl(k: str, lang: str) -> str:
    return LABEL[k].get(lang) or LABEL[k]["en"]


def _num_cols(ws, header_row: int, last_row: int) -> list[int]:
    out = []
    for c in range(1, ws.max_column + 1):
        vals = [ws.cell(row=r, column=c).value for r in range(header_row + 1, last_row + 1)]
        nums = [v for v in vals if isinstance(v, (int, float)) and not isinstance(v, bool)]
        if vals and len(nums) >= max(1, len([v for v in vals if v not in (None, "")]) * 0.7):
            out.append(c)
    return out


def _date_of(v):
    if isinstance(v, dt.datetime):
        return v.date()
    if isinstance(v, dt.date):
        return v
    if isinstance(v, str):
        for f in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%Y/%m/%d"):
            try:
                return dt.datetime.strptime(v.strip()[:10], f).date()
            except ValueError:
                continue
    return None


def apply(wb, spec: dict, title: str, colors: tuple[str, str, str], lang: str = "tr") -> None:
    from openpyxl.chart import BarChart, LineChart, Reference
    from openpyxl.formatting.rule import CellIsRule, DataBarRule, FormulaRule
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter as L

    layout = spec.get("xlsx_layout") or LAYOUT_OF.get(spec.get("id", ""), "")
    if not layout or not wb.worksheets:
        return
    accent, dark, tint = colors
    band = "0B1220" if spec.get("cover") == "dark" else dark
    font_name = spec.get("font_family") or "Calibri"
    ws = wb.worksheets[0]
    if ws.max_row < 2:
        return
    ncols = max(2, ws.max_column)
    rows_before = ws.max_row
    kpi = layout in ("dashboard", "budget", "pipeline")
    top = 6 if kpi else 3  # rows above the table: title, subtitle, (KPI boxes)
    ws.insert_rows(1, top)
    hdr, last = top + 1, top + rows_before
    # title band and subtitle
    width = max(ncols, 6)
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=width)
    t = ws.cell(row=1, column=1, value=title)
    t.font = Font(name=font_name, size=17, bold=True, color="FFFFFF")
    t.alignment = Alignment(vertical="center", indent=1)
    for c in range(1, width + 1):
        ws.cell(row=1, column=c).fill = PatternFill("solid", fgColor=band)
    ws.row_dimensions[1].height = 34
    sub = ws.cell(row=2, column=1, value=f"{(spec.get('name') or {}).get(lang) or (spec.get('name') or {}).get('en', '')} · "
                                         f"{dt.date.today().strftime('%d.%m.%Y')}")
    sub.font = Font(name=font_name, size=9, italic=True, color="64748B")
    # A total row the model wrote itself ("Toplam", "Total") stays as it is but is left out of every formula range
    # (a KPI box counted it twice: 39,000 visitors instead of 19,500), and no second total row is added.
    own_total = bool(re.match(r"\s*(genel\s+)?(toplam|total|sum|grand total|ara toplam|subtotal)\b",
                              str(ws.cell(row=last, column=1).value or ""), re.I))
    if own_total:
        last -= 1
    nums = _num_cols(ws, hdr, last)
    labels = [ws.cell(row=hdr, column=c).value for c in nums]
    # KPI boxes: live formulas over the table (they follow edits)
    if kpi and nums:
        thin = Side(style="thin", color="D9E2EC")
        for i, c in enumerate(nums[:4]):
            col = 1 + i * 2
            ws.merge_cells(start_row=4, start_column=col, end_row=4, end_column=col + 1)
            ws.merge_cells(start_row=5, start_column=col, end_row=5, end_column=col + 1)
            lab = ws.cell(row=4, column=col, value=str(labels[i] or "").upper()[:28])
            lab.font = Font(name=font_name, size=8, bold=True, color="64748B")
            fn = "AVERAGE" if re.search(r"%|oran|rate|ratio|olas|prob|pct|yüzde", str(labels[i] or ""), re.I) else "SUM"
            v = ws.cell(row=5, column=col, value=f"={fn}({L(c)}{hdr + 1}:{L(c)}{last})")
            v.font = Font(name=font_name, size=18, bold=True, color=accent)
            v.number_format = ws.cell(row=hdr + 1, column=c).number_format or "#,##0"
            for r in (4, 5):
                for cc in (col, col + 1):
                    cell = ws.cell(row=r, column=cc)
                    cell.fill = PatternFill("solid", fgColor="111A2E" if band == "0B1220" else tint)
                    cell.border = Border(top=Side(style="thick", color=accent) if r == 4 else thin,
                                         bottom=thin, left=thin if cc == col else None, right=thin if cc == col + 1 else None)
            if band == "0B1220":
                v.font = Font(name=font_name, size=18, bold=True, color="FFFFFF")
        ws.row_dimensions[5].height = 30
    # total row (budget)
    if layout == "budget" and nums and not own_total:
        tr = last + 1
        ws.cell(row=tr, column=1, value=_lbl("total", lang)).font = Font(name=font_name, bold=True)
        for c in nums:
            cell = ws.cell(row=tr, column=c, value=f"=SUM({L(c)}{hdr + 1}:{L(c)}{last})")
            cell.font = Font(name=font_name, bold=True)
            cell.number_format = ws.cell(row=hdr + 1, column=c).number_format or "#,##0"
        for c in range(1, ncols + 1):
            ws.cell(row=tr, column=c).border = Border(top=Side(style="medium", color=dark), bottom=Side(style="double", color=dark))
    # charts
    if layout in ("dashboard", "budget", "pipeline") and nums:
        ch = LineChart() if layout == "dashboard" else BarChart()
        if layout == "pipeline":
            ch.type = "bar"
        ch.title = str(labels[0] or title)[:40]
        ch.height, ch.width = 7.5, 15
        data = Reference(ws, min_col=nums[0], max_col=nums[min(1, len(nums) - 1)] if layout == "dashboard" else nums[0],
                         min_row=hdr, max_row=last)
        ch.add_data(data, titles_from_data=True)
        cats = Reference(ws, min_col=1, min_row=hdr + 1, max_row=last)
        ch.set_categories(cats)
        try:
            for s in ch.series:
                s.graphicalProperties.line.solidFill = accent
                s.graphicalProperties.solidFill = accent
        except AttributeError:
            pass
        ch.legend = None if len(ch.series) < 2 else ch.legend
        ws.add_chart(ch, f"{L(ncols + 2)}{hdr}")
    # status colours (tracker, pipeline, inventory, scorecard)
    rng = f"A{hdr + 1}:{L(ncols)}{last}"
    if layout in ("tracker", "pipeline"):
        for words, fill in ((r"tamam|bitti|done|complete|won|kazan", "DCFCE7"), (r"devam|progress|açık|open|negotiat|teklif", "FEF3C7"),
                            (r"risk|gecik|late|blocked|lost|kaybed|iptal", "FEE2E2")):
            for c in range(1, ncols + 1):
                head = str(ws.cell(row=hdr, column=c).value or "")
                if re.search(r"durum|status|aşama|stage", head, re.I):
                    for w in words.split("|"):
                        ws.conditional_formatting.add(
                            f"{L(c)}{hdr + 1}:{L(c)}{last}",
                            FormulaRule(formula=[f'ISNUMBER(SEARCH("{w}",{L(c)}{hdr + 1}))'], fill=PatternFill("solid", fgColor=fill)))
    if layout in ("tracker", "scorecard", "dashboard"):
        for c in nums:
            head = str(ws.cell(row=hdr, column=c).value or "")
            if re.search(r"%|ilerleme|progress|tamamlan|oran|rate|pct|yüzde", head, re.I):
                ws.conditional_formatting.add(f"{L(c)}{hdr + 1}:{L(c)}{last}",
                                              DataBarRule(start_type="num", start_value=0, end_type="max", color=accent))
    if layout == "scorecard":  # actual vs target: green / amber / red
        heads = {str(ws.cell(row=hdr, column=c).value or "").lower(): c for c in range(1, ncols + 1)}
        tc = next((c for h, c in heads.items() if re.search(r"hedef|target|plan", h)), None)
        ac = next((c for h, c in heads.items() if re.search(r"gerçek|actual|sonuç|result|değer|value", h)), None)
        if tc and ac:
            a, b = f"${L(ac)}{hdr + 1}", f"${L(tc)}{hdr + 1}"
            for f, fill in ((f"{a}>={b}", "DCFCE7"), (f"AND({a}<{b},{a}>={b}*0.9)", "FEF3C7"), (f"{a}<{b}*0.9", "FEE2E2")):
                ws.conditional_formatting.add(rng, FormulaRule(formula=[f], fill=PatternFill("solid", fgColor=fill)))
    if layout == "inventory":
        heads = {str(ws.cell(row=hdr, column=c).value or "").lower(): c for c in range(1, ncols + 1)}
        sc = next((c for h, c in heads.items() if re.search(r"stok|stock|adet|qty|miktar", h)), None)
        rc = next((c for h, c in heads.items() if re.search(r"kritik|reorder|min|eşik", h)), None)
        if sc and rc:
            ws.conditional_formatting.add(rng, FormulaRule(formula=[f"${L(sc)}{hdr + 1}<=${L(rc)}{hdr + 1}"],
                                                           fill=PatternFill("solid", fgColor="FEE2E2"),
                                                           font=Font(color="991B1B", bold=True)))
    # weekly Gantt (tracker): bars from a start and an end date column
    if layout == "tracker":
        dcols = [c for c in range(1, ncols + 1) if sum(1 for r in range(hdr + 1, last + 1)
                                                         if _date_of(ws.cell(row=r, column=c).value)) >= max(1, (last - hdr) // 2)]
        if len(dcols) >= 2:
            sdates = [_date_of(ws.cell(row=r, column=dcols[0]).value) for r in range(hdr + 1, last + 1)]
            edates = [_date_of(ws.cell(row=r, column=dcols[1]).value) for r in range(hdr + 1, last + 1)]
            known = [d for d in sdates + edates if d]
            start = min(known) - dt.timedelta(days=min(known).weekday())
            weeks = min(26, max(1, ((max(known) - start).days // 7) + 1))
            g0 = ncols + 2
            ws.cell(row=hdr - 1, column=g0, value=_lbl("gantt", lang)).font = Font(name=font_name, bold=True, color=dark)
            for w in range(weeks):
                d0 = start + dt.timedelta(days=7 * w)
                h = ws.cell(row=hdr, column=g0 + w, value=d0.strftime("%d.%m"))
                h.font = Font(name=font_name, size=8, bold=True, color="FFFFFF")
                h.fill = PatternFill("solid", fgColor=dark)
                h.alignment = Alignment(horizontal="center", text_rotation=90)
                ws.column_dimensions[L(g0 + w)].width = 3.2
                for i, (a, b) in enumerate(zip(sdates, edates)):
                    if a and b and a <= d0 + dt.timedelta(days=6) and b >= d0:
                        ws.cell(row=hdr + 1 + i, column=g0 + w).fill = PatternFill("solid", fgColor=accent)
    # year calendar (calendar layout): 12 months, 3 across, the table's dates marked
    if layout == "calendar":
        marked = {}
        for r in range(hdr + 1, last + 1):
            for c in range(1, ncols + 1):
                if d := _date_of(ws.cell(row=r, column=c).value):
                    marked[d] = str(ws.cell(row=r, column=1).value or "")
        year = min(marked).year if marked else dt.date.today().year
        cs = wb.create_sheet(_lbl("calendar", lang), 0)
        cs.sheet_properties.tabColor = accent
        cs.merge_cells(start_row=1, start_column=1, end_row=1, end_column=23)
        h = cs.cell(row=1, column=1, value=f"{title} · {year}")
        h.font = Font(name=font_name, size=17, bold=True, color="FFFFFF")
        for c in range(1, 24):
            cs.cell(row=1, column=c).fill = PatternFill("solid", fgColor=accent)
            cs.column_dimensions[L(c)].width = 4.2
        cs.row_dimensions[1].height = 32
        for m in range(1, 13):
            r0 = 3 + ((m - 1) // 3) * 9
            c0 = 1 + ((m - 1) % 3) * 8
            cs.merge_cells(start_row=r0, start_column=c0, end_row=r0, end_column=c0 + 6)
            mh = cs.cell(row=r0, column=c0, value=MONTHS.get(lang, MONTHS["en"])[m - 1])
            mh.font = Font(name=font_name, bold=True, color="FFFFFF")
            mh.alignment = Alignment(horizontal="center")
            for k in range(7):
                cs.cell(row=r0, column=c0 + k).fill = PatternFill("solid", fgColor=dark)
                d = cs.cell(row=r0 + 1, column=c0 + k, value=DAYS.get(lang, DAYS["en"])[k])
                d.font = Font(name=font_name, size=8, bold=True, color=accent)
                d.alignment = Alignment(horizontal="center")
            for w, week in enumerate(calendar.monthcalendar(year, m)):
                for k, day in enumerate(week):
                    if day:
                        cell = cs.cell(row=r0 + 2 + w, column=c0 + k, value=day)
                        cell.alignment = Alignment(horizontal="center")
                        cell.font = Font(name=font_name, size=9, color="94A3B8" if k >= 5 else "1F2933")
                        if dt.date(year, m, day) in marked:
                            cell.fill = PatternFill("solid", fgColor=accent)
                            cell.font = Font(name=font_name, size=9, bold=True, color="FFFFFF")
    ws.freeze_panes = f"A{hdr + 1}"
    if ws.auto_filter.ref:
        ws.auto_filter.ref = f"A{hdr}:{L(ncols)}{last}"
