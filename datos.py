"""Acceso a Supabase (base de datos gratuita)."""
from datetime import datetime, timezone

import streamlit as st
from supabase import create_client

PAGINA = 1000  # Supabase devuelve máx. 1000 filas por consulta


@st.cache_resource
def cliente():
    s = st.secrets["supabase"]
    return create_client(s["url"], s["key"])


def _todo(consulta):
    filas, i = [], 0
    while True:
        r = consulta().range(i, i + PAGINA - 1).execute().data
        filas += r
        if len(r) < PAGINA:
            return filas
        i += PAGINA


@st.cache_data(ttl=15, show_spinner=False)
def equipos():
    return _todo(lambda: cliente().table("equipos").select("*").order("orden").order("codigo"))


@st.cache_data(ttl=15, show_spinner=False)
def catalogo(tipo):
    r = _todo(lambda: cliente().table("catalogos").select("valor").eq("tipo", tipo).order("valor"))
    return [x["valor"] for x in r]


@st.cache_data(ttl=10, show_spinner=False)
def asignaciones_semana(desde, hasta):
    return _todo(lambda: cliente().table("asignaciones").select("*").gte("fecha", desde).lte("fecha", hasta).order("fecha"))


@st.cache_data(ttl=30, show_spinner=False)
def asignaciones_todas():
    return _todo(lambda: cliente().table("asignaciones").select("fecha,codigo,horario,unidad").order("fecha").order("codigo").order("horario"))


def guardar_asignaciones(filas, usuario):
    ahora = datetime.now(timezone.utc).isoformat()
    for f in filas:
        f["actualizado_por"], f["actualizado_en"] = usuario, ahora
    cliente().table("asignaciones").upsert(filas, on_conflict="fecha,codigo,horario").execute()
    st.cache_data.clear()


def guardar_equipos(filas, codigos_borrados):
    c = cliente().table("equipos")
    if filas:
        c.upsert(filas, on_conflict="codigo").execute()
    for cod in codigos_borrados:
        cliente().table("equipos").delete().eq("codigo", cod).execute()
    st.cache_data.clear()


def guardar_catalogo(tipo, valores):
    cliente().table("catalogos").delete().eq("tipo", tipo).execute()
    if valores:
        cliente().table("catalogos").insert([{"tipo": tipo, "valor": v} for v in valores]).execute()
    st.cache_data.clear()
