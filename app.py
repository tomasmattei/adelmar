import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import gspread
from google.oauth2.service_account import Credentials
import json
from datetime import timedelta
import warnings
warnings.filterwarnings("ignore")

st.set_page_config(
    page_title="Tablero Operativo - Flota",
    page_icon="🚛",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ─── Custom CSS ───────────────────────────────────────────────────────────────
st.markdown("""
<style>
    .main-header {
        font-size: 2rem;
        font-weight: 700;
        color: #1a1a2e;
        margin-bottom: 0.2rem;
    }
    .sub-header {
        color: #6c757d;
        font-size: 0.95rem;
        margin-bottom: 1.5rem;
    }
    .metric-card {
        background: #f8f9fa;
        border-left: 4px solid #0066cc;
        padding: 1rem;
        border-radius: 6px;
        margin-bottom: 0.5rem;
    }
    .metric-card.warning { border-left-color: #ff6b35; }
    .metric-card.success { border-left-color: #28a745; }
    .metric-card.danger  { border-left-color: #dc3545; }
    .stTabs [data-baseweb="tab-list"] { gap: 8px; }
    .stTabs [data-baseweb="tab"] {
        background: #f0f2f6;
        border-radius: 6px 6px 0 0;
        padding: 8px 20px;
        font-weight: 500;
    }
    .stTabs [aria-selected="true"] {
        background: #0066cc;
        color: white;
    }
    div[data-testid="stSidebarContent"] {
        background: #1a1a2e;
        color: white;
    }
    div[data-testid="stSidebarContent"] label { color: #ccc !important; }
    div[data-testid="stSidebarContent"] h1,
    div[data-testid="stSidebarContent"] h2,
    div[data-testid="stSidebarContent"] h3 { color: white !important; }
</style>
""", unsafe_allow_html=True)

# ─── Google Sheets connection ─────────────────────────────────────────────────
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

SHEET_TABS = {
    "cargas_descargas": "CargarDescargas",
    "incidencias": "Incidencias",
    "icm_ranking": "ICMRanking",
}

@st.cache_resource(show_spinner=False)
def get_gspread_client():
    creds_dict = st.secrets.get("gcp_service_account", None)
    if creds_dict is None:
        return None
    creds = Credentials.from_service_account_info(dict(creds_dict), scopes=SCOPES)
    return gspread.authorize(creds)


@st.cache_data(ttl=300, show_spinner=False)
def load_sheet(spreadsheet_url: str, tab_name: str) -> pd.DataFrame:
    client = get_gspread_client()
    if client is None:
        return pd.DataFrame()
    sh = client.open_by_url(spreadsheet_url)
    ws = sh.worksheet(tab_name)
    data = ws.get_all_records()
    return pd.DataFrame(data)


def load_all_data(spreadsheet_url: str):
    dfs = {}
    for key, tab in SHEET_TABS.items():
        try:
            dfs[key] = load_sheet(spreadsheet_url, tab)
        except Exception as e:
            dfs[key] = pd.DataFrame()
            st.sidebar.warning(f"⚠️ No se pudo leer '{tab}': {e}")
    return dfs


# ─── Data parsing helpers ─────────────────────────────────────────────────────
def parse_hhmm_to_minutes(series: pd.Series) -> pd.Series:
    """Convert 'X days HH:MM:SS' or 'HH:MM:SS' strings to total minutes."""
    def _conv(v):
        try:
            if pd.isna(v) or v == "":
                return np.nan
            v = str(v)
            days = 0
            if "days" in v:
                parts = v.split("days")
                days = int(parts[0].strip())
                v = parts[1].strip()
            if isinstance(v, str) and ":" in v:
                t = v.strip().split(":")
                h, m = int(t[0]), int(t[1])
                return days * 1440 + h * 60 + m
        except Exception:
            pass
        return np.nan
    return series.apply(_conv)


def minutes_to_hhmm(minutes):
    if pd.isna(minutes):
        return "N/A"
    h = int(minutes // 60)
    m = int(minutes % 60)
    return f"{h}h {m:02d}m"


def minutes_to_hm_format(minutes):
    """Convert minutes to H:MM format for heatmap display."""
    if pd.isna(minutes) or minutes == 0:
        return "0:00"
    h = int(minutes // 60)
    m = int(minutes % 60)
    return f"{h}:{m:02d}"


def prepare_cargas_descargas(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    date_cols = ["Entró", "Entró al dock", "Salió del dock"]
    for c in date_cols:
        if c in df.columns:
            df[c] = pd.to_datetime(df[c], errors="coerce")
    time_cols = ["Tiempo en cola (hs:mm)", "Tiempo en dock (hs:mm)", "Demora total (hs:mm)"]
    for c in time_cols:
        if c in df.columns:
            df[c + "_min"] = parse_hhmm_to_minutes(df[c])
    if "Entró" in df.columns:
        df["Dia"] = df["Entró"].dt.date
        df["DiaSemana"] = df["Entró"].dt.day_name()
        df["Hora"] = df["Entró"].dt.hour
    return df


def prepare_incidencias(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    if "Fecha del evento" in df.columns:
        df["Fecha del evento"] = pd.to_datetime(df["Fecha del evento"], errors="coerce")
        df["Dia"] = df["Fecha del evento"].dt.date
        df["Mes"] = df["Fecha del evento"].dt.to_period("M").astype(str)
    return df


# ─── Demo data (fallback when no Sheets connected) ────────────────────────────
@st.cache_data
def load_demo_data():
    """Load the uploaded Excel files as demo data."""
    import os
    base = "/mnt/user-data/uploads"
    f1 = os.path.join(base, "cargas-descargas_2026-04-23_a_2026-05-23.xlsx")
    f2 = os.path.join(base, "incidencias_2026-05-22.xlsx")
    f3 = os.path.join(base, "icm_ranking_2026-05-16_2026-05-22.xlsx")
    dfs = {}
    for key, path in [("cargas_descargas", f1), ("incidencias", f2), ("icm_ranking", f3)]:
        try:
            dfs[key] = pd.read_excel(path)
        except Exception:
            dfs[key] = pd.DataFrame()
    return dfs


# ─── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🚛 Tablero Flota")
    st.markdown("---")

    use_demo = st.toggle("🗂️ Usar datos de ejemplo", value=False)
    if not use_demo:
        DEFAULT_SHEET_URL = st.secrets.get("spreadsheet_url", "")

        spreadsheet_url = st.text_input(
            "URL de Google Sheets",
            value=DEFAULT_SHEET_URL,
            placeholder="https://docs.google.com/spreadsheets/d/...",
        )
        if spreadsheet_url:
            if st.button("🔄 Recargar datos"):
                st.cache_data.clear()
    else:
        spreadsheet_url = ""

    st.markdown("---")
    st.markdown("### ℹ️ Estructura requerida")
    st.markdown("""
    El Google Sheet debe tener **3 hojas**:
    - `CargarDescargas`
    - `Incidencias`
    - `ICMRanking`
    
    Con las mismas columnas que los archivos Excel de ejemplo.
    """)
    st.markdown("---")
    st.caption("v1.0 · Dashboard Operativo")


# ─── Load data ────────────────────────────────────────────────────────────────
if use_demo or not spreadsheet_url:
    raw = load_demo_data()
    if not use_demo:
        st.info("ℹ️ No se configuró una URL de Google Sheets. Mostrando datos de ejemplo.", icon="📊")
else:
    with st.spinner("Conectando con Google Sheets..."):
        raw = load_all_data(spreadsheet_url)

df_cd_raw = prepare_cargas_descargas(raw.get("cargas_descargas", pd.DataFrame()))
df_inc_raw = prepare_incidencias(raw.get("incidencias", pd.DataFrame()))
df_icm_raw = raw.get("icm_ranking", pd.DataFrame())

# ─── Header ──────────────────────────────────────────────────────────────────
st.markdown('<div class="main-header">🚛 Tablero Operativo de Flota</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">Monitoreo en tiempo real · Demoras · Incidencias · Kilómetros</div>', unsafe_allow_html=True)

# Global KPIs
col1, col2, col3, col4 = st.columns(4)
total_eventos = len(df_cd_raw)
total_inc = len(df_inc_raw)
total_unidades_icm = len(df_icm_raw)

avg_demora_min = df_cd_raw["Demora total (hs:mm)_min"].mean() if "Demora total (hs:mm)_min" in df_cd_raw.columns else 0
col1.metric("📦 Eventos Cargas/Descargas", f"{total_eventos:,}")
col2.metric("⚠️ Incidencias Registradas", f"{total_inc:,}")
col3.metric("🚗 Unidades en Ranking ICM", f"{total_unidades_icm:,}")
col4.metric("⏱️ Demora Promedio Total", minutes_to_hhmm(avg_demora_min))

st.markdown("---")

# ─── TABS ─────────────────────────────────────────────────────────────────────
tab1, tab2, tab3 = st.tabs([
    "🕐  Demoras Cargas & Descargas",
    "🔧  Incidencias",
    "📍  Km por Chofer / ICM",
])


# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 · DEMORAS CARGAS & DESCARGAS
# ══════════════════════════════════════════════════════════════════════════════
with tab1:

    if df_cd_raw.empty:
        st.warning("No hay datos de cargas/descargas disponibles.")
    else:
        df_cd = df_cd_raw.copy()

        # ── Filters ───────────────────────────────────────────────────────────
        fc1, fc2, fc3 = st.columns([2, 2, 2])
        with fc1:
            tipo_sel = st.multiselect(
                "Tipo de zona",
                options=sorted(df_cd["Tipo de zona"].dropna().unique()),
                default=sorted(df_cd["Tipo de zona"].dropna().unique()),
                key="tipo_zona",
            )
        with fc2:
            origen_sel = st.multiselect(
                "Origen",
                options=sorted(df_cd["Origen"].dropna().unique()),
                default=sorted(df_cd["Origen"].dropna().unique()),
                key="origen",
            )
        with fc3:
            estado_sel = st.multiselect(
                "Estado",
                options=sorted(df_cd["Estado"].dropna().unique()),
                default=["Completado"],
                key="estado_cd",
            )

        if tipo_sel:
            df_cd = df_cd[df_cd["Tipo de zona"].isin(tipo_sel)]
        if origen_sel:
            df_cd = df_cd[df_cd["Origen"].isin(origen_sel)]
        if estado_sel:
            df_cd = df_cd[df_cd["Estado"].isin(estado_sel)]

        df_cargas = df_cd[df_cd["Tipo de zona"] == "Carga"].copy()
        df_descargas = df_cd[df_cd["Tipo de zona"] == "Descarga"].copy()

        # ── Section A: CARGAS ─────────────────────────────────────────────────
        st.subheader("📦 Demoras en Cargas")
        if df_cargas.empty:
            st.info("No hay eventos de Carga con los filtros seleccionados.")
        else:
            kc1, kc2, kc3, kc4 = st.columns(4)
            kc1.metric("Total eventos", f"{len(df_cargas):,}")
            kc2.metric("Demora promedio", minutes_to_hhmm(df_cargas["Demora total (hs:mm)_min"].mean()))
            kc3.metric("Demora máxima", minutes_to_hhmm(df_cargas["Demora total (hs:mm)_min"].max()))
            kc4.metric("Tiempo en cola prom.", minutes_to_hhmm(df_cargas["Tiempo en cola (hs:mm)_min"].mean()))

            gc1, gc2 = st.columns(2)

            with gc1:
                # Demora promedio por día de la semana
                if "DiaSemana" in df_cargas.columns:
                    day_order = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
                    day_labels = {"Monday":"Lunes","Tuesday":"Martes","Wednesday":"Miércoles",
                                  "Thursday":"Jueves","Friday":"Viernes","Saturday":"Sábado","Sunday":"Domingo"}
                    g = df_cargas.groupby("DiaSemana")["Demora total (hs:mm)_min"].mean().reset_index()
                    g["DiaSemana"] = pd.Categorical(g["DiaSemana"], categories=day_order, ordered=True)
                    g = g.sort_values("DiaSemana")
                    g["Dia"] = g["DiaSemana"].map(day_labels)
                    fig = px.bar(g, x="Dia", y="Demora total (hs:mm)_min",
                                 title="Demora promedio por día (min) — Cargas",
                                 color="Demora total (hs:mm)_min",
                                 color_continuous_scale="Reds",
                                 labels={"Demora total (hs:mm)_min": "Minutos"})
                    fig.update_coloraxes(showscale=False)
                    fig.update_layout(height=320, margin=dict(t=40,b=20))
                    st.plotly_chart(fig, use_container_width=True)

            with gc2:
                # Demora promedio por hora
                if "Hora" in df_cargas.columns:
                    g = df_cargas.groupby("Hora")["Demora total (hs:mm)_min"].mean().reset_index()
                    fig = px.line(g, x="Hora", y="Demora total (hs:mm)_min",
                                  title="Demora promedio por hora del día — Cargas",
                                  markers=True,
                                  labels={"Demora total (hs:mm)_min": "Minutos", "Hora": "Hora del día"})
                    fig.update_traces(line_color="#0066cc")
                    fig.update_layout(height=320, margin=dict(t=40,b=20))
                    st.plotly_chart(fig, use_container_width=True)

            # Heatmap día x hora
            if "DiaSemana" in df_cargas.columns and "Hora" in df_cargas.columns:
                day_order = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
                day_labels_short = {"Monday":"Lun","Tuesday":"Mar","Wednesday":"Mié",
                                    "Thursday":"Jue","Friday":"Vie","Saturday":"Sáb","Sunday":"Dom"}
                pivot = df_cargas.groupby(["DiaSemana","Hora"])["Demora total (hs:mm)_min"].mean().unstack(fill_value=0)
                pivot = pivot.reindex([d for d in day_order if d in pivot.index])
                pivot.index = [day_labels_short.get(d, d) for d in pivot.index]
                # Convert minutes to HH:MM format for display
                pivot_display = pivot.map(minutes_to_hm_format)
                fig = px.imshow(pivot,
                                title="📊 Heatmap: Demora promedio (HH:MM) — Día × Hora · Cargas",
                                color_continuous_scale="YlOrRd",
                                labels={"color":"horas", "x":"Hora", "y":"Día"},
                                text_auto=False,
                                aspect="auto")
                # Add text annotations with HH:MM format
                fig.update_traces(text=pivot_display.values, texttemplate="%{text}", textfont={"size": 11})
                fig.update_layout(height=300, margin=dict(t=50,b=20))
                st.plotly_chart(fig, use_container_width=True)

            with st.expander("🔍 Top 20 unidades con mayor demora en Cargas"):
                if "Alias actual" in df_cargas.columns:
                    top = (df_cargas.groupby("Alias actual")["Demora total (hs:mm)_min"]
                           .agg(["mean","count"]).reset_index()
                           .rename(columns={"mean":"Demora prom (min)","count":"Eventos"})
                           .sort_values("Demora prom (min)", ascending=False).head(20))
                    top["Demora formateada"] = top["Demora prom (min)"].apply(minutes_to_hhmm)
                    st.dataframe(top[["Alias actual","Eventos","Demora formateada"]], use_container_width=True)

        st.markdown("---")

        # ── Section B: DESCARGAS ──────────────────────────────────────────────
        st.subheader("🔄 Demoras en Descargas")

        # Filter only Palmira origin for the planning impact
        palmira_keywords = ["palmira", "Palmira", "PALMIRA"]
        df_desc_palmira = df_descargas[
            df_descargas["Zona"].str.contains("almira", case=False, na=False) |
            df_descargas["Origen"].str.contains("almira", case=False, na=False)
        ] if not df_descargas.empty else pd.DataFrame()

        if df_descargas.empty:
            st.info("No hay eventos de Descarga con los filtros seleccionados.")
        else:
            kd1, kd2, kd3, kd4 = st.columns(4)
            kd1.metric("Total descargas", f"{len(df_descargas):,}")
            kd2.metric("Demora promedio", minutes_to_hhmm(df_descargas["Demora total (hs:mm)_min"].mean()))
            kd3.metric("Demora máxima", minutes_to_hhmm(df_descargas["Demora total (hs:mm)_min"].max()))
            kd4.metric("Tiempo en dock prom.", minutes_to_hhmm(df_descargas["Tiempo en dock (hs:mm)_min"].mean()))

            gd1, gd2 = st.columns(2)

            with gd1:
                if "DiaSemana" in df_descargas.columns:
                    day_order = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
                    day_labels = {"Monday":"Lunes","Tuesday":"Martes","Wednesday":"Miércoles",
                                  "Thursday":"Jueves","Friday":"Viernes","Saturday":"Sábado","Sunday":"Domingo"}
                    g = df_descargas.groupby("DiaSemana")["Demora total (hs:mm)_min"].mean().reset_index()
                    g["DiaSemana"] = pd.Categorical(g["DiaSemana"], categories=day_order, ordered=True)
                    g = g.sort_values("DiaSemana")
                    g["Dia"] = g["DiaSemana"].map(day_labels)
                    fig = px.bar(g, x="Dia", y="Demora total (hs:mm)_min",
                                 title="Demora promedio por día (min) — Descargas",
                                 color="Demora total (hs:mm)_min",
                                 color_continuous_scale="Blues",
                                 labels={"Demora total (hs:mm)_min": "Minutos"})
                    fig.update_coloraxes(showscale=False)
                    fig.update_layout(height=320, margin=dict(t=40,b=20))
                    st.plotly_chart(fig, use_container_width=True)

            with gd2:
                # Distribution of total delays
                fig = px.histogram(df_descargas, x="Demora total (hs:mm)_min",
                                   nbins=30,
                                   title="Distribución de demoras totales — Descargas",
                                   labels={"Demora total (hs:mm)_min": "Minutos"},
                                   color_discrete_sequence=["#0066cc"])
                fig.update_layout(height=320, margin=dict(t=40,b=20))
                st.plotly_chart(fig, use_container_width=True)

            # Impacto en planificación de cargas - comparar demora descarga vs siguiente carga
            st.markdown("#### 📍 Impacto de demoras en descargas sobre planificación de cargas (Origen Palmira)")
            if not df_desc_palmira.empty:
                st.info(f"Se encontraron **{len(df_desc_palmira)}** eventos de descarga relacionados a Palmira.")
                fig = px.scatter(
                    df_desc_palmira.dropna(subset=["Demora total (hs:mm)_min","Tiempo en dock (hs:mm)_min"]),
                    x="Tiempo en cola (hs:mm)_min",
                    y="Tiempo en dock (hs:mm)_min",
                    size="Demora total (hs:mm)_min",
                    hover_data=["Alias actual","Conductor","Zona"] if "Alias actual" in df_desc_palmira.columns else None,
                    title="Cola vs Tiempo en dock — Palmira (tamaño = Demora total)",
                    color="Demora total (hs:mm)_min",
                    color_continuous_scale="Oranges",
                    labels={
                        "Tiempo en cola (hs:mm)_min": "Tiempo en cola (min)",
                        "Tiempo en dock (hs:mm)_min": "Tiempo en dock (min)",
                    },
                )
                fig.update_layout(height=380, margin=dict(t=50,b=20))
                st.plotly_chart(fig, use_container_width=True)
            else:
                # Mostrar análisis general de descargas por zona
                if "Zona" in df_descargas.columns:
                    g = (df_descargas.groupby("Zona")["Demora total (hs:mm)_min"]
                         .agg(["mean","count"]).reset_index()
                         .rename(columns={"mean":"Demora prom (min)","count":"Eventos"})
                         .sort_values("Demora prom (min)", ascending=False).head(15))
                    fig = px.bar(g, x="Demora prom (min)", y="Zona", orientation="h",
                                 title="Demora promedio por zona de descarga",
                                 color="Demora prom (min)", color_continuous_scale="Blues",
                                 labels={"Demora prom (min)": "Minutos"})
                    fig.update_coloraxes(showscale=False)
                    fig.update_layout(height=400, margin=dict(t=40,b=20))
                    st.plotly_chart(fig, use_container_width=True)

            # Heatmap descargas
            if "DiaSemana" in df_descargas.columns and "Hora" in df_descargas.columns:
                day_order = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
                day_labels_short = {"Monday":"Lun","Tuesday":"Mar","Wednesday":"Mié",
                                    "Thursday":"Jue","Friday":"Vie","Saturday":"Sáb","Sunday":"Dom"}
                pivot = df_descargas.groupby(["DiaSemana","Hora"])["Demora total (hs:mm)_min"].mean().unstack(fill_value=0)
                pivot = pivot.reindex([d for d in day_order if d in pivot.index])
                pivot.index = [day_labels_short.get(d, d) for d in pivot.index]
                # Convert minutes to HH:MM format for display
                pivot_display = pivot.map(minutes_to_hm_format)
                fig = px.imshow(pivot,
                                title="📊 Heatmap: Demora promedio (HH:MM) — Día × Hora · Descargas",
                                color_continuous_scale="Blues",
                                labels={"color":"horas","x":"Hora","y":"Día"},
                                text_auto=False,
                                aspect="auto")
                # Add text annotations with HH:MM format
                fig.update_traces(text=pivot_display.values, texttemplate="%{text}", textfont={"size": 11})
                fig.update_layout(height=300, margin=dict(t=50,b=20))
                st.plotly_chart(fig, use_container_width=True)

            with st.expander("🔍 Top 20 unidades con mayor demora en Descargas"):
                if "Alias actual" in df_descargas.columns:
                    top = (df_descargas.groupby("Alias actual")["Demora total (hs:mm)_min"]
                           .agg(["mean","count"]).reset_index()
                           .rename(columns={"mean":"Demora prom (min)","count":"Eventos"})
                           .sort_values("Demora prom (min)", ascending=False).head(20))
                    top["Demora formateada"] = top["Demora prom (min)"].apply(minutes_to_hhmm)
                    st.dataframe(top[["Alias actual","Eventos","Demora formateada"]], use_container_width=True)


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 · INCIDENCIAS
# ══════════════════════════════════════════════════════════════════════════════
with tab2:

    if df_inc_raw.empty:
        st.warning("No hay datos de incidencias disponibles.")
    else:
        df_inc = df_inc_raw.copy()

        st.subheader("🔧 Reporte de Incidencias — Análisis de Recurrencia")

        fi1, fi2, fi3 = st.columns(3)
        with fi1:
            cat_sel = st.multiselect(
                "Categoría",
                options=sorted(df_inc["Categoría"].dropna().unique()),
                default=sorted(df_inc["Categoría"].dropna().unique()),
                key="cat_inc",
            )
        with fi2:
            sev_options = sorted(df_inc["Severidad"].dropna().unique()) if "Severidad" in df_inc.columns else []
            sev_sel = st.multiselect("Severidad", options=sev_options, default=sev_options, key="sev_inc")
        with fi3:
            estado_inc = sorted(df_inc["Estado"].dropna().unique()) if "Estado" in df_inc.columns else []
            estado_inc_sel = st.multiselect("Estado", options=estado_inc, default=estado_inc, key="est_inc")

        if cat_sel:
            df_inc = df_inc[df_inc["Categoría"].isin(cat_sel)]
        if sev_sel and "Severidad" in df_inc.columns:
            df_inc = df_inc[df_inc["Severidad"].isin(sev_sel)]
        if estado_inc_sel and "Estado" in df_inc.columns:
            df_inc = df_inc[df_inc["Estado"].isin(estado_inc_sel)]

        ki1, ki2, ki3, ki4 = st.columns(4)
        ki1.metric("Total incidencias", f"{len(df_inc):,}")
        ki2.metric("Unidades afectadas", f"{df_inc['Patente'].nunique():,}")
        ki3.metric("Categorías distintas", f"{df_inc['Categoría'].nunique():,}")
        alta = len(df_inc[df_inc["Severidad"] == "alta"]) if "Severidad" in df_inc.columns else "N/A"
        ki4.metric("Severidad Alta", str(alta))

        gi1, gi2 = st.columns(2)

        with gi1:
            # Top unidades con más incidencias
            top_unidades = (df_inc.groupby(["Patente","Alias"])
                            .size().reset_index(name="Incidencias")
                            .sort_values("Incidencias", ascending=False).head(20))
            top_unidades["Unidad"] = top_unidades["Alias"].fillna("") + " (" + top_unidades["Patente"] + ")"
            fig = px.bar(top_unidades.head(15), x="Incidencias", y="Unidad", orientation="h",
                         title="🔧 Top 15 unidades con más incidencias",
                         color="Incidencias", color_continuous_scale="Reds")
            fig.update_coloraxes(showscale=False)
            fig.update_layout(height=450, margin=dict(t=50,b=20), yaxis={"categoryorder":"total ascending"})
            st.plotly_chart(fig, use_container_width=True)

        with gi2:
            # Distribución por categoría
            cat_count = df_inc["Categoría"].value_counts().reset_index()
            cat_count.columns = ["Categoría", "Cantidad"]
            fig = px.pie(cat_count, values="Cantidad", names="Categoría",
                         title="Distribución por Categoría",
                         color_discrete_sequence=px.colors.qualitative.Set3)
            fig.update_layout(height=450, margin=dict(t=50,b=20))
            st.plotly_chart(fig, use_container_width=True)

        gi3, gi4 = st.columns(2)

        with gi3:
            # Subcategorías más frecuentes
            if "Subcategoría" in df_inc.columns:
                sub_count = df_inc["Subcategoría"].value_counts().head(12).reset_index()
                sub_count.columns = ["Subcategoría", "Cantidad"]
                fig = px.bar(sub_count, x="Cantidad", y="Subcategoría", orientation="h",
                             title="Subcategorías más frecuentes",
                             color="Cantidad", color_continuous_scale="Oranges")
                fig.update_coloraxes(showscale=False)
                fig.update_layout(height=380, margin=dict(t=50,b=20), yaxis={"categoryorder":"total ascending"})
                st.plotly_chart(fig, use_container_width=True)

        with gi4:
            # Evolución temporal
            if "Dia" in df_inc.columns:
                timeline = df_inc.groupby("Dia").size().reset_index(name="Incidencias")
                timeline["Dia"] = pd.to_datetime(timeline["Dia"])
                timeline = timeline.sort_values("Dia")
                fig = px.line(timeline, x="Dia", y="Incidencias",
                              title="Evolución de incidencias en el tiempo",
                              markers=True)
                fig.update_traces(line_color="#dc3545")
                fig.update_layout(height=380, margin=dict(t=50,b=20))
                st.plotly_chart(fig, use_container_width=True)

        # Tabla detallada para taller
        st.markdown("#### 🏭 Foco en Taller — Unidades con mayor recurrencia mecánica")
        df_mecanico = df_inc[df_inc["Categoría"].isin(["Mecánico","REPARACION"])]
        if not df_mecanico.empty:
            taller = (df_mecanico.groupby(["Patente","Alias"])
                      .agg(
                          Incidencias=("Patente","count"),
                          Ultima_incidencia=("Fecha del evento","max") if "Fecha del evento" in df_mecanico.columns else ("Patente","count"),
                          Subcategorias=("Subcategoría", lambda x: ", ".join(x.dropna().unique())) if "Subcategoría" in df_mecanico.columns else ("Patente","count"),
                      ).reset_index()
                      .sort_values("Incidencias", ascending=False))
            taller["Prioridad"] = taller["Incidencias"].apply(
                lambda x: "🔴 Alta" if x >= 3 else ("🟡 Media" if x == 2 else "🟢 Baja")
            )
            st.dataframe(
                taller[["Patente","Alias","Incidencias","Subcategorias","Prioridad"]],
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("No hay incidencias mecánicas con los filtros seleccionados.")

        with st.expander("📋 Detalle completo de incidencias"):
            cols_show = [c for c in ["#","Estado","Severidad","Patente","Alias","Categoría","Subcategoría",
                                      "Chofer","Descripción","Fecha del evento"] if c in df_inc.columns]
            st.dataframe(df_inc[cols_show].sort_values("Fecha del evento", ascending=False)
                         if "Fecha del evento" in df_inc.columns else df_inc[cols_show],
                         use_container_width=True, hide_index=True)


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 · KM POR CHOFER / ICM RANKING
# ══════════════════════════════════════════════════════════════════════════════
with tab3:

    if df_icm_raw.empty:
        st.warning("No hay datos de ICM/Ranking disponibles.")
    else:
        df_icm = df_icm_raw.copy()

        st.subheader("📍 Reporte de Km Recorrido por Chofer / Unidad")

        # KPIs
        kk1, kk2, kk3, kk4 = st.columns(4)
        kk1.metric("Total unidades", f"{len(df_icm):,}")
        kk2.metric("KM promedio", f"{df_icm['KM'].mean():,.0f}" if "KM" in df_icm.columns else "N/A")
        kk3.metric("KM total flota", f"{df_icm['KM'].sum():,.0f}" if "KM" in df_icm.columns else "N/A")

        # Umbral configurable
        km_threshold = st.slider(
            "⚙️ Umbral de alerta KM bajo (unidades por debajo de este valor se marcan en rojo)",
            min_value=0, max_value=int(df_icm["KM"].max()) if "KM" in df_icm.columns else 5000,
            value=int(df_icm["KM"].quantile(0.25)) if "KM" in df_icm.columns else 1000,
            step=50,
        )
        bajo_ritmo = df_icm[df_icm["KM"] < km_threshold] if "KM" in df_icm.columns else pd.DataFrame()
        kk4.metric("Unidades bajo umbral", f"{len(bajo_ritmo):,}", delta=f"< {km_threshold} km", delta_color="inverse")

        gk1, gk2 = st.columns(2)

        with gk1:
            # Ranking KM
            if "KM" in df_icm.columns and "Alias" in df_icm.columns:
                df_sorted = df_icm.sort_values("KM", ascending=True)
                df_sorted["Color"] = df_sorted["KM"].apply(
                    lambda x: "🔴 Bajo" if x < km_threshold else "🟢 Normal"
                )
                fig = px.bar(df_sorted.tail(30), x="KM", y="Alias", orientation="h",
                             title="KM recorrido por unidad (últimas 30)",
                             color="Color",
                             color_discrete_map={"🔴 Bajo": "#dc3545", "🟢 Normal": "#28a745"},
                             labels={"KM": "Kilómetros", "Alias": "Unidad"})
                fig.update_layout(height=600, margin=dict(t=50,b=20),
                                  yaxis={"categoryorder":"total ascending"}, showlegend=True)
                st.plotly_chart(fig, use_container_width=True)

        with gk2:
            # Eventos / 100 km (seguridad)
            if "Ev/100km" in df_icm.columns and "Alias" in df_icm.columns:
                df_ev = df_icm.sort_values("Ev/100km", ascending=False).head(20)
                fig = px.bar(df_ev, x="Alias", y="Ev/100km",
                             title="Top 20 unidades — Eventos por 100 km (mayor riesgo)",
                             color="Ev/100km", color_continuous_scale="YlOrRd",
                             labels={"Ev/100km": "Ev/100km", "Alias": "Unidad"})
                fig.update_coloraxes(showscale=False)
                fig.update_layout(height=400, margin=dict(t=50,b=20),
                                  xaxis_tickangle=-45)
                st.plotly_chart(fig, use_container_width=True)

            # KM vs Velocidad
            if "KM" in df_icm.columns and "Velocidad" in df_icm.columns:
                fig = px.scatter(df_icm, x="KM", y="Velocidad",
                                 hover_data=["Alias","Patente"] if "Patente" in df_icm.columns else ["Alias"],
                                 title="KM vs Eventos de Velocidad",
                                 color="Velocidad", color_continuous_scale="Reds",
                                 labels={"KM": "Kilómetros", "Velocidad": "Eventos velocidad"})
                fig.update_layout(height=320, margin=dict(t=50,b=20))
                st.plotly_chart(fig, use_container_width=True)

        # Unidades bajo ritmo — tabla de acción
        st.markdown("#### 🚨 Unidades con KM bajo umbral — Foco de ajuste")
        if not bajo_ritmo.empty:
            cols_tbl = [c for c in ["#","Alias","Patente","KM","Ev/100km","Eventos","Velocidad","Frenados","Fatiga (#)"] if c in bajo_ritmo.columns]
            st.dataframe(
                bajo_ritmo[cols_tbl].sort_values("KM"),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.success("✅ Todas las unidades están sobre el umbral configurado.")

        # Full table
        with st.expander("📋 Tabla completa ICM Ranking"):
            cols_full = [c for c in ["#","Alias","Patente","KM","Ev/100km","Eventos","Velocidad",
                                      "Frenados","Aceleración","Giros","Baches","Fatiga (#)","Fatiga (min)"]
                         if c in df_icm.columns]
            st.dataframe(df_icm[cols_full].sort_values("KM", ascending=False),
                         use_container_width=True, hide_index=True)
