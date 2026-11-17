import hmac
from datetime import date

import pandas as pd
import streamlit as st

import datos
import logica as L

st.set_page_config(page_title="EMAVRA - Equipo Pesado", page_icon="🚜", layout="wide")


# ---------- Acceso ----------
def login() -> bool:
    if st.session_state.get("user"):
        return True
    st.title("🚜 EMAVRA - Programación de Equipo Pesado")
    with st.form("login"):
        u = st.text_input("Usuario").strip()
        p = st.text_input("Contraseña", type="password")
        if st.form_submit_button("Ingresar"):
            usuarios = st.secrets["usuarios"]
            if u in usuarios and hmac.compare_digest(str(usuarios[u]), p):
                st.session_state["user"] = u
                st.rerun()
            st.error("Usuario o contraseña incorrectos")
    return False


if not login():
    st.stop()

usuario = st.session_state["user"]
es_admin = usuario in list(st.secrets.get("admins", []))
equipos = datos.equipos()
unidades = datos.catalogo("unidad")
tecnicos = datos.catalogo("tecnico")

with st.sidebar:
    st.markdown(f"👤 **{usuario}**")
    paginas = ["📅 Programar", "📊 Panel semanal", "🖨️ Exportar / Imprimir"] + (["⚙️ Equipos y catálogos"] if es_admin else [])
    pagina = st.radio("Menú", paginas)
    if st.button("Cerrar sesión"):
        st.session_state.clear()
        st.rerun()


def semana_selector(clave):
    f = st.date_input("Semana (elige cualquier día de esa semana)", value=date.today(), key=clave, format="DD/MM/YYYY")
    return L.lunes_de(f)


def semana_idx(lunes):
    fechas = L.fechas_semana(lunes)
    return L.indexar(datos.asignaciones_semana(fechas[0].isoformat(), fechas[-1].isoformat()))


# ---------- 1. Programar ----------
def pagina_programar():
    st.header("📅 Programar equipos")
    lunes = semana_selector("sel_prog")
    fechas = L.fechas_semana(lunes)
    idx = semana_idx(lunes)
    act = L.activos(equipos)
    if not act:
        st.warning("No hay equipos activos. Pídele al administrador que los cargue.")
        return
    modo = st.radio("Cómo quieres llenar", ["Por día (todos los equipos)", "Por equipo (semana completa)"], horizontal=True)

    filas = []
    if modo.startswith("Por día"):
        dia = st.selectbox("Día", range(6), format_func=lambda i: f"{L.DIAS[i]} {fechas[i]:%d/%m/%Y}")
        clave = f"d{lunes}-{dia}"
        for e in act:
            for hr in L.HORARIOS:
                filas.append((fechas[dia], e, hr))
    else:
        cod = st.selectbox("Equipo", [e["codigo"] for e in act])
        e = next(x for x in act if x["codigo"] == cod)
        clave = f"e{lunes}-{cod}"
        for i, f in enumerate(fechas):
            for hr in L.HORARIOS:
                filas.append((f, e, hr))

    base = []
    for f, e, hr in filas:
        r = idx.get((f.isoformat(), e["codigo"], hr)) or {}
        base.append({
            "Equipo": e["codigo"], "Operador": e.get("operador") or "",
            "Día": f"{L.DIAS[f.weekday()]} {f:%d/%m}", "Horario": hr,
            "Unidad": r.get("unidad") or None, "Actividad / Zona": r.get("actividad") or "",
            "Técnico Solicitante": r.get("tecnico") or None,
        })
    orig = pd.DataFrame(base)
    editado = st.data_editor(
        orig, key=clave, hide_index=True, width="stretch", height=min(38 * len(orig) + 40, 700),
        disabled=["Equipo", "Operador", "Día", "Horario"],
        column_config={
            "Unidad": st.column_config.SelectboxColumn(options=unidades),
            "Técnico Solicitante": st.column_config.SelectboxColumn(options=tecnicos),
            "Actividad / Zona": st.column_config.TextColumn(max_chars=200),
        },
    )
    st.caption("Si dos personas editan la misma casilla a la vez, queda lo último que se guardó.")
    if st.button("💾 Guardar cambios", type="primary"):
        a_guardar = []
        for i, (f, e, hr) in enumerate(filas):
            o, n = orig.iloc[i], editado.iloc[i]
            if any((o[c] or "") != (n[c] or "") for c in ["Unidad", "Actividad / Zona", "Técnico Solicitante"]):
                a_guardar.append({
                    "fecha": f.isoformat(), "codigo": e["codigo"], "horario": hr,
                    "unidad": n["Unidad"] or "", "actividad": (n["Actividad / Zona"] or "").strip(),
                    "tecnico": n["Técnico Solicitante"] or "",
                })
        if not a_guardar:
            st.info("No hay cambios para guardar.")
        else:
            try:
                datos.guardar_asignaciones(a_guardar, usuario)
                st.success(f"Guardado: {len(a_guardar)} casilla(s) actualizada(s).")
            except Exception as ex:
                st.error(f"No se pudo guardar: {ex}")


# ---------- 2. Panel ----------
def pagina_panel():
    st.header("📊 Panel semanal")
    lunes = semana_selector("sel_panel")
    idx = semana_idx(lunes)
    st.subheader(f"Semana del {lunes:%d/%m/%Y} al {L.fechas_semana(lunes)[-1]:%d/%m/%Y}")
    res = L.resumen_semana(equipos, idx, lunes)
    cols = st.columns(len(res))
    for c, (k, (u, cap)) in zip(cols, res.items()):
        c.metric(k if k != "TOTAL" else "Todo el parque", f"{(u / cap if cap else 0):.0%}", f"{u} de {cap} horarios", delta_color="off")
    st.markdown(L.panel_html(equipos, idx, lunes), unsafe_allow_html=True)

    st.divider()
    st.subheader("Resumen general de todas las semanas")
    glob = L.resumen_global(equipos, datos.asignaciones_todas())
    if not glob:
        st.info("Todavía no hay semanas programadas.")
        return
    tipos = L.tipos_presentes(L.activos(equipos))
    df = pd.DataFrame([{
        "Semana": f"Semana {g['semana']}: {g['inicio']:%d/%m/%Y} al {g['fin']:%d/%m/%Y}",
        **{t: g["por_tipo"].get(t, 0) for t in tipos},
        "Usos totales": g["usos"], "% uso": g["pct"],
    } for g in glob])
    st.dataframe(df, hide_index=True, width="stretch",
                 column_config={"% uso": st.column_config.ProgressColumn(format="percent", min_value=0, max_value=1)})
    mayor, menor = max(glob, key=lambda g: g["usos"]), min(glob, key=lambda g: g["usos"])
    a, b = st.columns(2)
    a.metric("📈 Semana de mayor uso", f"Semana {mayor['semana']}", f"{mayor['pct']:.0%}", delta_color="off")
    b.metric("📉 Semana de menor uso", f"Semana {menor['semana']}", f"{menor['pct']:.0%}", delta_color="off")
    st.caption("Las semanas se numeran desde la primera que tiene datos. Cuenta como 'en uso' toda casilla con una Unidad distinta de 'Disponible'.")


# ---------- 3. Exportar ----------
def pagina_exportar():
    st.header("🖨️ Exportar / Imprimir")
    lunes = semana_selector("sel_exp")
    idx = semana_idx(lunes)
    st.download_button(
        "⬇️ Descargar 'Mezcla por Maquina' (Excel, 1 hoja carta)",
        L.exportar_semana_xlsx(equipos, idx, lunes),
        file_name=f"Mezcla_por_Maquina_{lunes:%Y-%m-%d}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", type="primary",
    )
    st.caption("El archivo ya sale configurado: hoja carta vertical, ajustada a 1 página, márgenes de 0,4\", sin cuadrícula.")
    if es_admin:
        st.divider()
        st.subheader("Respaldo completo (solo administrador)")
        todo = datos.asignaciones_semana("2000-01-01", "2100-01-01")
        df = pd.DataFrame(todo)
        from io import BytesIO
        buf = BytesIO()
        df.to_excel(buf, index=False, sheet_name="Asignaciones")
        st.download_button("⬇️ Descargar todos los datos", buf.getvalue(),
                           file_name=f"Respaldo_EMAVRA_{date.today():%Y-%m-%d}.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        st.caption("Descarga este respaldo cada semana: es tu copia de seguridad.")


# ---------- 4. Admin ----------
def pagina_admin():
    st.header("⚙️ Equipos y catálogos")
    st.subheader("Equipos")
    df = pd.DataFrame(equipos or [], columns=["codigo", "tipo", "operador", "orden", "activo"])
    ed = st.data_editor(
        df, num_rows="dynamic", hide_index=True, width="stretch", key="ed_equipos",
        column_config={
            "tipo": st.column_config.SelectboxColumn(options=L.ORDEN_TIPOS, required=True),
            "codigo": st.column_config.TextColumn(required=True),
            "activo": st.column_config.CheckboxColumn(default=True),
            "orden": st.column_config.NumberColumn(step=1, default=0),
        },
    )
    st.caption("Si borras un equipo, también se borra su historial. Para dejarlo de usar sin perder datos, desmarca 'activo'.")
    if st.button("💾 Guardar equipos"):
        nuevos = ed.dropna(subset=["codigo", "tipo"]).copy()
        nuevos["codigo"] = nuevos["codigo"].astype(str).str.strip()
        nuevos["operador"] = nuevos["operador"].fillna("")
        nuevos["orden"] = nuevos["orden"].fillna(0).astype(int)
        nuevos["activo"] = nuevos["activo"].fillna(True).astype(bool)
        borrados = set(df["codigo"]) - set(nuevos["codigo"])
        datos.guardar_equipos(nuevos.to_dict("records"), borrados)
        st.success("Equipos guardados.")
        st.rerun()

    for tipo, titulo, actuales in [("unidad", "Unidades (lista desplegable)", unidades), ("tecnico", "Técnicos solicitantes", tecnicos)]:
        st.subheader(titulo)
        e = st.data_editor(pd.DataFrame({"valor": actuales}), num_rows="dynamic", hide_index=True, key=f"ed_{tipo}")
        if st.button(f"💾 Guardar {titulo.split(' (')[0].lower()}", key=f"b_{tipo}"):
            vals = sorted({str(v).strip() for v in e["valor"].dropna() if str(v).strip()})
            datos.guardar_catalogo(tipo, vals)
            st.success("Guardado.")
            st.rerun()


{"📅 Programar": pagina_programar, "📊 Panel semanal": pagina_panel,
 "🖨️ Exportar / Imprimir": pagina_exportar, "⚙️ Equipos y catálogos": pagina_admin}[pagina]()
