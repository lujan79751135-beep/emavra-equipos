"""Lógica pura (sin Streamlit) de la programación de equipo pesado EMAVRA."""
from datetime import date, timedelta
from html import escape
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

HORARIOS = ["7:30", "10:30", "13:00", "15:00"]
DIAS = ["LUNES", "MARTES", "MIÉRCOLES", "JUEVES", "VIERNES", "SÁBADO"]
ORDEN_TIPOS = ["Retroexcavadora", "Volqueta", "Minicargador"]
ICONOS = {"Retroexcavadora": "🚜", "Volqueta": "🚚", "Minicargador": "🏗️"}
PALETA = {
    "Retroexcavadora": ["#F5B700", "#F28C28", "#C98B00", "#FFD166"],
    "Volqueta": ["#2563EB", "#0891B2", "#16A34A", "#7C3AED"],
    "Minicargador": ["#DC2626", "#DB2777", "#EA580C", "#9333EA"],
}
COLOR_DEFECTO = ["#475569", "#0F766E", "#B45309", "#6D28D9"]
SLOTS_SEMANA = len(DIAS) * len(HORARIOS)  # 24 por equipo


def lunes_de(d: date) -> date:
    return d - timedelta(days=d.weekday())


def fechas_semana(lunes: date) -> list:
    return [lunes + timedelta(days=i) for i in range(len(DIAS))]


def en_uso(unidad) -> bool:
    u = (unidad or "").strip().lower()
    return u != "" and u != "disponible"


def indexar(filas) -> dict:
    return {(f["fecha"], f["codigo"], f["horario"]): f for f in filas}


def tipos_presentes(equipos) -> list:
    extras = sorted({e["tipo"] for e in equipos} - set(ORDEN_TIPOS))
    return [t for t in ORDEN_TIPOS + extras if any(e["tipo"] == t for e in equipos)]


def activos(equipos) -> list:
    return [e for e in equipos if e.get("activo", True)]


def usa(idx, fecha, codigo, horario) -> bool:
    fila = idx.get((fecha.isoformat(), codigo, horario))
    return en_uso(fila.get("unidad")) if fila else False


def usos_equipo(idx, fechas, codigo) -> int:
    return sum(usa(idx, f, codigo, h) for f in fechas for h in HORARIOS)


def resumen_semana(equipos, idx, lunes) -> dict:
    """{tipo: (usados, capacidad)} y total."""
    fechas = fechas_semana(lunes)
    out, tu, tc = {}, 0, 0
    for tipo in tipos_presentes(activos(equipos)):
        eqs = [e for e in activos(equipos) if e["tipo"] == tipo]
        u = sum(usos_equipo(idx, fechas, e["codigo"]) for e in eqs)
        c = len(eqs) * SLOTS_SEMANA
        out[tipo] = (u, c)
        tu, tc = tu + u, tc + c
    out["TOTAL"] = (tu, tc)
    return out


def resumen_global(equipos, filas_todas) -> list:
    """Una fila por semana con datos: [{semana, inicio, usos_por_tipo, usos, capacidad, pct}]"""
    tipo_de = {e["codigo"]: e["tipo"] for e in equipos}
    cap_tipo = {}
    for e in activos(equipos):
        cap_tipo[e["tipo"]] = cap_tipo.get(e["tipo"], 0) + SLOTS_SEMANA
    cap_total = sum(cap_tipo.values())
    semanas = {}
    for f in filas_todas:
        if not en_uso(f.get("unidad")):
            continue
        l = lunes_de(date.fromisoformat(f["fecha"]))
        t = tipo_de.get(f["codigo"])
        if t is None:
            continue
        s = semanas.setdefault(l, {})
        s[t] = s.get(t, 0) + 1
    res = []
    for l in sorted(semanas):
        usos = sum(semanas[l].values())
        res.append({
            "inicio": l,
            "fin": l + timedelta(days=5),
            "por_tipo": semanas[l],
            "usos": usos,
            "capacidad": cap_total,
            "pct": usos / cap_total if cap_total else 0.0,
        })
    for i, r in enumerate(res, 1):
        r["semana"] = i
    return res


def _color(tipo, i):
    return PALETA.get(tipo, COLOR_DEFECTO)[i % 4]


CSS = """
<style>
.panel{border-collapse:collapse;font-size:12px;width:100%;min-width:1100px}
.panel th,.panel td{border:1px solid #d1d5db;padding:3px 4px;text-align:center}
.panel th{background:#1F3A5F;color:#fff}
.panel td.cod{font-weight:700;text-align:left;white-space:nowrap}
.panel td.op{text-align:left;white-space:nowrap}
.panel tr.grupo td{background:#E8EEF7;font-weight:700;text-align:left}
.panel tr.sub td{background:#F3F4F6;font-weight:600}
.panel tr.tot td{background:#1F3A5F;color:#fff;font-weight:700}
.panel td.libre{background:#EEF0F3;color:#9CA3AF}
.panel td.libre .ic{opacity:.35;filter:grayscale(1)}
.panel td.uso{color:#111;font-weight:700;border:2px solid #111}
.panel .et{display:block;font-size:9px;letter-spacing:.3px}
</style>
"""


def panel_html(equipos, idx, lunes) -> str:
    fechas = fechas_semana(lunes)
    ncols = 2 + len(fechas) * len(HORARIOS) + 2
    h = [CSS, '<div style="overflow-x:auto"><table class="panel">']
    h.append('<tr><th rowspan="2">Código</th><th rowspan="2">Operador</th>')
    for d, f in zip(DIAS, fechas):
        h.append(f'<th colspan="{len(HORARIOS)}">{d} {f:%d/%m}</th>')
    h.append('<th rowspan="2">Usos</th><th rowspan="2">%</th></tr><tr>')
    for _ in fechas:
        h.extend(f"<th>{hr}</th>" for hr in HORARIOS)
    h.append("</tr>")
    act = activos(equipos)
    tot_slot = [0] * (len(fechas) * len(HORARIOS))
    for tipo in tipos_presentes(act):
        eqs = [e for e in act if e["tipo"] == tipo]
        icono = ICONOS.get(tipo, "🔧")
        h.append(f'<tr class="grupo"><td colspan="{ncols}">{icono} {escape(tipo)} ({len(eqs)})</td></tr>')
        sub = [0] * len(tot_slot)
        for i, e in enumerate(eqs):
            color = _color(tipo, i)
            h.append(f'<tr><td class="cod" style="border-left:6px solid {color}">{escape(e["codigo"])}</td>'
                     f'<td class="op">{escape(e.get("operador") or "")}</td>')
            usos, k = 0, 0
            for f in fechas:
                for hr in HORARIOS:
                    fila = idx.get((f.isoformat(), e["codigo"], hr)) or {}
                    uso = en_uso(fila.get("unidad"))
                    tip = escape(" | ".join(x for x in (fila.get("unidad"), fila.get("actividad"), fila.get("tecnico")) if x))
                    if uso:
                        usos += 1
                        sub[k] += 1
                        h.append(f'<td class="uso" title="{tip}" style="background:{color}"><span class="ic">{icono}</span><span class="et">EN USO</span></td>')
                    else:
                        h.append(f'<td class="libre" title="{tip}"><span class="ic">{icono}</span><span class="et">LIBRE</span></td>')
                    k += 1
            h.append(f"<td><b>{usos}</b></td><td>{usos / SLOTS_SEMANA:.0%}</td></tr>")
        cap = len(eqs) * SLOTS_SEMANA
        su = sum(sub)
        h.append('<tr class="sub"><td colspan="2" style="text-align:left">Subtotal ' + escape(tipo) + f' ({len(eqs)})</td>'
                 + "".join(f"<td>{v}</td>" for v in sub) + f"<td>{su}</td><td>{su / cap:.0%}</td></tr>")
        tot_slot = [a + b for a, b in zip(tot_slot, sub)]
    tu, tc = sum(tot_slot), len(act) * SLOTS_SEMANA
    h.append(f'<tr class="tot"><td colspan="2" style="text-align:left">TOTAL PARQUE ({len(act)} EQ.)</td>'
             + "".join(f"<td>{v}</td>" for v in tot_slot)
             + f"<td>{tu}</td><td>{(tu / tc if tc else 0):.0%}</td></tr></table></div>")
    return "".join(h)


def exportar_semana_xlsx(equipos, idx, lunes) -> bytes:
    """Hoja 'Mezcla por Maquina' de la semana, lista para imprimir en 1 hoja carta."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Mezcla por Maquina"
    fechas = fechas_semana(lunes)
    borde = Border(*(Side(style="thin", color="999999"),) * 4)
    azul = PatternFill("solid", fgColor="1F3A5F")
    verde = PatternFill("solid", fgColor="D9F2E0")
    gris = PatternFill("solid", fgColor="F1F3F5")
    centro = Alignment(horizontal="center", vertical="center", wrap_text=True)
    izq = Alignment(horizontal="left", vertical="center", wrap_text=True)
    ult = 3 + len(fechas)

    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=ult)
    ws["A1"] = f"EMAVRA - CRONOGRAMA DE USO DE EQUIPO PESADO  |  {fechas[0]:%d/%m/%Y} al {fechas[-1]:%d/%m/%Y}"
    ws["A1"].font = Font(bold=True, size=12, color="FFFFFF")
    ws["A1"].fill = azul
    ws["A1"].alignment = centro
    ws.row_dimensions[1].height = 22

    for c, t in enumerate(["Equipo", "Operador", "Horario"], 1):
        ws.cell(2, c, t)
    for i, (d, f) in enumerate(zip(DIAS, fechas)):
        ws.cell(2, 4 + i, f"{d} {f:%d/%m}")
    for c in range(1, ult + 1):
        x = ws.cell(2, c)
        x.font, x.fill, x.alignment, x.border = Font(bold=True, size=9, color="FFFFFF"), azul, centro, borde

    fila = 3
    for tipo in tipos_presentes(activos(equipos)):
        for e in [q for q in activos(equipos) if q["tipo"] == tipo]:
            ini = fila
            for hr in HORARIOS:
                ws.cell(fila, 3, hr)
                for i, f in enumerate(fechas):
                    r = idx.get((f.isoformat(), e["codigo"], hr)) or {}
                    partes = [r.get("unidad") or "", r.get("actividad") or ""]
                    txt = "\n".join(p for p in partes if p)
                    if r.get("tecnico"):
                        txt += f"\n({r['tecnico']})"
                    c = ws.cell(fila, 4 + i, txt)
                    c.fill = verde if en_uso(r.get("unidad")) else gris
                    c.alignment, c.font = izq, Font(size=8)
                for col in range(1, ult + 1):
                    ws.cell(fila, col).border = borde
                ws.cell(fila, 3).alignment = centro
                ws.cell(fila, 3).font = Font(size=8, bold=True)
                ws.row_dimensions[fila].height = 34
                fila += 1
            ws.merge_cells(start_row=ini, start_column=1, end_row=fila - 1, end_column=1)
            ws.merge_cells(start_row=ini, start_column=2, end_row=fila - 1, end_column=2)
            ws.cell(ini, 1, e["codigo"]).font = Font(bold=True, size=10)
            ws.cell(ini, 2, e.get("operador") or "").font = Font(size=8)
            ws.cell(ini, 1).alignment = ws.cell(ini, 2).alignment = centro

    ws.column_dimensions["A"].width = 8
    ws.column_dimensions["B"].width = 14
    ws.column_dimensions["C"].width = 7
    for i in range(len(fechas)):
        ws.column_dimensions[chr(ord("D") + i)].width = 23
    ws.freeze_panes = "D3"

    ws.print_area = f"A1:{chr(ord('A') + ult - 1)}{fila - 1}"
    ws.page_setup.paperSize = ws.PAPERSIZE_LETTER
    ws.page_setup.orientation = "portrait"
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 1
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_margins.left = ws.page_margins.right = 0.4
    ws.page_margins.top = ws.page_margins.bottom = 0.4
    ws.print_options.horizontalCentered = True
    ws.sheet_view.showGridLines = False

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
