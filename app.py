"""
Plataforma de Análisis GPS UBIKO para Cuerpos Técnicos de Fútbol.
Trabajo de Fin de Grado (TFG) - Ingeniería Informática.
Interfaz interactiva 100% Python desarrollada con Streamlit.
"""

import os
import sys
from pathlib import Path
from datetime import date, datetime
import time
import streamlit as st
import pandas as pd
from sqlalchemy.orm import Session
from typing import Optional, List, Dict, Any, Tuple
import importlib

# Asegurar la raíz del proyecto en el path de Python (crítico para Streamlit Cloud en Linux)
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# Configuración de página Streamlit (debe ser el primer comando de Streamlit)
st.set_page_config(
    page_title="UBIKO Performance & Tactical Hub",
    page_icon="⚽",
    layout="wide",
    initial_sidebar_state="expanded"
)

try:
    from src.config import (
        DEFAULT_CLUB_ID,
        MICROCYCLE_DAYS,
        MICROCYCLE_DESCRIPTIONS,
        POSITIONS,
        DATABASE_PATH,
        SAMPLES_DIR,
        MICROCYCLE_MATCH_TARGETS,
        SALERM_PUENTE_GENIL_MATRIX
    )
    from src.database.connection import get_db, init_db
    from src.database.models import Player, TrainingSession, PlayerMetric, TargetLoad, PlayerMatchPeak
    from src.services.analytics import (
        calculate_session_summary,
        calculate_ewma_acwr,
        calculate_compliance_table,
        calculate_individual_microcycle_compliance,
        calculate_pre_session_prescription,
        save_pre_session_prescription,
        evaluate_multivariable_deficit,
        get_player_longitudinal_comparison,
        get_player_match_peak,
        sync_and_update_player_match_peaks,
        get_rpe_category,
        get_all_reference_matches,
        get_match_reference_table_data,
        calculate_excel_pre_session_prescription,
        get_post_session_multivariable_table,
        LOAD_LEVEL_PRESETS,
        get_load_level_preset,
        classify_session_player_states,
        get_available_microcycles,
        get_weekly_microcycle_summary,
        get_starting_xi_weekly_readiness,
        get_player_individual_profile_data
    )
    from src.services.importer import UbikoImporter
    try:
        from src.services.report_generator import (
            generate_tactical_report,
            generate_weekly_coach_report,
            generate_weekly_coach_html_report
        )
    except (ImportError, AttributeError):
        importlib.reload(src.services.report_generator)
        from src.services.report_generator import (
            generate_tactical_report,
            generate_weekly_coach_report,
            generate_weekly_coach_html_report
        )
    from src.utils.helpers import (
        create_acwr_longitudinal_chart,
        create_compliance_chart,
        create_zscore_chart,
        create_training_vs_match_chart,
        create_weekly_comparison_chart,
        render_semaforo_legend_html
    )
    from seed_data import seed_database
except Exception as e_import:
    import traceback
    st.error(f"❌ **Error al cargar los módulos del sistema**: `{e_import}`")
    st.code(traceback.format_exc(), language="python")
    st.stop()


# Estilos CSS personalizados para temática deportiva profesional de alto rendimiento
st.markdown("""
<style>
    /* ====================================================================
       SISTEMA DE DISEÑO VISUAL PROFESIONAL - UBIKO PERFORMANCE HUB
       Paleta: Dark / Slate Premium (#0B1120, #0F172A, #1E293B, #334155)
       Tipografía: Inter (Google Fonts) + Soporte Números Tabulares (tnum)
       ==================================================================== */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');

    :root {
        --bg-main: #0B1120;
        --bg-surface: #0F172A;
        --bg-card: #1E293B;
        --border-card: #334155;
        --border-subtle: #1E293B;
        --text-primary: #F8FAFC;
        --text-secondary: #94A3B8;
        --text-muted: #64748B;
        --accent-primary: #38BDF8;
        --accent-blue: #0284C7;
        --status-opt: #10B981;
        --status-mod: #F59E0B;
        --status-dgr: #EF4444;
    }

    /* Tipografía Global y Estilo Base */
    html, body, [class*="css"], .stApp {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif !important;
        background-color: var(--bg-main) !important;
        color: var(--text-primary) !important;
        -webkit-font-smoothing: antialiased;
    }

    /* Números Tabulares para prevenir saltos de línea y facilitar lectura técnica rápida */
    .tabular-nums, [data-testid="stDataFrame"], [data-testid="stTable"], .metric-value, .badge, .badge-pill {
        font-variant-numeric: tabular-nums !important;
        font-feature-settings: "tnum" 1 !important;
    }

    /* Ocultar elementos predeterminados de Streamlit por seguridad y estética de suite */
    #MainMenu {visibility: hidden; display: none !important;}
    header {visibility: hidden; height: 0px !important;}
    footer {visibility: hidden; display: none !important;}
    [data-testid="stToolbar"] {visibility: hidden; display: none !important;}
    [data-testid="stDecoration"] {visibility: hidden; display: none !important;}
    [data-testid="stStatusWidget"] {visibility: hidden; display: none !important;}
    .viewerBadge_container__1QSob {display: none !important;}
    [data-testid="manage-app-button"] {display: none !important;}

    /* Contenedor fluido con padding ergonómico */
    .block-container {
        padding-top: 1.25rem !important;
        padding-bottom: 2.5rem !important;
        padding-left: 1.25rem !important;
        padding-right: 1.25rem !important;
        max-width: 100% !important;
    }

    /* Barra Lateral SaaS */
    [data-testid="stSidebar"] {
        background-color: #070D18 !important;
        border-right: 1px solid #1E293B !important;
    }
    [data-testid="stSidebar"] hr {
        border-color: #1E293B !important;
        margin: 12px 0 !important;
    }
    [data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3 {
        color: #F8FAFC !important;
        font-weight: 700 !important;
        letter-spacing: -0.01em !important;
    }

    /* Píldora de Estado Cloud Supabase */
    .db-status-badge {
        display: inline-flex;
        align-items: center;
        gap: 7px;
        background: rgba(16, 185, 129, 0.08);
        border: 1px solid rgba(16, 185, 129, 0.25);
        border-radius: 9999px;
        padding: 3px 10px;
        font-size: 0.74rem;
        font-weight: 600;
        color: #34D399;
        margin-top: 4px;
        margin-bottom: 6px;
    }
    .db-dot {
        width: 7px;
        height: 7px;
        background-color: #10B981;
        border-radius: 50%;
        box-shadow: 0 0 6px #10B981;
        display: inline-block;
    }

    /* Tarjetas de Métricas Ejecutivas (KPI Cards) */
    .metric-card {
        background-color: #1E293B;
        border: 1px solid #334155;
        border-radius: 10px;
        padding: 13px 15px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.22);
        margin-bottom: 10px;
        transition: border-color 0.15s ease, transform 0.15s ease;
    }
    .metric-card:hover {
        border-color: #475569;
    }
    .metric-title {
        color: #94A3B8;
        font-size: 0.74rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        margin-bottom: 4px;
    }
    .metric-value {
        color: #F8FAFC;
        font-size: 1.65rem;
        font-weight: 700;
        line-height: 1.2;
    }
    .metric-subtitle {
        color: #64748B;
        font-size: 0.74rem;
        margin-top: 4px;
    }

    /* Insignias de Estado Redondeadas (Pills) */
    .badge, .badge-pill {
        display: inline-block;
        padding: 2px 10px;
        border-radius: 9999px;
        font-size: 0.74rem;
        font-weight: 600;
        letter-spacing: 0.02em;
    }
    .badge-optimal {
        background-color: rgba(16, 185, 129, 0.12);
        border: 1px solid rgba(16, 185, 129, 0.3);
        color: #34D399;
    }
    .badge-warning {
        background-color: rgba(245, 158, 11, 0.12);
        border: 1px solid rgba(245, 158, 11, 0.3);
        color: #FBBF24;
    }
    .badge-danger {
        background-color: rgba(239, 68, 68, 0.12);
        border: 1px solid rgba(239, 68, 68, 0.3);
        color: #F87171;
    }
    .badge-info {
        background-color: rgba(56, 189, 248, 0.12);
        border: 1px solid rgba(56, 189, 248, 0.3);
        color: #38BDF8;
    }

    /* Pestañas (Tabs) Estilizadas */
    [data-testid="stTabs"] [data-baseweb="tab-list"] {
        gap: 6px;
        background-color: transparent;
        border-bottom: 1px solid #334155;
        padding-bottom: 2px;
    }
    [data-testid="stTabs"] [data-baseweb="tab"] {
        background-color: transparent !important;
        border-radius: 6px 6px 0 0 !important;
        border: none !important;
        color: #94A3B8 !important;
        font-weight: 600 !important;
        font-size: 0.88rem !important;
        padding: 7px 16px !important;
    }
    [data-testid="stTabs"] [data-baseweb="tab"][aria-selected="true"] {
        color: #38BDF8 !important;
        border-bottom: 2px solid #38BDF8 !important;
    }

    /* Botones Streamlit Refinados */
    .stButton > button {
        border-radius: 8px !important;
        font-weight: 600 !important;
        font-size: 0.88rem !important;
        transition: all 0.15s ease !important;
        border: 1px solid #334155 !important;
    }
    .stButton > button[kind="primary"] {
        background: linear-gradient(135deg, #0284C7 0%, #0369A1 100%) !important;
        border: 1px solid #38BDF8 !important;
        color: #FFFFFF !important;
        box-shadow: 0 2px 4px rgba(2, 132, 199, 0.3) !important;
    }
    .stButton > button[kind="primary"]:hover {
        background: linear-gradient(135deg, #0369A1 0%, #075985 100%) !important;
        border-color: #7DD3FC !important;
    }
    .stButton > button[kind="secondary"] {
        background-color: #1E293B !important;
        color: #E2E8F0 !important;
    }
    .stButton > button[kind="secondary"]:hover {
        background-color: #243248 !important;
        border-color: #475569 !important;
        color: #F8FAFC !important;
    }

    /* Selectores, Radios y Entradas de Formulario */
    [data-testid="stRadio"] label, [data-testid="stSelectbox"] label, [data-testid="stMultiSelect"] label {
        font-size: 0.80rem !important;
        font-weight: 600 !important;
        color: #94A3B8 !important;
        text-transform: uppercase !important;
        letter-spacing: 0.04em !important;
    }
    [data-baseweb="select"] > div {
        background-color: #1E293B !important;
        border: 1px solid #334155 !important;
        border-radius: 8px !important;
    }

    /* Dataframes y Tablas Estilo Suite Analítica */
    [data-testid="stDataFrame"], [data-testid="stTable"] {
        border: 1px solid #334155 !important;
        border-radius: 10px !important;
        overflow: hidden !important;
    }

    /* Paneles de Notificación / Alertas nativas de Streamlit */
    [data-testid="stAlert"] {
        background-color: #1E293B !important;
        border: 1px solid #334155 !important;
        border-radius: 8px !important;
        color: #E2E8F0 !important;
    }

    /* Caja de Informes Tácticos */
    .report-box {
        background-color: #0F172A;
        border: 1px solid #334155;
        border-radius: 8px;
        padding: 16px;
        font-family: 'JetBrains Mono', 'Fira Code', 'Courier New', monospace;
        white-space: pre-wrap;
        color: #E2E8F0;
        line-height: 1.55;
        font-size: 0.84rem;
        overflow-x: auto;
    }

    /* OPTIMIZACIÓN MULTIPLATAFORMA MÓVIL Y TABLET (Breakpoints < 768px) */
    @media (max-width: 768px) {
        .block-container {
            padding-left: 0.6rem !important;
            padding-right: 0.6rem !important;
            padding-top: 1rem !important;
        }

        h1 {
            font-size: 1.50rem !important;
            line-height: 1.25 !important;
        }
        h2 {
            font-size: 1.25rem !important;
        }
        h3 {
            font-size: 1.05rem !important;
        }

        .metric-value {
            font-size: 1.35rem !important;
        }
        .metric-card {
            padding: 10px 12px !important;
            margin-bottom: 8px !important;
        }

        [data-testid="column"] {
            min-width: 100% !important;
            flex: 1 1 100% !important;
            margin-bottom: 0.5rem;
        }

        button[kind="primary"], button[kind="secondary"], .stButton > button {
            min-height: 44px !important;
            font-size: 0.92rem !important;
            border-radius: 8px !important;
        }

        [data-testid="stDataFrame"], [data-testid="stTable"] {
            overflow-x: auto !important;
            -webkit-overflow-scrolling: touch;
            width: 100% !important;
        }

        .js-plotly-plot, .plot-container {
            max-width: 100% !important;
            overflow-x: hidden !important;
        }
    }
</style>

<!-- Metadatos y soporte PWA (Progressive Web App) -->
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="UBIKO Hub">
<meta name="theme-color" content="#0B1120">
<link rel="apple-touch-icon" href="https://img.icons8.com/color/192/football-ball.png">
""", unsafe_allow_html=True)


@st.cache_resource(show_spinner="Cargando...")
def bootstrap_database():
    """
    Inicializa la base de datos y la plantilla oficial de 26 jugadores una sola vez al arrancar el servidor.
    Sincroniza automáticamente cualquier archivo CSV de sesión disponible en data/samples.
    """
    init_db()
    with get_db() as db:
        from src.database.models import Player, TargetLoad
        if db.query(Player).count() == 0 or db.query(TargetLoad).count() == 0:
            from seed_data import seed_roster_and_targets
            seed_roster_and_targets()

        # Sincronizar techos dinámicos del 100% de partido de máxima exigencia
        from src.services.analytics import sync_and_update_player_match_peaks
        sync_and_update_player_match_peaks(db)

    # Iniciar verificación/descarga de Chromium en segundo plano para estar listo ante clics del P.F.
    try:
        import threading
        from ubiko_sync import ensure_playwright_installed
        threading.Thread(target=ensure_playwright_installed, daemon=True).start()
    except Exception:
        pass

    return True


# Inicialización ultrarrápida (solo se ejecuta 1 vez)
bootstrap_database()


@st.cache_data(ttl=300, show_spinner="Cargando...")
def get_cached_sessions():
    """Cachea la lista de sesiones durante 5 min en RAM (se invalida automáticamente al sincronizar)."""
    with get_db() as db:
        sessions = (
            db.query(TrainingSession)
            .order_by(TrainingSession.date.desc())
            .all()
        )
        result = []
        seen = set()
        for s in sessions:
            label = f"{s.date.strftime('%d/%m/%Y')} - {s.microcycle_day} ({s.session_type})"
            if label in seen:
                clean_name = s.name.replace("TEMPORADA_", "").replace("SESIÓN_", "S").replace("SESION_", "S")
                label = f"{s.date.strftime('%d/%m/%Y')} - {s.microcycle_day} [{clean_name[:15]}]"
            seen.add(label)
            result.append((s.id, label))
        return result


@st.cache_data(ttl=600, show_spinner="Cargando...")
def get_cached_session_summary(session_id: int):
    """Cachea los KPIs, z-scores y resumen de la sesión en RAM para renderizado a 60 FPS."""
    with get_db() as db:
        return calculate_session_summary(db, session_id)


@st.cache_data(ttl=600, show_spinner="Cargando...")
def get_cached_players_list():
    """Cachea la lista de futbolistas activos."""
    with get_db() as db:
        players = db.query(Player).filter(Player.active == True).order_by(Player.dorsal.asc()).all()
        return [(p.id, p.dorsal, p.name, p.position, p.max_speed_kmh) for p in players]


@st.cache_data(ttl=600, show_spinner="Cargando...")
def get_cached_player_acwr(player_id: int, metric: str = "total_distance"):
    """Cachea la serie temporal de EWMA ACWR de un futbolista."""
    with get_db() as db:
        return calculate_ewma_acwr(db, player_id, load_metric=metric)


@st.cache_data(ttl=600, show_spinner="Cargando...")
def get_cached_individual_compliance(session_id: int):
    """Cachea la comparativa individual respecto al 100% de Partido de Máxima Exigencia."""
    with get_db() as db:
        return calculate_individual_microcycle_compliance(db, session_id)


@st.cache_data(ttl=600, show_spinner="Cargando...")
def get_cached_player_longitudinal(player_id: int):
    """Cachea el histórico de sesiones y techo de partido 100% para comparativas."""
    with get_db() as db:
        return get_player_longitudinal_comparison(db, player_id)


@st.cache_data(ttl=600, show_spinner="Cargando...")
def get_cached_pre_session_prescription(microcycle_day: str, pct_td: float, pct_hsr: float, pct_eff: float):
    """Cachea las metas cuantitativas mínimas requeridas para la plantilla en planificación pre-sesión."""
    with get_db() as db:
        return calculate_pre_session_prescription(db, microcycle_day, pct_td, pct_hsr, pct_eff)


@st.cache_data(ttl=300, show_spinner="Cargando...")
def get_cached_all_reference_matches(include_individual_peaks: bool = True):
    """Cachea los partidos oficiales y bloques de referencia disponibles."""
    with get_db() as db:
        try:
            matches = get_all_reference_matches(db, include_individual_peaks=include_individual_peaks)
        except TypeError:
            matches = get_all_reference_matches(db)
        
        if not include_individual_peaks:
            matches = [m for m in matches if m.get("session_id") is not None]
        return matches


@st.cache_data(ttl=300, show_spinner="Cargando...")
def get_cached_match_reference_table_data(session_id: Optional[int], top_player_id: Optional[int] = None):
    """Cachea la tabla de referencia de datos de partido idéntica al Excel del preparador."""
    with get_db() as db:
        try:
            return get_match_reference_table_data(db, session_id, top_player_id=top_player_id)
        except TypeError:
            return get_match_reference_table_data(db, session_id)


@st.cache_data(ttl=600, show_spinner="Cargando...")
def get_cached_excel_pre_session_prescription(
    reference_session_id: Optional[int],
    microcycle_day: str,
    pct_td: float,
    pct_hsr: float,
    pct_sprint: float,
    pct_eff: float
):
    """Cachea la calculadora de prescripción pre-sesión en formato exacto de Excel."""
    with get_db() as db:
        return calculate_excel_pre_session_prescription(
            db, reference_session_id, microcycle_day, pct_td, pct_hsr, pct_sprint, pct_eff
        )


@st.cache_data(ttl=600, show_spinner="Cargando...")
def get_cached_post_session_multivariable_table(session_id: int, reference_session_id: Optional[int], level: Optional[int] = None):
    """Cachea la tabla de semáforo de déficit multivariable post-sesión."""
    with get_db() as db:
        import importlib
        import src.services.analytics as _analytics
        try:
            return _analytics.get_post_session_multivariable_table(db, session_id, reference_session_id, level=level)
        except TypeError:
            importlib.reload(_analytics)
            return _analytics.get_post_session_multivariable_table(db, session_id, reference_session_id, level=level)


@st.cache_data(ttl=600, show_spinner="Cargando...")
def get_cached_classified_session_states(session_id: int, reference_session_id: Optional[int] = None):
    """Cachea la clasificación de la plantilla en los 3 estados operativos (Déficit, Óptimo, Sobre-estímulo)."""
    with get_db() as db:
        return classify_session_player_states(db, session_id, reference_session_id)


@st.cache_data(ttl=300, show_spinner="Cargando...")
def get_cached_available_microcycles():
    """Cachea la lista de microciclos competitivos de la temporada."""
    with get_db() as db:
        return get_available_microcycles(db)


@st.cache_data(ttl=600, show_spinner="Cargando...")
def get_cached_weekly_microcycle_summary(start_date: date, end_date: date):
    """Cachea el resumen y KPIs del microciclo semanal para el cuerpo técnico."""
    with get_db() as db:
        return get_weekly_microcycle_summary(db, start_date, end_date)


@st.cache_data(ttl=300, show_spinner="Analizando cargas semanales...")
def get_cached_starting_xi_readiness(session_id: int):
    """Cachea la matriz de carga semanal de 7 días y recomendación de once inicial."""
    with get_db() as db:
        return get_starting_xi_weekly_readiness(db, session_id)


@st.cache_data(ttl=300, show_spinner="Cargando perfil individual del futbolista...")
def get_cached_player_individual_profile(player_id: int):
    """Cachea el perfil individual longitudinal y matriz de cumplimiento del jugador."""
    with get_db() as db:
        return get_player_individual_profile_data(db, player_id)






# ==========================================
# SEGURIDAD & AUTENTICACIÓN DEL CUERPO TÉCNICO
# ==========================================
def check_authentication() -> bool:
    """Verifica si el usuario se ha autenticado con la contraseña de seguridad."""
    if st.session_state.get("authenticated", False):
        return True

    try:
        configured_pwd = (
            st.secrets.get("APP_PASSWORD", "ubiko2026")
            if hasattr(st, "secrets")
            else os.environ.get("APP_PASSWORD", "ubiko2026")
        )
    except Exception:
        configured_pwd = os.environ.get("APP_PASSWORD", "ubiko2026")

    col_l1, col_l2, col_l3 = st.columns([1, 1.8, 1])
    with col_l2:
        st.write("")
        st.write("")
        st.markdown("""
        <div style="background: #1E293B; border: 1px solid #334155; border-radius: 14px; padding: 28px 24px; text-align: center; box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.4);">
            <img src="https://img.icons8.com/color/96/football-ball.png" width="56" style="margin-bottom: 10px; filter: drop-shadow(0 2px 4px rgba(0,0,0,0.3));"/>
            <h2 style="color: #F8FAFC; margin: 0 0 6px 0; font-size: 1.45rem; font-weight: 700; letter-spacing: -0.02em;">UBIKO Performance Hub</h2>
            <div style="color: #94A3B8; font-size: 0.84rem; margin-bottom: 16px; line-height: 1.45;">
                Suite Analítica de Telemetría GPS & Periodización Táctica.<br>
                <span class="badge-pill optimal" style="margin-top: 6px;">Acceso Confidencial &bull; Cuerpo Técnico</span>
            </div>
        </div>
        """, unsafe_allow_html=True)
        st.write("")

        with st.form("login_form", clear_on_submit=False):
            entered_pwd = st.text_input(
                "Contraseña de Acceso del Club:",
                type="password",
                placeholder="Introduce la clave del cuerpo técnico...",
                help="Protege la telemetría, prescripciones y datos de los futbolistas frente a accesos no autorizados."
            )
            submit_btn = st.form_submit_button("Entrar al Sistema", type="primary", use_container_width=True)
            if submit_btn:
                if entered_pwd == configured_pwd:
                    st.session_state["authenticated"] = True
                    st.toast("Acceso concedido al Hub.", icon="⚽")
                    st.rerun()
                else:
                    st.error("Contraseña incorrecta. Acceso restringido por confidencialidad del club.")

        st.caption("Cifrado de datos en tránsito y reposo bajo políticas de club profesional.")

    return False

if not check_authentication():
    st.stop()


# ==========================================
# BARRA LATERAL (SIDEBAR SAAS)
# ==========================================
with st.sidebar:
    st.markdown("""
    <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 6px; padding-top: 4px;">
        <img src="https://img.icons8.com/color/96/football-ball.png" width="38" height="38" style="filter: drop-shadow(0 2px 4px rgba(0,0,0,0.3));"/>
        <div>
            <div style="color: #F8FAFC; font-weight: 700; font-size: 1.15rem; letter-spacing: -0.02em; line-height: 1.15;">UBIKO Hub</div>
            <div style="color: #64748B; font-size: 0.72rem; font-weight: 500;">Rendimiento GPS & Cargas</div>
        </div>
    </div>
    <div class="db-status-badge">
        <span class="db-dot"></span>
        <span>Supabase Cloud Conectado</span>
    </div>
    """, unsafe_allow_html=True)

    allowed_menus = [
        "📊 Panel de Sesión & Semáforo",
        "👤 Perfil Individual del Jugador",
        "🏟️ Referencia Partidos (Excel P.F.)",
        "📋 Planificación & Comparativa (50/70/80%)",
        "📈 Evolución Longitudinal & ACWR",
        "🤖 Asistente de IA (Cuerpo Técnico)"
    ]

    if "nav_menu" not in st.session_state or st.session_state["nav_menu"] not in allowed_menus:
        st.session_state["nav_menu"] = "📊 Panel de Sesión & Semáforo"

    menu = st.radio(
        "Navegación del Sistema",
        allowed_menus,
        key="nav_menu"
    )

    st.divider()
    st.markdown('<div class="metric-title" style="margin-bottom: 6px;">Selección de Sesión</div>', unsafe_allow_html=True)

    cached_sessions = get_cached_sessions()
    session_options = {label: s_id for s_id, label in cached_sessions}

    if session_options:
        selected_session_label = st.selectbox("Sesión activa:", list(session_options.keys()), label_visibility="collapsed")
        selected_session_id = session_options[selected_session_label]
    else:
        st.warning("No hay sesiones en la base de datos.")
        selected_session_id = None

    with st.expander("🔄 Sincronización Web UBIKO (Nuevas Sesiones)", expanded=False):
        st.caption("💡 **Base de datos permanentemente actualizada:** Todas las sesiones ya están guardadas en Supabase. Usa este botón **únicamente** cuando el equipo acabe de disputar un nuevo entreno/partido y se hayan subido los chalecos a la web de UBIKO.")
        sync_from_date = st.date_input("Recopilar desde fecha:", value=date(2026, 9, 3), key="sidebar_sync_date")
        col_opt1, col_opt2 = st.columns(2)
        with col_opt1:
            force_sync = st.checkbox("Forzar todo", value=False, key="sidebar_force_sync", help="Re-descarga e ingesta sesiones en Supabase aunque ya existan.")
        with col_opt2:
            visible_sync = st.checkbox("Ver navegador", value=False, key="sidebar_visible_sync", help="Muestra la ventana del navegador para verificar el login o descargas en UBIKO.")

        if st.button("Sincronizar Telemetría", type="primary", use_container_width=True):
            with st.spinner("Conectando con UBIKO Web y guardando en Supabase..."):
                import importlib
                import ubiko_sync
                importlib.reload(ubiko_sync)
                res_sync = ubiko_sync.sync_latest_session(headless=not visible_sync, force=force_sync, min_date=sync_from_date)
                st.cache_data.clear()

                is_success = res_sync.get("success", False)
                synced_count = res_sync.get("synced_count", 0)
                msg = res_sync.get("message", "Sincronización con Supabase completada.")

                if is_success and synced_count > 0:
                    st.toast(msg, icon="⚽")
                    st.success(f"{msg}")
                    time.sleep(1.2)
                    st.rerun()
                elif is_success and synced_count == 0:
                    st.info(f"{msg}")
                else:
                    st.error(f"{msg}")

    with st.expander("Subida Manual de Datos GPS (CSV)", expanded=False):
        st.caption("Si prefieres importar manualmente o te encuentras sin conexión web directa, arrastra el archivo exportado por UBIKO:")
        sb_uploaded = st.file_uploader("Archivo de sesión:", type=["csv", "xlsx"], key="sb_quick_csv")
        if sb_uploaded is not None:
            from src.services.importer import UbikoImporter
            with st.spinner("Procesando e insertando en Supabase..."):
                df_parsed = UbikoImporter.parse_file(sb_uploaded, sb_uploaded.name)
                with get_db() as db:
                    res_imp = UbikoImporter.import_session_to_db(db, df_parsed, original_filename=sb_uploaded.name)
                st.cache_data.clear()
                if res_imp.get("success"):
                    st.success(f"{res_imp.get('message', 'Sesión importada correctamente')}")
                    time.sleep(1.2)
                    st.rerun()
                else:
                    st.error(f"{res_imp.get('error', 'Error al importar archivo')}")

    col_sb1, col_sb2 = st.columns(2)
    with col_sb1:
        if st.button("Depurar Pruebas", use_container_width=True, help="Elimina sesiones y métricas simuladas de Supabase, manteniendo la plantilla y objetivos."):
            from seed_data import purge_simulated_sessions_and_metrics
            n_s, n_m = purge_simulated_sessions_and_metrics()
            st.cache_data.clear()
            st.toast(f"Depuración: {n_s} sesiones y {n_m} métricas borradas.", icon="🧹")
            st.rerun()
    with col_sb2:
        if st.button("Simular Datos", use_container_width=True, help="Genera datos sintéticos de prueba."):
            from seed_data import seed_database
            seed_database(include_sessions=True)
            st.cache_data.clear()
            st.toast("Datos sintéticos generados.", icon="✅")
            st.rerun()

    st.caption("TFG Grado en Ingeniería Informática | UCO")

    st.divider()
    if st.button("Cerrar Sesión", use_container_width=True, help="Bloquea el portal y cierra la sesión del cuerpo técnico."):
        st.session_state["authenticated"] = False
        st.rerun()


# ==========================================
# VISTA 1: PANEL DE SESIÓN & SEMÁFORO
# ==========================================
if menu == "📊 Panel de Sesión & Semáforo":
    if not selected_session_id:
        st.info("Por favor, selecciona o importa una sesión.")
        st.stop()

    summary = get_cached_session_summary(selected_session_id)

    if not summary or "session" not in summary:
        st.warning("No se pudieron cargar los datos de la sesión seleccionada.")
        st.stop()

    sess = summary["session"]
    df_metrics = summary.get("metrics", pd.DataFrame())
    team_kpis = summary.get("team_kpis", {})
    targets = summary.get("targets", {})

    # Cabecera ejecutiva de la sesión
    st.markdown(f"""
    <div style="background: #1E293B; border: 1px solid #334155; border-radius: 12px; padding: 18px 20px; margin-bottom: 16px;">
        <div style="display: flex; justify-content: space-between; align-items: flex-start; flex-wrap: wrap; gap: 10px;">
            <div>
                <div style="color: #94A3B8; font-size: 0.74rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em;">Monitorización de Sesión</div>
                <h1 style="color: #F8FAFC; font-size: 1.60rem; font-weight: 700; margin: 3px 0 6px 0; letter-spacing: -0.02em;">{sess.name}</h1>
                <div style="color: #94A3B8; font-size: 0.84rem;">
                    <b>Enfoque Fisiológico:</b> {MICROCYCLE_DESCRIPTIONS.get(sess.microcycle_day, 'Trabajo de periodización táctica')}
                </div>
            </div>
            <div style="display: flex; gap: 8px; flex-wrap: wrap; align-items: center; margin-top: 4px;">
                <span class="badge-pill" style="background: rgba(15, 23, 42, 0.6); border: 1px solid #334155; color: #E2E8F0;">📅 {sess.date.strftime('%d/%m/%Y')}</span>
                <span class="badge-pill info">⚡ {sess.microcycle_day}</span>
                <span class="badge-pill" style="background: rgba(15, 23, 42, 0.6); border: 1px solid #334155; color: #E2E8F0;">⏱️ {sess.duration_minutes} min</span>
                <span class="badge-pill {'badge-info' if sess.session_type == 'Partido' else 'badge-optimal'}">{sess.session_type}</span>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Fila de KPIs de la sesión
    kpi1, kpi2, kpi3, kpi4, kpi5 = st.columns(5)

    with kpi1:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-title">Distancia Media</div>
            <div class="metric-value">{team_kpis.get('mean_distance', 0.0):.0f} m</div>
            <div class="metric-subtitle">Metros por jugador</div>
        </div>
        """, unsafe_allow_html=True)

    with kpi2:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-title">HSR Medio (>21 km/h)</div>
            <div class="metric-value">{team_kpis.get('mean_hsr', 0.0):.0f} m</div>
            <div class="metric-subtitle">Carrera de alta velocidad</div>
        </div>
        """, unsafe_allow_html=True)

    with kpi3:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-title">HMLD Promedio</div>
            <div class="metric-value">{team_kpis.get('mean_hmld', 0.0):.0f} m</div>
            <div class="metric-subtitle">Distancia metabólica</div>
        </div>
        """, unsafe_allow_html=True)

    with kpi4:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-title">Cumplimiento Plan</div>
            <div class="metric-value">{team_kpis.get('mean_compliance', 0.0):.1f}%</div>
            <div class="metric-subtitle">Real vs Prescrito</div>
        </div>
        """, unsafe_allow_html=True)

    with kpi5:
        danger_count = team_kpis.get('players_in_danger', 0)
        border_col = "#EF4444" if danger_count > 0 else "#10B981"
        st.markdown(f"""
        <div class="metric-card" style="border-left: 4px solid {border_col};">
            <div class="metric-title">Alertas de Sobrecarga</div>
            <div class="metric-value" style="color: {border_col};">{danger_count}</div>
            <div class="metric-subtitle">Jugadores en zona roja</div>
        </div>
        """, unsafe_allow_html=True)

    st.write("")

    if team_kpis.get("count_rpe", 0) > 0:
        r_mean = team_kpis.get("mean_rpe", 0.0)
        sr_mean = team_kpis.get("mean_srpe", 0.0)
        n_rpe = team_kpis.get("count_rpe", 0)
        cat_desc, cat_col = get_rpe_category(r_mean)
        st.info(
            f"⏱️ **Carga Interna Registrada (Foster):** RPE Promedio = **{r_mean:.1f}/10** ({cat_desc}) | "
            f"Carga Interna Media (sRPE) = **{sr_mean:.0f} AU** | Muestra evaluada: **{n_rpe} futbolistas**."
        )

    # ========================================================
    # 1. MONITOR DE CARGA SEMANAL Y DECISIÓN DEL ONCE INICIAL
    # ========================================================
    xi_data = get_cached_starting_xi_readiness(selected_session_id)
    s_cnt = xi_data.get("sessions_count", 0)
    w_start = xi_data.get("start_date")
    w_end = xi_data.get("end_date")
    mc_label = xi_data.get("microcycle_label", "Microciclo")
    range_str = f"{w_start.strftime('%d/%m')} al {w_end.strftime('%d/%m')}" if w_start and w_end else "Semana actual"

    st.markdown("### 📋 Monitor de Carga Semanal y Decisión del Once Inicial")
    st.caption(
        f"Control de carga acumulada en el **{mc_label}** ({range_str} | **{s_cnt} sesiones analizadas**) "
        "para asistir al cuerpo técnico en la confección del once inicial según fatiga aguda (ACWR), sprint/HSR y disponibilidad física."
    )

    # 4 Tarjetas Ejecutivas de Decisión Táctica
    col_x1, col_x2, col_x3, col_x4 = st.columns(4)
    with col_x1:
        st.markdown(f"""
        <div style="background: rgba(16, 185, 129, 0.08); border-top: 4px solid #10B981; border-radius: 10px; padding: 12px 14px; border-left: 1px solid rgba(16, 185, 129, 0.2); border-right: 1px solid rgba(16, 185, 129, 0.2); border-bottom: 1px solid rgba(16, 185, 129, 0.2); min-height: 110px;">
            <div style="color: #6EE7B7; font-size: 0.8rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.04em;">🟢 Aptos Once Titular</div>
            <div style="color: #10B981; font-size: 1.8rem; font-weight: 800; margin: 2px 0;">{xi_data.get('optimal_count', 0)} <span style="font-size: 0.85rem; font-weight: 500; color: #94A3B8;">jugadores</span></div>
            <div style="color: #94A3B8; font-size: 0.74rem;">Sweet Spot (0.80 - 1.25). Carga asimilada y máxima reactividad para 90'.</div>
        </div>
        """, unsafe_allow_html=True)

    with col_x2:
        st.markdown(f"""
        <div style="background: rgba(245, 158, 11, 0.08); border-top: 4px solid #F59E0B; border-radius: 10px; padding: 12px 14px; border-left: 1px solid rgba(245, 158, 11, 0.2); border-right: 1px solid rgba(245, 158, 11, 0.2); border-bottom: 1px solid rgba(245, 158, 11, 0.2); min-height: 110px;">
            <div style="color: #FCD34D; font-size: 0.8rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.04em;">🟡 Precaución Titular</div>
            <div style="color: #F59E0B; font-size: 1.8rem; font-weight: 800; margin: 2px 0;">{xi_data.get('caution_count', 0)} <span style="font-size: 0.85rem; font-weight: 500; color: #94A3B8;">jugadores</span></div>
            <div style="color: #94A3B8; font-size: 0.74rem;">Carga semanal alta o fatiga moderada. Aptos, pero programar recambio min 60-70.</div>
        </div>
        """, unsafe_allow_html=True)

    with col_x3:
        st.markdown(f"""
        <div style="background: rgba(239, 68, 68, 0.08); border-top: 4px solid #EF4444; border-radius: 10px; padding: 12px 14px; border-left: 1px solid rgba(239, 68, 68, 0.2); border-right: 1px solid rgba(239, 68, 68, 0.2); border-bottom: 1px solid rgba(239, 68, 68, 0.2); min-height: 110px;">
            <div style="color: #FCA5A5; font-size: 0.8rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.04em;">🔴 Desaconsejado / Rotar</div>
            <div style="color: #EF4444; font-size: 1.8rem; font-weight: 800; margin: 2px 0;">{xi_data.get('danger_count', 0)} <span style="font-size: 0.85rem; font-weight: 500; color: #94A3B8;">jugadores</span></div>
            <div style="color: #94A3B8; font-size: 0.74rem;">Sobrecarga aguda crítica (ACWR > 1.45) o fatiga extrema. Riesgo lesional elevado.</div>
        </div>
        """, unsafe_allow_html=True)

    with col_x4:
        st.markdown(f"""
        <div style="background: rgba(148, 163, 184, 0.08); border-top: 4px solid #94A3B8; border-radius: 10px; padding: 12px 14px; border-left: 1px solid rgba(148, 163, 184, 0.2); border-right: 1px solid rgba(148, 163, 184, 0.2); border-bottom: 1px solid rgba(148, 163, 184, 0.2); min-height: 110px;">
            <div style="color: #CBD5E1; font-size: 0.8rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.04em;">⚪ Revulsivo / Déficit</div>
            <div style="color: #94A3B8; font-size: 1.8rem; font-weight: 800; margin: 2px 0;">{xi_data.get('deficit_count', 0)} <span style="font-size: 0.85rem; font-weight: 500; color: #94A3B8;">jugadores</span></div>
            <div style="color: #94A3B8; font-size: 0.74rem;">Menos de 100' semanales. Gran frescura neuromuscular; perfil ideal para 2ª mitad.</div>
        </div>
        """, unsafe_allow_html=True)

    st.write("")

    all_player_cards = xi_data.get("players", [])

    # Filtros interactivos de exploración
    f_c1, f_c2, f_c3 = st.columns([1.5, 1.8, 1.2])
    with f_c1:
        pos_options = ["Todas", "Porteros", "Defensas", "Centrocampistas", "Delanteros"]
        selected_pos_group = st.pills("Demarcación:", pos_options, default="Todas", key="xi_pos_pill")
    with f_c2:
        cat_options = ["Todos", "🟢 Apto Titular", "🟡 Precaución", "🔴 Desaconsejado / Rotar", "⚪ Revulsivo / Sin Carga"]
        selected_cat = st.pills("Estado Once:", cat_options, default="Todos", key="xi_cat_pill")
    with f_c3:
        view_mode = st.radio(
            "Visualización:",
            ["Tarjetas Tácticas", "Tabla Comparativa"],
            horizontal=True,
            key="xi_view_mode"
        )

    # Filtrar jugadores
    filtered_players = all_player_cards
    if selected_pos_group != "Todas":
        pos_map = {
            "Porteros": ["Portero"],
            "Defensas": ["Defensa Central", "Lateral Derecho", "Lateral Izquierdo", "Lateral"],
            "Centrocampistas": ["Mediocentro", "Mediocentro Defensivo", "Centrocampista", "Mediapunta", "Interior"],
            "Delanteros": ["Extremo Derecho", "Extremo Izquierdo", "Delantero Centro", "Delantero"]
        }
        allowed_positions = pos_map.get(selected_pos_group, [])
        filtered_players = [
            p for p in filtered_players
            if any(p["position"].lower() in ap.lower() or ap.lower() in p["position"].lower() for ap in allowed_positions)
        ]

    if selected_cat != "Todos":
        if "Apto" in selected_cat:
            filtered_players = [p for p in filtered_players if p["category"] == "Óptimo"]
        elif "Precaución" in selected_cat:
            filtered_players = [p for p in filtered_players if p["category"] == "Precaución"]
        elif "Desaconsejado" in selected_cat:
            filtered_players = [p for p in filtered_players if p["category"] == "Riesgo Sobrecarga"]
        elif "Revulsivo" in selected_cat:
            filtered_players = [p for p in filtered_players if p["category"] in ["Déficit Semanal", "Sin Carga"]]

    if not filtered_players:
        st.info("ℹ️ No hay jugadores que coincidan con los filtros seleccionados.")
    elif view_mode == "Tarjetas Tácticas":
        card_cols = st.columns(3)
        for idx, pl in enumerate(filtered_players):
            col_idx = idx % 3
            with card_cols[col_idx]:
                border_color = pl["xi_color"]
                badge_bg = (
                    "rgba(16, 185, 129, 0.15)" if pl["category"] == "Óptimo" else
                    "rgba(245, 158, 11, 0.15)" if pl["category"] == "Precaución" else
                    "rgba(239, 68, 68, 0.2)" if pl["category"] == "Riesgo Sobrecarga" else
                    "rgba(148, 163, 184, 0.12)"
                )
                st.markdown(f"""
                <div style="background: #1E293B; border-radius: 10px; border: 1px solid #334155; border-left: 4px solid {border_color}; padding: 12px 14px; margin-bottom: 12px; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.2);">
                    <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 6px;">
                        <div>
                            <span style="color: #F8FAFC; font-weight: 700; font-size: 0.95rem;">#{pl['dorsal']} {pl['name']}</span>
                            <div style="color: #94A3B8; font-size: 0.72rem;">{pl['position']} &bull; {pl['sessions_count']} ses. ({pl['mins']:.0f}')</div>
                        </div>
                        <span style="background: {badge_bg}; color: {border_color}; border: 1px solid {border_color}; padding: 2px 7px; border-radius: 6px; font-size: 0.70rem; font-weight: 700;">
                            {pl['xi_badge']}
                        </span>
                    </div>
                    <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 4px; background: #0F172A; padding: 6px 8px; border-radius: 6px; margin: 8px 0; text-align: center;">
                        <div>
                            <div style="color: #64748B; font-size: 0.65rem; text-transform: uppercase;">Dist. Semanal</div>
                            <div style="color: #38BDF8; font-size: 0.85rem; font-weight: 700;">{pl['td_km']:.1f}k</div>
                        </div>
                        <div>
                            <div style="color: #64748B; font-size: 0.65rem; text-transform: uppercase;">HSR >21</div>
                            <div style="color: #F59E0B; font-size: 0.85rem; font-weight: 700;">{pl['hsr_m']:.0f}m</div>
                        </div>
                        <div>
                            <div style="color: #64748B; font-size: 0.65rem; text-transform: uppercase;">Sprint >25</div>
                            <div style="color: #A855F7; font-size: 0.85rem; font-weight: 700;">{pl['sprint_m']:.0f}m</div>
                        </div>
                        <div>
                            <div style="color: #64748B; font-size: 0.65rem; text-transform: uppercase;">ACWR</div>
                            <div style="color: {border_color}; font-size: 0.85rem; font-weight: 700;">{pl['acwr']:.2f}</div>
                        </div>
                    </div>
                    <div style="font-size: 0.72rem; color: #CBD5E1; background: rgba(15, 23, 42, 0.6); padding: 6px 8px; border-radius: 4px; border-left: 2px solid {border_color}; line-height: 1.3;">
                        💡 <b>Staff:</b> {pl['xi_rec']}
                    </div>
                </div>
                """, unsafe_allow_html=True)
    else:
        tbl_data = []
        for pl in filtered_players:
            tbl_data.append({
                "Jugador": f"#{pl['dorsal']} {pl['name']}",
                "Demarcación": pl["position"],
                "Decisión Once": pl["xi_badge"],
                "Minutos Semanales": f"{pl['mins']:.0f}'",
                "Sesiones": pl["sessions_count"],
                "Dist. Semanal (km)": pl["td_km"],
                "HSR Semanal (m)": pl["hsr_m"],
                "Sprint Semanal (m)": pl["sprint_m"],
                "AC.E Semanales": pl["eff"],
                "ACWR (EWMA)": pl["acwr"],
                "Ref. 100% DT": pl["td_100"],
                "Ref. 100% HSR": pl["hsr_100"],
                "Recomendación Staff": pl["xi_rec"]
            })
        df_xi = pd.DataFrame(tbl_data)
        st.dataframe(
            df_xi,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Jugador": st.column_config.TextColumn("Jugador", pinned=True, width="medium"),
                "Demarcación": st.column_config.TextColumn("Posición", width="small"),
                "Decisión Once": st.column_config.TextColumn("Decisión Once Inicial", width="medium"),
                "Minutos Semanales": st.column_config.TextColumn("Minutos", width="small"),
                "Sesiones": st.column_config.NumberColumn("Ses.", format="%d"),
                "Dist. Semanal (km)": st.column_config.NumberColumn("Dist. Semanal", format="%.2f km"),
                "HSR Semanal (m)": st.column_config.NumberColumn("HSR >21", format="%d m"),
                "Sprint Semanal (m)": st.column_config.NumberColumn("Sprint >25", format="%d m"),
                "AC.E Semanales": st.column_config.NumberColumn("AC.E", format="%d"),
                "ACWR (EWMA)": st.column_config.NumberColumn("ACWR", format="%.2f"),
                "Ref. 100% DT": st.column_config.NumberColumn("Ref. 100% DT", format="%.1f km"),
                "Ref. 100% HSR": st.column_config.NumberColumn("Ref. 100% HSR", format="%d m"),
                "Recomendación Staff": st.column_config.TextColumn("Pauta de Selección", width="large")
            }
        )

    st.write("")

    # ========================================================
    # 2. CLASIFICACIÓN VISUAL EN 3 ESTADOS (CUERPO TÉCNICO) & SEMÁFORO DE CUMPLIMIENTO
    # ========================================================
    classified_states = get_cached_classified_session_states(
        selected_session_id,
        st.session_state.get("active_ref_session_id")
    )
    c_counts = classified_states.get("counts", {})
    c_groups = classified_states.get("groups", {})
    crit_lbl = classified_states.get("critical_label", "Métrica Diana")
    crit_note = classified_states.get("secondary_note", "")

    st.markdown(f"### 🎯 Clasificación Operativa en 3 Estados ({sess.microcycle_day} | Metodología P.F.)")
    if crit_note:
        st.info(f"📌 **Criterio Metodológico ({sess.microcycle_day}):** Métrica crítica diana = **{crit_lbl}**. {crit_note}")

    # Panel visual de 3 Columnas para el Cuerpo Técnico
    st_col1, st_col2, st_col3 = st.columns(3)

    with st_col1:
        st.markdown(f"""
        <div style="background: rgba(239, 68, 68, 0.08); border-top: 4px solid #EF4444; border-radius: 10px; padding: 14px; border-left: 1px solid rgba(239, 68, 68, 0.2); border-right: 1px solid rgba(239, 68, 68, 0.2); border-bottom: 1px solid rgba(239, 68, 68, 0.2); margin-bottom: 10px;">
            <div style="color: #FCA5A5; font-size: 0.82rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em;">
                🔴 ESTADO 1: DÉFICIT DE ESTÍMULO (&lt;80%)
            </div>
            <div style="color: #EF4444; font-size: 1.8rem; font-weight: 800; margin: 4px 0;">
                {c_counts.get('deficit', 0)} <span style="font-size: 0.9rem; font-weight: 500; color: #94A3B8;">jugadores</span>
            </div>
            <div style="color: #94A3B8; font-size: 0.76rem;">
                No alcanzaron el 80% en <b>{crit_lbl}</b>. Requieren compensación.
            </div>
        </div>
        """, unsafe_allow_html=True)
        def_list = c_groups.get("deficit", [])
        if def_list:
            for p in def_list:
                st.markdown(f"""
                <div style="background: #1E293B; border-left: 3px solid #EF4444; border-radius: 6px; padding: 8px 10px; margin-top: 6px; font-size: 0.82rem;">
                    <b>#{p['dorsal']} {p['name'].upper()}</b> <span style="color:#94A3B8; font-size:0.75rem;">({p['position']})</span><br>
                    <span style="color: #F87171; font-weight: 600;">{p['detail_str']}</span><br>
                    <span style="color: #64748B; font-size: 0.72rem;">{p['secondary_str']}</span>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.success("✨ Ningún jugador con déficit en la métrica rectora.")

    with st_col2:
        st.markdown(f"""
        <div style="background: rgba(16, 185, 129, 0.08); border-top: 4px solid #10B981; border-radius: 10px; padding: 14px; border-left: 1px solid rgba(16, 185, 129, 0.2); border-right: 1px solid rgba(16, 185, 129, 0.2); border-bottom: 1px solid rgba(16, 185, 129, 0.2); margin-bottom: 10px;">
            <div style="color: #6EE7B7; font-size: 0.82rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em;">
                🟢 ESTADO 2: EN RANGO ÓPTIMO (80% - 115%)
            </div>
            <div style="color: #10B981; font-size: 1.8rem; font-weight: 800; margin: 4px 0;">
                {c_counts.get('optimal', 0)} <span style="font-size: 0.9rem; font-weight: 500; color: #94A3B8;">jugadores</span>
            </div>
            <div style="color: #94A3B8; font-size: 0.76rem;">
                Asimilaron la dosis prevista en <b>{crit_lbl}</b> para la adaptación táctica.
            </div>
        </div>
        """, unsafe_allow_html=True)
        opt_list = c_groups.get("optimal", [])
        if opt_list:
            for p in opt_list:
                st.markdown(f"""
                <div style="background: #1E293B; border-left: 3px solid #10B981; border-radius: 6px; padding: 8px 10px; margin-top: 6px; font-size: 0.82rem;">
                    <b>#{p['dorsal']} {p['name'].upper()}</b> <span style="color:#94A3B8; font-size:0.75rem;">({p['position']})</span><br>
                    <span style="color: #34D399; font-weight: 600;">{p['detail_str']}</span><br>
                    <span style="color: #64748B; font-size: 0.72rem;">{p['secondary_str']}</span>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.caption("Ningún jugador en este rango.")

    with st_col3:
        st.markdown(f"""
        <div style="background: rgba(245, 158, 11, 0.08); border-top: 4px solid #F59E0B; border-radius: 10px; padding: 14px; border-left: 1px solid rgba(245, 158, 11, 0.2); border-right: 1px solid rgba(245, 158, 11, 0.2); border-bottom: 1px solid rgba(245, 158, 11, 0.2); margin-bottom: 10px;">
            <div style="color: #FCD34D; font-size: 0.82rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em;">
                🟠 ESTADO 3: SOBRE-ESTÍMULO / ALERTA (&gt;115%)
            </div>
            <div style="color: #F59E0B; font-size: 1.8rem; font-weight: 800; margin: 4px 0;">
                {c_counts.get('excess', 0)} <span style="font-size: 0.9rem; font-weight: 500; color: #94A3B8;">jugadores</span>
            </div>
            <div style="color: #94A3B8; font-size: 0.76rem;">
                Superaron el 115% de <b>{crit_lbl}</b>. Alerta al preparador de posible sobrecarga.
            </div>
        </div>
        """, unsafe_allow_html=True)
        exc_list = c_groups.get("excess", [])
        if exc_list:
            for p in exc_list:
                st.markdown(f"""
                <div style="background: #1E293B; border-left: 3px solid #F59E0B; border-radius: 6px; padding: 8px 10px; margin-top: 6px; font-size: 0.82rem;">
                    <b>#{p['dorsal']} {p['name'].upper()}</b> <span style="color:#94A3B8; font-size:0.75rem;">({p['position']})</span><br>
                    <span style="color: #FBBF24; font-weight: 600;">{p['detail_str']} ⚠️</span><br>
                    <span style="color: #64748B; font-size: 0.72rem;">{p['secondary_str']}</span>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.success("✨ Ningún jugador sobre-estimulado en exceso.")

    st.write("")

    # Tabla Desglosada Individual con Filtros
    df_indiv_compliance = get_cached_individual_compliance(selected_session_id)
    day_cfg = MICROCYCLE_MATCH_TARGETS.get(sess.microcycle_day, MICROCYCLE_MATCH_TARGETS.get("MD", {}))
    day_desc = day_cfg.get("description", MICROCYCLE_DESCRIPTIONS.get(sess.microcycle_day, "Trabajo específico del microciclo"))
    day_metric_label = day_cfg.get("key_label", day_cfg.get("primary_label", "Carga clave"))
    day_pct = day_cfg.get("target_pct", 100.0)

    st.markdown(f"#### 📊 Detalle de Cumplimiento Individual de la Plantilla ({sess.microcycle_day})")

    if not df_indiv_compliance.empty:
        col_ci1, col_ci2 = st.columns([1, 1])
        with col_ci1:
            ci_pos_filter = st.multiselect("Filtrar demarcación:", POSITIONS, default=POSITIONS, key="ci_pos_filter")
        with col_ci2:
            ci_status_filter = st.selectbox(
                "Filtrar por Diagnóstico de Estímulo:",
                ["Todos", "🔴 Con Déficit de Estímulo", "🟢 Estímulo Óptimo Cumplido", "🟠 Con Sobre-estímulo / Fatiga"],
                key="ci_status_filter"
            )

        df_ci_display = df_indiv_compliance[df_indiv_compliance["position"].isin(ci_pos_filter)].copy()
        if ci_status_filter != "Todos":
            if "Déficit" in ci_status_filter:
                df_ci_display = df_ci_display[df_ci_display["diagnosis"].str.contains("Déficit", na=False)]
            elif "Cumplido" in ci_status_filter or "Óptimo" in ci_status_filter:
                df_ci_display = df_ci_display[df_ci_display["diagnosis"].str.contains("Cumplido|Correcta|Óptimo|Adecuada", na=False)]
            elif "Sobre-estímulo" in ci_status_filter or "Fatiga" in ci_status_filter:
                df_ci_display = df_ci_display[df_ci_display["diagnosis"].str.contains("Sobre-estímulo|Exceso|Sobrecarga", na=False)]

        df_table_ci = df_ci_display[[
            "player_name", "position", "dorsal",
            "comp_pct_td", "comp_pct_hsr", "comp_pct_eff",
            "diagnosis", "val_real_formatted", "val_target_formatted", "val_match_100_formatted", "peak_match_name"
        ]].copy()
        df_table_ci.columns = [
            "Jugador", "Posición", "Dorsal",
            "% Cumpl. DT", "% Cumpl. HSR", "% Cumpl. AC.E",
            "Diagnóstico de Estímulo", f"Real ({day_metric_label})",
            f"Prescrito ({day_pct}%)", "Partido Récord (100%)", "Partido Referencia"
        ]

        def highlight_diag(val):
            s = str(val)
            if "Déficit" in s:
                return "background-color: rgba(239, 68, 68, 0.15); color: #FCA5A5; font-weight: 600; border-radius: 9999px; padding: 2px 8px;"
            elif "Sobre" in s or "Exceso" in s or "Sobrecarga" in s:
                return "background-color: rgba(245, 158, 11, 0.15); color: #FCD34D; font-weight: 600; border-radius: 9999px; padding: 2px 8px;"
            elif "Cumplido" in s or "Correcta" in s or "Óptimo" in s or "Adecuada" in s:
                return "background-color: rgba(16, 185, 129, 0.15); color: #6EE7B7; font-weight: 600; border-radius: 9999px; padding: 2px 8px;"
            return ""

        def highlight_metric_pct(val):
            try:
                v = float(val)
                if v < 80.0:
                    return "background-color: rgba(239, 68, 68, 0.12); color: #F87171; font-weight: 600; border-radius: 6px; padding: 2px 6px;"
                elif v > 115.0:
                    return "background-color: rgba(245, 158, 11, 0.12); color: #FBBF24; font-weight: 600; border-radius: 6px; padding: 2px 6px;"
                else:
                    return "background-color: rgba(16, 185, 129, 0.12); color: #34D399; font-weight: 600; border-radius: 6px; padding: 2px 6px;"
            except Exception:
                return ""

        st.dataframe(
            df_table_ci.style
            .format({
                "% Cumpl. DT": "{:.1f}%",
                "% Cumpl. HSR": "{:.1f}%",
                "% Cumpl. AC.E": "{:.1f}%"
            })
            .map(highlight_diag, subset=["Diagnóstico de Estímulo"])
            .map(highlight_metric_pct, subset=["% Cumpl. DT", "% Cumpl. HSR", "% Cumpl. AC.E"]),
            column_config={
                "Jugador": st.column_config.TextColumn("Jugador", pinned=True, width="medium"),
                "Posición": st.column_config.TextColumn("Posición", width="small"),
                "Dorsal": st.column_config.TextColumn("Nº", width="small"),
                "Diagnóstico de Estímulo": st.column_config.TextColumn("Diagnóstico de Estímulo", width="large"),
                "Partido Referencia": st.column_config.TextColumn("Partido Referencia", width="medium"),
            },
            width="stretch",
            hide_index=True
        )

        # Comparativa Completa Real vs Meta (Metodología Excel Preparador Físico)
        with st.expander("📋 Ver Comparativa Completa Real vs. Mínimo Prescrito (Metodología Excel P.F.)", expanded=False):
            st.caption(
                "Contraste cuantitativo de todas las variables del Excel: #ACC EXPL, #DCC EXPL, Distancia Total (km), "
                "HSR (m) y Metros en Sprint respecto a la referencia seleccionada."
            )
            df_post_multi = get_cached_post_session_multivariable_table(
                selected_session_id,
                st.session_state.get("active_ref_session_id")
            )
            if not df_post_multi.empty:
                def highlight_post_cell(val):
                    try:
                        v = float(val)
                        if v < 80.0:
                            return "background-color: rgba(239, 68, 68, 0.14); color: #FCA5A5; font-weight: 600; border-radius: 6px; padding: 2px 6px;"
                        elif v > 115.0:
                            return "background-color: rgba(245, 158, 11, 0.14); color: #FCD34D; font-weight: 600; border-radius: 6px; padding: 2px 6px;"
                        else:
                            return "background-color: rgba(16, 185, 129, 0.14); color: #6EE7B7; font-weight: 600; border-radius: 6px; padding: 2px 6px;"
                    except Exception:
                        return ""

                st.dataframe(
                    df_post_multi.style
                    .format({
                        "DT Real (km)": "{:.2f}",
                        "DT Meta (km)": "{:.2f}",
                        "% DT": "{:.1f}%",
                        "HSR Real (m)": "{:.0f}",
                        "HSR Meta (m)": "{:.0f}",
                        "% HSR": "{:.1f}%",
                        "Sprint Real (m)": "{:.0f}",
                        "Sprint Meta (m)": "{:.0f}",
                        "% Sprint": "{:.1f}%",
                        "% ACC": "{:.1f}%",
                        "% DCC": "{:.1f}%"
                    })
                    .map(highlight_diag, subset=["Diagnóstico de Estímulo"])
                    .map(highlight_post_cell, subset=["% DT", "% HSR", "% Sprint", "% ACC", "% DCC"]),
                    column_config={
                        "Jugador": st.column_config.TextColumn("Jugador", pinned=True, width="medium"),
                        "Posición": st.column_config.TextColumn("Posición", width="small"),
                        "Diagnóstico de Estímulo": st.column_config.TextColumn("Diagnóstico de Estímulo", width="large"),
                        "Entreno/Partido Referencia": st.column_config.TextColumn("Entreno/Partido Referencia", width="medium"),
                    },
                    width="stretch",
                    hide_index=True
                )
                col_em1, col_em2 = st.columns([2.5, 1.5])
                with col_em2:
                    try:
                        from src.services.excel_exporter import export_dataframe_to_formatted_excel
                        excel_post = export_dataframe_to_formatted_excel(
                            df=df_post_multi,
                            sheet_name="Real vs Prescrito",
                            header_color="1E3A8A"
                        )
                        st.download_button(
                            label="📊 Descargar Comparativa (.xlsx)",
                            data=excel_post,
                            file_name=f"comparativa_real_vs_meta_{sess.date}_{sess.microcycle_day}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            use_container_width=True
                        )
                    except Exception as e_xl:
                        st.caption(f"Aviso Excel: {e_xl}")
    else:
        st.info("Sin registros de prescripción individual disponibles para esta sesión.")

    st.write("")
    st.divider()

    # ========================================================
    # 3. MONITOR DE CARGA COMPLETO Y FILTROS
    # ========================================================
    # Filtros para la tabla general
    col_f1, col_f2 = st.columns([1, 1])
    with col_f1:
        filter_pos = st.multiselect("Filtrar por Demarcación:", POSITIONS, default=POSITIONS)
    with col_f2:
        acwr_filter = st.selectbox(
            "Filtrar por Estado de Fatiga (ACWR):",
            ["Todos", "Sobrecarga / Peligro (Rojo)", "Precaución / Fatiga (Amarillo)", "Óptimo (Sweet Spot)", "Subentrenamiento"]
        )

    # Filtrar dataframe
    df_filtered = df_metrics[df_metrics["position"].isin(filter_pos)].copy()
    if acwr_filter != "Todos":
        filter_term = acwr_filter.split(" (")[0]
        df_filtered = df_filtered[df_filtered["acwr_status"].str.contains(filter_term, case=False, na=False)]

    # Leyenda visual del semáforo fisiológico
    st.markdown(render_semaforo_legend_html(), unsafe_allow_html=True)

    with st.expander("ℹ️ ¿Cómo interpretar los semáforos de la tabla (% Cumplimiento, Z-Score y RPE)?"):
        col_exp1, col_exp2 = st.columns(2)
        with col_exp1:
            st.markdown("""
            **🎯 Semáforo de % Cumplimiento Planificado:**
            * 🟢 **88% – 112% (Objetivo Cumplido):** Carga realizada coincide con la prescrita para el día del microciclo.
            * 🟡 **75% – 87% o 113% – 125% (Precaución):** Desviación moderada por defecto o exceso.
            * 🔴 **< 75% o > 125% (Alerta):** Déficit severo o sobrecarga excesiva no planificada.
            """)
        with col_exp2:
            st.markdown("""
            **⏱️ Carga Interna (sRPE de Foster):**
            * Multiplica la nota subjetiva de esfuerzo (1-10) por los minutos entrenados: $\\text{sRPE} = \\text{RPE} \\times \\text{min}$.
            * Si un jugador tiene un RPE alto (7-10) con una distancia GPS normal, indica **fatiga neuromuscular oculta** o necesidad de descanso.
            """)

    st.subheader(f"Telemetría GPS Completa de la Sesión ({len(df_filtered)} jugadores)")

    # Asegurar que todas las columnas necesarias existan en el DataFrame
    if "compliance_pct" in df_filtered.columns:
        df_filtered["global_compliance"] = df_filtered["compliance_pct"].fillna(100.0)
    elif "global_compliance" not in df_filtered.columns:
        df_filtered["global_compliance"] = 100.0

    if "acwr" not in df_filtered.columns:
        df_filtered["acwr"] = 1.0
    if "acwr_status" not in df_filtered.columns:
        df_filtered["acwr_status"] = "Óptimo Sweet Spot (0.80-1.30)"

    for col_req in ["dorsal", "player_name", "position", "total_distance", "hsr_distance", "hmld", "acc_dec_eff", "max_speed"]:
        if col_req not in df_filtered.columns:
            df_filtered[col_req] = 0

    has_rpe = "rpe" in df_filtered.columns and df_filtered["rpe"].dropna().count() > 0
    if has_rpe:
        display_df = df_filtered[[
            "dorsal", "player_name", "position", "total_distance", "hsr_distance",
            "hmld", "acc_dec_eff", "max_speed", "rpe", "srpe", "global_compliance", "acwr", "acwr_status"
        ]].copy()
        display_df.columns = [
            "Dorsal", "Jugador", "Posición", "DT (m)", "HSR (m)",
            "HMLD (m)", "AC.E", "Vmax (km/h)", "RPE", "sRPE (AU)", "% Cumpl.", "ACWR", "Estado Fatiga"
        ]
        format_map = {
            "DT (m)": "{:.0f}",
            "HSR (m)": "{:.0f}",
            "HMLD (m)": "{:.0f}",
            "AC.E": "{:d}",
            "Vmax (km/h)": "{:.1f}",
            "RPE": lambda x: f"{x:.1f}" if pd.notna(x) and x > 0 else "-",
            "sRPE (AU)": lambda x: f"{x:.0f}" if pd.notna(x) and x > 0 else "-",
            "% Cumpl.": "{:.1f}%",
            "ACWR": "{:.2f}"
        }
    else:
        display_df = df_filtered[[
            "dorsal", "player_name", "position", "total_distance", "hsr_distance",
            "hmld", "acc_dec_eff", "max_speed", "global_compliance", "acwr", "acwr_status"
        ]].copy()
        display_df.columns = [
            "Dorsal", "Jugador", "Posición", "DT (m)", "HSR (m)",
            "HMLD (m)", "AC.E", "Vmax (km/h)", "% Cumpl.", "ACWR", "Estado Fatiga"
        ]
        format_map = {
            "DT (m)": "{:.0f}",
            "HSR (m)": "{:.0f}",
            "HMLD (m)": "{:.0f}",
            "AC.E": "{:d}",
            "Vmax (km/h)": "{:.1f}",
            "% Cumpl.": "{:.1f}%",
            "ACWR": "{:.2f}"
        }

    # Estilizado visual en Streamlit
    def highlight_status(val):
        if "Sobrecarga" in str(val) or "Peligro" in str(val):
            return "background-color: rgba(239, 68, 68, 0.15); color: #FCA5A5; font-weight: 600; border-radius: 9999px; padding: 2px 8px;"
        elif "Precaución" in str(val) or "Fatiga" in str(val):
            return "background-color: rgba(245, 158, 11, 0.15); color: #FCD34D; font-weight: 600; border-radius: 9999px; padding: 2px 8px;"
        elif "Óptimo" in str(val) or "Sweet" in str(val):
            return "background-color: rgba(16, 185, 129, 0.15); color: #6EE7B7; font-weight: 600; border-radius: 9999px; padding: 2px 8px;"
        elif "Subentrenamiento" in str(val):
            return "background-color: rgba(56, 189, 248, 0.15); color: #7DD3FC; font-weight: 600; border-radius: 9999px; padding: 2px 8px;"
        return ""

    def highlight_compliance(val):
        try:
            v = float(val)
            if v < 75.0 or v > 125.0:
                return "background-color: rgba(239, 68, 68, 0.14); color: #F87171; font-weight: 600; border-radius: 6px; padding: 2px 6px;"
            elif v < 88.0 or v > 112.0:
                return "background-color: rgba(245, 158, 11, 0.14); color: #FBBF24; font-weight: 600; border-radius: 6px; padding: 2px 6px;"
            else:
                return "background-color: rgba(16, 185, 129, 0.14); color: #34D399; font-weight: 600; border-radius: 6px; padding: 2px 6px;"
        except Exception:
            return ""

    st.dataframe(
        display_df.style
        .format(format_map)
        .map(highlight_status, subset=["Estado Fatiga"])
        .map(highlight_compliance, subset=["% Cumpl."]),
        width="stretch",
        hide_index=True
    )

    st.write("")
    st.divider()

    # Gráficos de cumplimiento y Z-scores
    col_g1, col_g2 = st.columns(2)

    with col_g1:
        st.subheader("Cumplimiento Real vs. Planificado")
        df_comp = calculate_compliance_table(df_metrics, targets)
        fig_comp = create_compliance_chart(df_comp)
        st.plotly_chart(fig_comp, width="stretch")

    with col_g2:
        st.subheader("Detección de Desviaciones (Z-Score)")
        metric_choice = st.selectbox(
            "Métrica para cálculo de Z-Score:",
            [("hsr_distance", "Carrera Alta Velocidad (HSR)"), ("total_distance", "Distancia Total (DT)")],
            format_func=lambda x: x[1]
        )
        fig_z = create_zscore_chart(df_metrics, metric_col=metric_choice[0])
        st.plotly_chart(fig_z, width="stretch")


# ==========================================
# VISTA: PERFIL INDIVIDUAL DEL JUGADOR & EVOLUCIÓN LONGITUDINAL
# ==========================================
elif menu == "👤 Perfil Individual del Jugador":
    st.markdown("""
    <div style="background: #1E293B; border: 1px solid #334155; border-radius: 12px; padding: 20px 24px; margin-bottom: 20px; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.2);">
        <div style="color: #38BDF8; font-size: 0.74rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em;">Fisiología y Control Individualizado</div>
        <h2 style="color: #F8FAFC; margin: 3px 0 6px 0; font-size: 1.45rem; font-weight: 700; letter-spacing: -0.02em;">
            Perfil Integral del Jugador &amp; Evolución Longitudinal
        </h2>
        <div style="color: #94A3B8; font-size: 0.85rem; line-height: 1.5;">
            Monitoreo sesión a sesión de todas las variables registradas por Ubiko contrastadas con el techo individual del jugador (100%), las demandas posicionales y la matriz oficial de microciclo del Salerm Puente Genil (Mesociclos 1 y 2). Incluye diagnóstico de cumplimiento (Déficit, En Rango, Sobrecarga) y seguimiento longitudinal de 4 semanas.
        </div>
    </div>
    """, unsafe_allow_html=True)

    players_data = get_cached_players_list()
    player_dict = {f"#{dorsal} {name} ({pos})": p_id for p_id, dorsal, name, pos, _ in players_data}

    col_sel1, col_sel2 = st.columns([2, 1])
    with col_sel1:
        sel_player_label = st.selectbox("Seleccionar Futbolista:", list(player_dict.keys()), key="indiv_profile_player")
        sel_player_id = player_dict[sel_player_label]

    profile = get_cached_player_individual_profile(sel_player_id)
    if not profile:
        st.warning("No se encontraron registros para este futbolista.")
        st.stop()

    peak = profile["peak"]
    acwr = profile["acwr"]
    pos_bm = profile["position_benchmark"]
    alerts = profile.get("alerts", [])
    weeks = profile.get("weeks_summary", [])
    history = profile.get("sessions_history", [])

    # 1. TARJETAS EJECUTIVAS SUPERIORES (KPIS CLAVE)
    k1, k2, k3, k4 = st.columns(4)
    with k1:
        st.markdown(f"""
        <div class="metric-card" style="border-left: 4px solid #38BDF8;">
            <div class="metric-title">Techo Máx. Exigencia (100%)</div>
            <div class="metric-value">{peak['td_km']} km</div>
            <div class="metric-subtitle">Récord: {peak['session_name']} ({peak['minutes']:.0f}')</div>
        </div>
        """, unsafe_allow_html=True)
    with k2:
        st.markdown(f"""
        <div class="metric-card" style="border-left: 4px solid #818CF8;">
            <div class="metric-title">Velocidad Máxima / Perfil</div>
            <div class="metric-value">{peak['vmax']:.2f} km/h</div>
            <div class="metric-subtitle">Posición: {profile['position']} (HSR máx: {peak['hsr_m']:.0f}m)</div>
        </div>
        """, unsafe_allow_html=True)
    with k3:
        st.markdown(f"""
        <div class="metric-card" style="border-left: 4px solid {acwr['color']};">
            <div class="metric-title">Ratio ACWR Actual (EWMA)</div>
            <div class="metric-value" style="color: {acwr['color']};">{acwr['val']:.2f}</div>
            <div class="metric-subtitle">{acwr['status']}</div>
        </div>
        """, unsafe_allow_html=True)
    with k4:
        st.markdown(f"""
        <div class="metric-card" style="border-left: 4px solid #F59E0B;">
            <div class="metric-title">Carga Aguda vs. Crónica</div>
            <div class="metric-value">{acwr['acute']:.0f} m / {acwr['chronic']:.0f} m</div>
            <div class="metric-subtitle">Fatiga 7d vs. Fitness base 28d</div>
        </div>
        """, unsafe_allow_html=True)

    st.write("")

    # 2. BANNER DE ALERTAS PREVENTIVAS DEL CUERPO TÉCNICO
    if alerts:
        st.markdown("##### 🚨 Alertas de Seguimiento de Carga y Precaución:")
        for al in alerts:
            al_color = "#EF4444" if al["level"] == "danger" else ("#F59E0B" if al["level"] == "warning" else "#10B981")
            al_bg = "rgba(239, 68, 68, 0.12)" if al["level"] == "danger" else ("rgba(245, 158, 11, 0.12)" if al["level"] == "warning" else "rgba(16, 185, 129, 0.12)")
            st.markdown(f"""
            <div style="background: {al_bg}; border-left: 4px solid {al_color}; padding: 12px 18px; border-radius: 8px; margin-bottom: 10px; font-size: 0.88rem;">
                <strong style="color: {al_color}; font-size: 0.95rem;">{al['title']}</strong>
                <div style="color: #E2E8F0; margin-top: 4px;">{al['message']}</div>
                <div style="color: #94A3B8; margin-top: 4px; font-weight: 500;">
                    💡 <strong>Acción Recomendada:</strong> {al['recommendation']}
                </div>
            </div>
            """, unsafe_allow_html=True)
        st.write("")

    # 3. PESTAÑAS DE CONTENIDO ANALÍTICO
    tab_p1, tab_p2, tab_p3 = st.tabs([
        "📋 Histórico Sesión a Sesión (Matriz Ubiko)",
        "📈 Evolución de las Últimas 4 Semanas",
        "🤖 Dictamen Individual de IA (Cuerpo Técnico)"
    ])

    # PESTAÑA 1: HISTÓRICO SESIÓN A SESIÓN
    with tab_p1:
        st.subheader("Histórico Detallado Sesión a Sesión")
        st.caption("Todas las métricas registradas por los chalecos GPS de Ubiko contrastadas con el rango planificado del microciclo:")

        col_fil1, col_fil2 = st.columns([1.5, 2.5])
        with col_fil1:
            sess_filter = st.selectbox(
                "Filtrar por tipo de sesión:",
                ["Todas las sesiones", "Solo Partidos (MD)", "Solo Entrenamientos"],
                key="indiv_sess_filter"
            )

        filtered_history = history
        if sess_filter == "Solo Partidos (MD)":
            filtered_history = [s for s in history if s["session_type"] == "Partido" or s["microcycle_day"] == "MD"]
        elif sess_filter == "Solo Entrenamientos":
            filtered_history = [s for s in history if s["session_type"] != "Partido" and s["microcycle_day"] != "MD"]

        if filtered_history:
            df_display_sessions = pd.DataFrame([
                {
                    "Fecha": s["date_str"],
                    "Sesión": s["session_name"],
                    "Día Micro": s["microcycle_day"],
                    "Tiempo": f"{s['minutes']:.0f}'",
                    "Distancia (km)": f"{s['distance_km']:.2f}",
                    "Ritmo (m/min)": f"{s['pace_m_min']:.1f}",
                    "V. Máx (km/h)": f"{s['max_speed']:.2f}",
                    "HSR (m)": f"{s['hsr_m']:.0f}",
                    "Sprint (m)": f"{s['sprint_m']:.0f}",
                    "#Sprints": s["sprints_cnt"],
                    "ACC / DCC": f"{s['acc_eff']} / {s['dec_eff']}",
                    "AC.E Totales": s["total_eff"],
                    "RPE": f"{s['rpe']:.0f}" if s["rpe"] else "-",
                    "% Techo DT": f"{s['pct_peak_td']:.0f}%",
                    "% Techo HSR": f"{s['pct_peak_hsr']:.0f}%",
                    "Estado Microciclo": s["status_badge"],
                    "Diagnóstico Fisiológico": s["eval_text"]
                }
                for s in filtered_history
            ])

            st.dataframe(
                df_display_sessions,
                hide_index=True,
                use_container_width=True
            )

            # Botón de descarga de la tabla del jugador
            csv_data = df_display_sessions.to_csv(index=False).encode("utf-8")
            st.download_button(
                f"📥 Descargar Histórico de {profile['name']} (CSV)",
                data=csv_data,
                file_name=f"historico_{profile['name'].lower().replace(' ', '_')}.csv",
                mime="text/csv",
                key="btn_download_indiv_csv"
            )
        else:
            st.info("No hay sesiones que coincidan con el filtro seleccionado.")

        st.write("")
        # Expander de consulta de la Matriz Oficial Salerm Puente Genil
        with st.expander("📖 Consultar Matriz Oficial de Parámetros Referenciales (Salerm Puente Genil - Mesociclos 1 y 2)"):
            st.markdown("""
            Valores objetivo establecidos por el preparador físico para cada día del microciclo competitivo:
            """)
            matrix_rows = []
            for d_k, d_v in SALERM_PUENTE_GENIL_MATRIX.items():
                matrix_rows.append({
                    "Día Microciclo": d_v["label"],
                    "Objetivo / Foco": d_v["objective"],
                    "Distancia (km)": f"{d_v['dist_km_min']} - {d_v['dist_km_max']} km" if d_v['dist_km_max'] > 0 else "Reset (0)",
                    "Ritmo (m/min)": f"{d_v['m_min_min']:.0f} - {d_v['m_min_max']:.0f}" if d_v['m_min_max'] > 0 else "-",
                    "HSR (m)": f"{d_v['hsr_min']:.0f} - {d_v['hsr_max']:.0f} m" if d_v['hsr_max'] > 0 else "-",
                    "Sprint (m)": f"{d_v['sprint_m_min']:.0f} - {d_v['sprint_m_max']:.0f} m" if d_v['sprint_m_max'] > 0 else "-",
                    "#Sprints": f"{d_v['sprints_cnt_min']} - {d_v['sprints_cnt_max']}" if d_v['sprints_cnt_max'] > 0 else "-",
                    "ACC / DCC": f"{d_v['acc_target']} / {d_v['dec_target']}" if d_v['acc_target'] > 0 else "-",
                    "RPE": f"{d_v['rpe_target']}" if d_v['rpe_target'] > 0 else "-"
                })
            st.dataframe(pd.DataFrame(matrix_rows), hide_index=True, use_container_width=True)

    # PESTAÑA 2: EVOLUCIÓN 4 SEMANAS
    with tab_p2:
        st.subheader("Dinámica y Acumulación en las Últimas 4 Semanas")
        st.caption("Control de la carga acumulada semanal para detectar si la fatiga o desentrenamiento vienen de semanas previas:")

        if weeks:
            df_weeks = pd.DataFrame([
                {
                    "Semana": w["label"],
                    "Periodo": w["range_str"],
                    "Sesiones": w["sessions_count"],
                    "Distancia (km)": f"{w['total_distance_km']:.2f}",
                    "HSR (m)": f"{w['hsr_distance_m']:.0f}",
                    "Sprint (m)": f"{w['sprint_distance_m']:.0f}",
                    "#Sprints": w["sprints_cnt"],
                    "AC.E Totales": w["total_eff"],
                    "Minutos": f"{w['total_minutes']:.0f}'",
                    "V. Máx (km/h)": f"{w['max_speed']:.2f}",
                    "Estado Carga": w["status"]
                }
                for w in weeks
            ])
            st.dataframe(df_weeks, hide_index=True, use_container_width=True)

            # Gráficos comparativos de las 4 semanas
            col_g1, col_g2 = st.columns(2)
            with col_g1:
                import plotly.graph_objects as go
                fig_w_td = go.Figure()
                week_labels = [w["label"].replace("Semana Actual (En Curso)", "Semana Actual") for w in reversed(weeks)]
                week_tds = [w["total_distance_km"] for w in reversed(weeks)]
                fig_w_td.add_trace(go.Bar(
                    x=week_labels,
                    y=week_tds,
                    marker_color="#0284C7",
                    text=[f"{v:.1f} km" for v in week_tds],
                    textposition="auto"
                ))
                fig_w_td.update_layout(
                    title=f"Volumen Semanal (DT km) - {profile['name']}",
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                    font=dict(color="#F8FAFC"),
                    height=320,
                    margin=dict(l=20, r=20, t=40, b=20),
                    yaxis=dict(gridcolor="#334155", title="Distancia Total (km)")
                )
                st.plotly_chart(fig_w_td, use_container_width=True)

            with col_g2:
                fig_w_hsr = go.Figure()
                week_hsrs = [w["hsr_distance_m"] for w in reversed(weeks)]
                week_sprints = [w["sprint_distance_m"] for w in reversed(weeks)]
                fig_w_hsr.add_trace(go.Bar(
                    name="HSR (>21 km/h)",
                    x=week_labels,
                    y=week_hsrs,
                    marker_color="#F59E0B"
                ))
                fig_w_hsr.add_trace(go.Bar(
                    name="Sprint (>25 km/h)",
                    x=week_labels,
                    y=week_sprints,
                    marker_color="#EF4444"
                ))
                fig_w_hsr.update_layout(
                    title=f"Alta Intensidad Semanal (HSR & Sprint m)",
                    barmode="group",
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                    font=dict(color="#F8FAFC"),
                    height=320,
                    margin=dict(l=20, r=20, t=40, b=20),
                    yaxis=dict(gridcolor="#334155", title="Metros (m)")
                )
                st.plotly_chart(fig_w_hsr, use_container_width=True)

    # PESTAÑA 3: DICTAMEN INDIVIDUAL DE IA
    with tab_p3:
        st.subheader("Dictamen Fisiológico y Prescripción Individual por IA")
        st.caption("Informe técnico-táctico generado exclusivamente para este futbolista, sin compararlo con otros jugadores:")

        st.markdown(f"""
        <div style="background: rgba(30, 41, 59, 0.6); border: 1px solid #334155; padding: 14px 18px; border-radius: 8px; margin-bottom: 16px; font-size: 0.88rem;">
            Analiza el estado de <strong>#{profile['dorsal']} {profile['name']} ({profile['position']})</strong> considerando sus techos de máxima exigencia, su cumplimiento en el microciclo del Salerm Puente Genil y su histórico de las últimas 4 semanas.
        </div>
        """, unsafe_allow_html=True)

        if st.button(f"Generar Dictamen Individual para #{profile['dorsal']} {profile['name']}", type="primary", use_container_width=True, key="btn_gen_indiv_ai"):
            with st.spinner("Analizando telemetría GPS e infiriendo dictamen con Inteligencia Artificial..."):
                from src.services.ai_assistant import AIAssistant
                ai_serv = AIAssistant()
                with get_db() as db_session:
                    indiv_report = ai_serv.generate_individual_player_report(sel_player_id, db_session)
                st.markdown(f'<div class="report-box">{indiv_report}</div>', unsafe_allow_html=True)


# ==========================================
# VISTA: REFERENCIA PARTIDOS (EXCEL PREPARADOR FÍSICO)
# ==========================================
elif menu == "🏟️ Referencia Partidos (Excel P.F.)":
    st.markdown("""
    <div style="background: #1E293B; border: 1px solid #334155; border-radius: 12px; padding: 18px 22px; margin-bottom: 20px; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.2);">
        <div style="color: #38BDF8; font-size: 0.74rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em;">Modelo de Rendimiento Competitivo</div>
        <h2 style="color: #F8FAFC; margin: 3px 0 6px 0; font-size: 1.40rem; font-weight: 700; letter-spacing: -0.02em;">
            Salerm Puente Genil &bull; Datos de Referencia de Partidos
        </h2>
        <div style="color: #94A3B8; font-size: 0.84rem;">
            Estructura oficial de control del preparador físico | Techos de máxima exigencia competitiva por demarcación y rendimiento del equipo.
        </div>
    </div>
    """, unsafe_allow_html=True)

    # 1. Selector de Partido de Referencia Oficial (Exclusivo partidos de Liga)
    ref_matches = get_cached_all_reference_matches(include_individual_peaks=False)
    match_dict = {m["label"]: m["session_id"] for m in ref_matches}

    # Inicializar referencia activa en session_state si no existe o si contenía la opción individual
    if "active_ref_session_id" not in st.session_state or st.session_state.get("active_ref_session_id") not in match_dict.values():
        default_sess_id = ref_matches[0]["session_id"] if ref_matches else None
        default_label = ref_matches[0]["label"] if ref_matches else ""
        st.session_state["active_ref_session_id"] = default_sess_id
        st.session_state["active_ref_match_label"] = default_label

    col_m1, col_m2 = st.columns([2, 1])
    with col_m1:
        labels_list = list(match_dict.keys())
        curr_label = st.session_state.get("active_ref_match_label")
        default_idx = labels_list.index(curr_label) if curr_label in labels_list else 0
        selected_match_label = st.selectbox(
            "Seleccionar Partido Oficial para Visualizar:",
            labels_list,
            index=default_idx,
            help="Muestra exclusivamente las actas oficiales de partidos de Liga disputados por el primer equipo."
        )
        selected_match_id = match_dict[selected_match_label]

    with col_m2:
        st.write("")
        st.write("")
        is_active = (selected_match_id == st.session_state.get("active_ref_session_id"))
        if is_active:
            st.success("✅ Referencia 100% ACTIVA")
        else:
            if st.button("📌 Fijar como Referencia 100% Activa", use_container_width=True, type="primary"):
                st.session_state["active_ref_session_id"] = selected_match_id
                st.session_state["active_ref_match_label"] = selected_match_label
                st.cache_data.clear()
                st.toast("¡Partido fijado como Referencia 100% de la plantilla!", icon="📌")
                st.rerun()

    # 2. Obtener datos de la tabla de referencia
    ref_data_init = get_cached_match_reference_table_data(selected_match_id)
    candidates = ref_data_init.get("top_candidates", [])
    default_top_id = ref_data_init.get("top_player", {}).get("player_id") if ref_data_init.get("top_player") else None

    cand_ids = [c["player_id"] for c in candidates]
    top_key = f"sel_top_{selected_match_id}"
    if top_key not in st.session_state or st.session_state[top_key] not in cand_ids:
        st.session_state[top_key] = default_top_id

    col_top_sel, col_top_info = st.columns([1.8, 1.2])
    with col_top_sel:
        chosen_top_id = st.selectbox(
            "⭐ Jugador TOP de Referencia (Minutos + Distancia + Criterio Cualitativo P.F.):",
            options=cand_ids,
            key=top_key,
            format_func=lambda pid: next((c["label"] for c in candidates if c["player_id"] == pid), str(pid)),
            help="El sistema sugiere automáticamente al jugador con mayor volumen entre los titulares (minutos y distancias). El preparador físico puede modificarlo con un solo clic desplegando esta lista para elegir a cualquier otro futbolista."
        )

    with col_top_info:
        st.caption("ℹ️ **Metodología Oficial del Preparador Físico**")
        st.caption("Filtro por **minutos** (titulares >= 65'), clasificación por **distancia total** y **posición**, con ajuste libre **a ojo cualitativo**.")

    ref_data = get_cached_match_reference_table_data(selected_match_id, top_player_id=chosen_top_id)

    df_disp = ref_data.get("df_display", pd.DataFrame())
    top_p = ref_data.get("top_player")
    team_sum = ref_data.get("team_summary", {})

    if not df_disp.empty:
        # Fila de KPIs del equipo (Estilo Excel del club)
        kpi1, kpi2, kpi3, kpi4, kpi5 = st.columns(5)
        with kpi1:
            st.markdown(f"""
            <div class="metric-card" style="border-left: 4px solid #3B82F6;">
                <div class="metric-title">Distancia Acumulada Equipo</div>
                <div class="metric-value" style="color: #60A5FA;">{team_sum.get('tot_distance_km', 0.0):.2f} KM</div>
                <div class="metric-subtitle">{team_sum.get('num_players', 0)} jugadores evaluados</div>
            </div>
            """, unsafe_allow_html=True)
        with kpi2:
            st.markdown(f"""
            <div class="metric-card" style="border-left: 4px solid #10B981;">
                <div class="metric-title">Pico Velocidad Máxima</div>
                <div class="metric-value" style="color: #34D399;">{team_sum.get('peak_max_speed', 0.0):.2f} <span style="font-size:0.9rem;">km/h</span></div>
                <div class="metric-subtitle">Velocidad punta del equipo</div>
            </div>
            """, unsafe_allow_html=True)
        with kpi3:
            st.markdown(f"""
            <div class="metric-card" style="border-left: 4px solid #F59E0B;">
                <div class="metric-title">Alta Intensidad (HSR)</div>
                <div class="metric-value" style="color: #FBBF24;">{team_sum.get('tot_hsr_m', 0.0):.0f} m</div>
                <div class="metric-subtitle">Metros acumulados >21 km/h</div>
            </div>
            """, unsafe_allow_html=True)
        with kpi4:
            st.markdown(f"""
            <div class="metric-card" style="border-left: 4px solid #EC4899;">
                <div class="metric-title">Total Sprints Equipo</div>
                <div class="metric-value" style="color: #F472B6;">{team_sum.get('tot_sprints', 0)}</div>
                <div class="metric-subtitle">{team_sum.get('tot_sprint_m', 0.0):.0f} m totales al sprint</div>
            </div>
            """, unsafe_allow_html=True)
        with kpi5:
            tot_acc_dec = team_sum.get('tot_acc_expl', 0) + team_sum.get('tot_dcc_expl', 0)
            st.markdown(f"""
            <div class="metric-card" style="border-left: 4px solid #8B5CF6;">
                <div class="metric-title">Esfuerzos Acel / Desacel</div>
                <div class="metric-value" style="color: #A78BFA;">{tot_acc_dec}</div>
                <div class="metric-subtitle">{team_sum.get('tot_acc_expl', 0)} ACC | {team_sum.get('tot_dcc_expl', 0)} DCC</div>
            </div>
            """, unsafe_allow_html=True)

        st.write("")

        # Destacado del JUGADOR TOP
        if top_p:
            st.markdown(f"""
            <div style="background: rgba(239, 68, 68, 0.08); border: 1px solid rgba(239, 68, 68, 0.3); border-radius: 10px; padding: 12px 18px; margin-bottom: 16px; display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 8px;">
                <div style="display: flex; align-items: center; gap: 8px;">
                    <span class="badge-pill danger">JUGADOR TOP DEL PARTIDO</span>
                    <span style="color: #F8FAFC; font-weight: 700; font-size: 0.95rem;">#{top_p['dorsal']} {top_p['player_name'].upper()}</span>
                    <span style="color: #94A3B8; font-size: 0.80rem;">({top_p['position']})</span>
                </div>
                <div style="color: #FCA5A5; font-size: 0.84rem; font-weight: 600;">
                    Distancia: <b>{top_p['distance_km']:.2f} km</b> &bull; Vmax: <b>{top_p['max_speed']:.2f} km/h</b> &bull; HSR: <b>{top_p['hsr_m']:.0f} m</b> &bull; Esfuerzos: <b>{top_p['acc_expl'] + top_p['dcc_expl']}</b>
                </div>
            </div>
            """, unsafe_allow_html=True)

        # Selector de Modo de Visualización (Formato Oficial 6 Roles vs Convocatoria Completa)
        col_vm1, col_vm2 = st.columns([1.3, 1])
        with col_vm1:
            view_mode = st.radio(
                "Estructura de la Tabla:",
                ["📋 Formato Oficial P.F. (6 Roles Referencia)", "👥 Convocatoria Completa (Todos los Jugadores)"],
                horizontal=True,
                help="El Formato Oficial P.F. replica exactamente el Excel del preparador físico con los 6 roles clave y el resumen del equipo."
            )

        if view_mode == "📋 Formato Oficial P.F. (6 Roles Referencia)":
            df_view = ref_data.get("df_display", df_disp).copy()
        else:
            df_full = ref_data.get("df_full", df_disp).copy()
            with col_vm2:
                pos_excel_filter = st.multiselect(
                    "Filtrar por Demarcación:",
                    ["CENTRAL", "LATERAL", "MEDIOCENTRO", "EXTREMO", "DELANTERO"],
                    default=["CENTRAL", "LATERAL", "MEDIOCENTRO", "EXTREMO", "DELANTERO"],
                    key="excel_ref_pos_filter"
                )
            mask = (
                df_full["POSICIÓN"].isin(pos_excel_filter) |
                (df_full["_row_type"].isin(["top", "team"]))
            )
            df_view = df_full[mask].copy()

        cols_clean = [c for c in df_view.columns if not c.startswith("_")]

        def style_excel_match_table(row):
            row_type = row.get("_row_type", "")
            pos = str(row.get("POSICIÓN", ""))
            if row_type == "top" or "⭐" in pos:
                return ["background-color: rgba(239, 68, 68, 0.16); color: #FCA5A5; font-weight: 700; border-top: 1px solid rgba(239, 68, 68, 0.4); border-bottom: 1px solid rgba(239, 68, 68, 0.4);"] * len(row)
            elif row_type == "team" or "EQUIPO" in pos:
                return ["background-color: rgba(30, 58, 138, 0.25); color: #93C5FD; font-weight: 700; border-top: 2px solid #38BDF8;"] * len(row)
            elif row_type == "player_top":
                return ["background-color: rgba(239, 68, 68, 0.08); font-weight: 600;"] * len(row)
            return [""] * len(row)

        st.dataframe(
            df_view.style.apply(style_excel_match_table, axis=1),
            column_order=cols_clean,
            width="stretch",
            hide_index=True
        )

        col_dl1, col_dl2, col_dl3, col_dl4 = st.columns([1.0, 1.3, 1.2, 0.7])
        import re
        safe_fname = re.sub(r'[^\w\-_\.]', '_', selected_match_label.replace("🏟️", "").replace("🏆", "").strip())[:28]

        with col_dl2:
            try:
                from src.services.pdf_generator import generate_match_reference_pdf
                is_full = (view_mode != "📋 Formato Oficial P.F. (6 Roles Referencia)")
                pdf_data = generate_match_reference_pdf(
                    match_title=selected_match_label,
                    df_rows=df_view,
                    is_full_squad=is_full
                )
                st.download_button(
                    label="📄 Descargar PDF Oficial (P.F.)",
                    data=pdf_data,
                    file_name=f"referencia_oficial_{safe_fname}.pdf",
                    mime="application/pdf",
                    type="primary",
                    use_container_width=True,
                    help="Descarga el documento PDF con el diseño y colores idénticos a las tablas del preparador físico."
                )
            except Exception as e_pdf:
                st.error(f"Aviso generando PDF: {e_pdf}")

        with col_dl3:
            try:
                from src.services.excel_exporter import export_dataframe_to_formatted_excel
                excel_ref = export_dataframe_to_formatted_excel(
                    df=df_view,
                    sheet_name=f"Referencia_{safe_fname[:18]}",
                    header_color="1E3A8A"
                )
                st.download_button(
                    label="📊 Descargar Excel (.xlsx)",
                    data=excel_ref,
                    file_name=f"referencia_{safe_fname}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                    help="Descarga el libro de Excel oficial (.xlsx) con los colores, bordes y anchos ajustados."
                )
            except Exception as e_xl:
                st.error(f"Aviso generando Excel: {e_xl}")

        with col_dl4:
            csv_data = df_view[cols_clean].to_csv(index=False, sep=";").encode("utf-8-sig")
            st.download_button(
                "📥 CSV",
                data=csv_data,
                file_name=f"referencia_partido_{selected_match_id or 'record'}.csv",
                mime="text/csv",
                use_container_width=True
            )
    else:
        st.warning("No hay datos de telemetría disponibles para el partido seleccionado.")


# ==========================================
# VISTA: PLANIFICACIÓN PRE-SESIÓN (CALCULADORA DE OBJETIVOS)
# ==========================================
# ==========================================
# VISTA: COMPARATIVA DE SESIÓN VS. EXIGENCIAS DE PARTIDO (50% / 70% / 80%)
# ==========================================
elif menu in ["📋 Planificación & Comparativa (50/70/80%)", "📋 Planificación Pre-Sesión"]:
    st.markdown("""
    <div style="background: linear-gradient(90deg, #1E293B 0%, #0F172A 100%); padding: 18px 22px; border-radius: 12px; border: 1px solid #334155; margin-bottom: 18px;">
        <h2 style="color: #F8FAFC; margin: 0; font-size: 1.35rem;">
            📋 Comparativa de Sesión vs. Exigencias de Partido (50% / 70% / 80%)
        </h2>
        <p style="color: #94A3B8; margin: 6px 0 0 0; font-size: 0.88rem;">
            Metodología del Preparador Físico: Elige la sesión subida desde UBIKO para contrastar el rendimiento GPS real de los jugadores frente al 50%, 70% u 80% de las exigencias del partido oficial.
        </p>
    </div>
    """, unsafe_allow_html=True)

    # 1. Selectores de Sesión a Comparar y Partido de Referencia
    cached_all_sessions = get_cached_sessions()
    session_options_dict = {label: s_id for s_id, label in cached_all_sessions}

    ref_matches = get_cached_all_reference_matches(include_individual_peaks=True)
    match_dict = {m["label"]: m["session_id"] for m in ref_matches}

    if not session_options_dict:
        st.warning("No hay sesiones en la base de datos para comparar.")
        st.stop()

    col_cs1, col_cs2 = st.columns([1.5, 1.5])
    with col_cs1:
        sess_labels = list(session_options_dict.keys())
        default_sess_idx = 0
        if selected_session_id:
            for idx, (lbl, sid) in enumerate(session_options_dict.items()):
                if sid == selected_session_id:
                    default_sess_idx = idx
                    break
        sel_cmp_label = st.selectbox(
            "⚽ Sesión Realizada a Comparar:",
            sess_labels,
            index=default_sess_idx,
            key="cmp_session_select",
            help="Selecciona la sesión de entrenamiento subida desde UBIKO para analizar el rendimiento."
        )
        cmp_session_id = session_options_dict[sel_cmp_label]

    with col_cs2:
        match_labels = list(match_dict.keys())
        curr_ref_label = st.session_state.get("active_ref_match_label")
        default_ref_idx = match_labels.index(curr_ref_label) if curr_ref_label in match_labels else 0
        sel_cmp_ref_label = st.selectbox(
            "🏟️ Partido de Referencia (Base 100% Exigencias):",
            match_labels,
            index=default_ref_idx,
            key="cmp_ref_match_select",
            help="Selecciona sobre qué partido oficial se aplicarán los porcentajes del 50%, 70% y 80%."
        )
        cmp_ref_id = match_dict[sel_cmp_ref_label]

    # Metadatos de la sesión seleccionada
    summary_cmp = get_cached_session_summary(cmp_session_id)
    if summary_cmp and "session" in summary_cmp:
        s_obj = summary_cmp["session"]
        m_list = summary_cmp.get("metrics", pd.DataFrame())
        st.markdown(f"""
        <div style="background: #1E293B; border: 1px solid #334155; border-radius: 10px; padding: 12px 18px; margin-bottom: 14px; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px;">
            <div style="font-weight: 600; color: #F8FAFC; font-size: 0.90rem;">
                Sesión: <span style="color: #38BDF8;">{s_obj.name}</span>
            </div>
            <div style="display: flex; gap: 6px; flex-wrap: wrap;">
                <span class="badge-pill" style="background: rgba(15, 23, 42, 0.6); border: 1px solid #334155; color: #E2E8F0;">📅 {s_obj.date.strftime('%d/%m/%Y')}</span>
                <span class="badge-pill info">⚡ {s_obj.microcycle_day}</span>
                <span class="badge-pill" style="background: rgba(15, 23, 42, 0.6); border: 1px solid #334155; color: #E2E8F0;">⏱️ {s_obj.duration_minutes} min</span>
                <span class="badge-pill optimal">👥 {len(m_list)} futbolistas</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

    # 2. Filtros Interactivos (colocados arriba de las pestañas)
    col_f1, col_f2 = st.columns([1.0, 1.4])
    with col_f1:
        pos_filter = st.multiselect(
            "Filtrar por Demarcación:",
            ["CENTRAL", "LATERAL", "MEDIOCENTRO", "EXTREMO", "DELANTERO", "PORTERO"],
            default=["CENTRAL", "LATERAL", "MEDIOCENTRO", "EXTREMO", "DELANTERO"],
            key="cmp_global_pos_filter"
        )
    with col_f2:
        status_filter = st.radio(
            "⚡ Filtro Rápido de Estado:",
            ["Todos", "🔴 Mostrar solo en Déficit", "🟠 Mostrar solo Sobre-estímulo", "🟢 Mostrar solo Óptimo"],
            horizontal=True,
            key="cmp_global_status_filter_pills",
            help="Filtra a los futbolistas a un solo clic según su respuesta fisiológica."
        )

    st.write("")

    # 3. Elección de Pestañas (debajo de los filtros): 50%, 70% y 80%
    tab_50, tab_70, tab_80 = st.tabs([
        "🟢 Comparación al 50% (Carga Baja)",
        "🟡 Comparación al 70% (Carga Media)",
        "🔴 Comparación al 80% (Carga Alta / Máx. Estímulo)"
    ])

    def render_level_tab_content(lvl_val: int, tab_title: str, tab_badge: str, tab_desc: str, border_col: str):
        st.markdown(f"""
        <div style="background: rgba(30, 41, 59, 0.65); padding: 14px 18px; border-radius: 10px; border-left: 5px solid {border_col}; margin-bottom: 16px;">
            <div style="font-weight: bold; color: #F8FAFC; font-size: 1.05rem;">{tab_badge} — {tab_title}</div>
            <div style="margin-top: 4px; color: #94A3B8; font-size: 0.85rem;">{tab_desc}</div>
        </div>
        """, unsafe_allow_html=True)

        df_level = get_cached_post_session_multivariable_table(cmp_session_id, cmp_ref_id, level=lvl_val)

        if df_level.empty:
            st.warning(f"No hay datos de telemetría de futbolistas para calcular la comparativa al {lvl_val}%.")
            return

        # Aplicar filtros
        df_view = df_level[df_level["Posición"].isin(pos_filter)].copy()
        if "Déficit" in status_filter:
            df_view = df_view[df_view["Estado"] == "Déficit"]
        elif "Sobre" in status_filter:
            df_view = df_view[df_view["Estado"] == "Sobre-estímulo"]
        elif "Óptimo" in status_filter:
            df_view = df_view[df_view["Estado"] == "Óptimo"]

        # Métricas de resumen KPI
        tot_players = len(df_level)
        n_opt = len(df_level[df_level["Estado"] == "Óptimo"])
        n_def = len(df_level[df_level["Estado"] == "Déficit"])
        n_sob = len(df_level[df_level["Estado"] == "Sobre-estímulo"])
        mean_dt_pct = df_view["% DT"].mean() if ("% DT" in df_view.columns and not df_view.empty) else 0.0

        k1, k2, k3, k4, k5 = st.columns(5)
        with k1:
            st.markdown(f"""
            <div class="metric-card">
                <div class="metric-title">Evaluados</div>
                <div class="metric-value">{tot_players}</div>
                <div class="metric-subtitle">Jugadores en sesión</div>
            </div>
            """, unsafe_allow_html=True)
        with k2:
            st.markdown(f"""
            <div class="metric-card" style="border-left: 4px solid #10B981;">
                <div class="metric-title">Cumplieron Objetivo</div>
                <div class="metric-value" style="color: #10B981;">{n_opt}</div>
                <div class="metric-subtitle">En rango óptimo (80-115%)</div>
            </div>
            """, unsafe_allow_html=True)
        with k3:
            st.markdown(f"""
            <div class="metric-card" style="border-left: 4px solid #EF4444;">
                <div class="metric-title">En Déficit</div>
                <div class="metric-value" style="color: #EF4444;">{n_def}</div>
                <div class="metric-subtitle">< 80% de meta {lvl_val}%</div>
            </div>
            """, unsafe_allow_html=True)
        with k4:
            st.markdown(f"""
            <div class="metric-card" style="border-left: 4px solid #F59E0B;">
                <div class="metric-title">Sobre-estímulo</div>
                <div class="metric-value" style="color: #F59E0B;">{n_sob}</div>
                <div class="metric-subtitle">> 115% de meta {lvl_val}%</div>
            </div>
            """, unsafe_allow_html=True)
        with k5:
            st.markdown(f"""
            <div class="metric-card">
                <div class="metric-title">% Cumpl. Medio DT</div>
                <div class="metric-value">{mean_dt_pct:.1f}%</div>
                <div class="metric-subtitle">Media filtrada vs {lvl_val}%</div>
            </div>
            """, unsafe_allow_html=True)

        st.write("")

        # Funciones de estilo
        def highlight_diag(val):
            s = str(val)
            if "Déficit" in s or "🔴" in s:
                return "background-color: rgba(239, 68, 68, 0.15); color: #FCA5A5; font-weight: 600; border-radius: 9999px; padding: 2px 8px;"
            elif "Sobre" in s or "🟠" in s or "Exceso" in s:
                return "background-color: rgba(245, 158, 11, 0.15); color: #FCD34D; font-weight: 600; border-radius: 9999px; padding: 2px 8px;"
            elif "Cumplido" in s or "🟢" in s or "Óptimo" in s:
                return "background-color: rgba(16, 185, 129, 0.15); color: #6EE7B7; font-weight: 600; border-radius: 9999px; padding: 2px 8px;"
            return ""

        def highlight_comp_cell(val):
            try:
                v = float(val)
                if v < 80.0:
                    return "background-color: rgba(239, 68, 68, 0.12); color: #F87171; font-weight: 600; border-radius: 6px; padding: 2px 6px;"
                elif v > 115.0:
                    return "background-color: rgba(245, 158, 11, 0.12); color: #FBBF24; font-weight: 600; border-radius: 6px; padding: 2px 6px;"
                else:
                    return "background-color: rgba(16, 185, 129, 0.12); color: #34D399; font-weight: 600; border-radius: 6px; padding: 2px 6px;"
            except Exception:
                return ""

        display_cols = [
            "Jugador", "Posición",
            "DT Real (km)", "DT Meta (km)", "% DT",
            "HSR Real (m)", "HSR Meta (m)", "% HSR",
            "Sprint Real (m)", "Sprint Meta (m)", "% Sprint",
            "ACC Real", "ACC Meta", "% ACC",
            "DCC Real", "DCC Meta", "% DCC",
            "Diagnóstico de Estímulo",
            "Entreno/Partido Referencia"
        ]
        available_cols = [c for c in display_cols if c in df_view.columns]

        st.dataframe(
            df_view[available_cols].style
            .format({
                "DT Real (km)": "{:.2f}",
                "DT Meta (km)": "{:.2f}",
                "% DT": "{:.1f}%",
                "HSR Real (m)": "{:.0f}",
                "HSR Meta (m)": "{:.0f}",
                "% HSR": "{:.1f}%",
                "Sprint Real (m)": "{:.0f}",
                "Sprint Meta (m)": "{:.0f}",
                "% Sprint": "{:.1f}%",
                "% ACC": "{:.1f}%",
                "% DCC": "{:.1f}%"
            })
            .map(highlight_diag, subset=["Diagnóstico de Estímulo"])
            .map(highlight_comp_cell, subset=["% DT", "% HSR", "% Sprint", "% ACC", "% DCC"]),
            column_config={
                "Jugador": st.column_config.TextColumn("Jugador", pinned=True, width="medium"),
                "Posición": st.column_config.TextColumn("Posición", width="small"),
                "Diagnóstico de Estímulo": st.column_config.TextColumn("Diagnóstico de Estímulo", width="large"),
                "Entreno/Partido Referencia": st.column_config.TextColumn("Entreno/Partido Referencia", width="medium"),
            },
            width="stretch",
            hide_index=True
        )

        col_dl1, col_dl2, col_dl3 = st.columns([2, 1.2, 0.8])
        with col_dl2:
            try:
                from src.services.excel_exporter import export_dataframe_to_formatted_excel
                excel_data = export_dataframe_to_formatted_excel(
                    df=df_view[available_cols],
                    sheet_name=f"Comparativa {lvl_val}%",
                    header_color="1E3A8A"
                )
                st.download_button(
                    label=f"📊 Descargar Excel {lvl_val}% (.xlsx)",
                    data=excel_data,
                    file_name=f"comparativa_sesion_{lvl_val}pct_{cmp_session_id}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    type="primary",
                    use_container_width=True,
                    key=f"btn_dl_xl_{lvl_val}"
                )
            except Exception as e_xl:
                st.caption(f"Aviso Excel: {e_xl}")

        with col_dl3:
            csv_data = df_view[available_cols].to_csv(index=False, sep=";").encode("utf-8-sig")
            st.download_button(
                label="📥 CSV",
                data=csv_data,
                file_name=f"comparativa_sesion_{lvl_val}pct_{cmp_session_id}.csv",
                mime="text/csv",
                use_container_width=True,
                key=f"btn_dl_csv_{lvl_val}"
            )

    with tab_50:
        render_level_tab_content(
            50,
            "Nivel 50% de Exigencias de Partido",
            "🟢 Carga Baja / Regenerativa",
            "Estímulo objetivo al 50% del partido oficial. Adecuado para sesiones regenerativas (MD+1), post-partido o compensatorios de futbolistas con pocos minutos.",
            "#10B981"
        )

    with tab_70:
        render_level_tab_content(
            70,
            "Nivel 70% de Exigencias de Partido",
            "🟡 Carga Media / Estándar",
            "Estímulo objetivo al 70% del partido oficial. Carga media equilibrada que busca adaptación y estímulo sin generar fatiga residual previa al fin de semana.",
            "#F59E0B"
        )

    with tab_80:
        render_level_tab_content(
            80,
            "Nivel 80% de Exigencias de Partido",
            "🔴 Carga Alta / Máxima Estimulación",
            "Estímulo objetivo al 80% del partido oficial. Día de máxima sobrecarga neuromuscular y metabólica semanal (MD-4 en aceleraciones, MD-3 en volumen, MD-2 en velocidad).",
            "#EF4444"
        )

    st.write("")
    st.divider()

    # Desplegable secundario con la calculadora previa por si desean consultar o fijar objetivos teóricos en TargetLoad
    with st.expander("🛠️ Calculadora y Prescripción Pre-Sesión (Opcional - Objetivos Teóricos Previos)", expanded=False):
        st.caption("Si deseas planificar metas teóricas antes de realizar la sesión y guardarlas en la base de datos (TargetLoad), puedes hacerlo aquí:")

        col_pre_day, col_pre_lvl = st.columns(2)
        with col_pre_day:
            sel_day = st.selectbox(
                "Día del Microciclo a Planificar:",
                MICROCYCLE_DAYS,
                index=0,
                key="pre_expander_day",
                help="Selecciona el día para cargar las pautas de periodización táctica recomendadas."
            )
        with col_pre_lvl:
            active_lvl = st.session_state.get(f"active_load_level_{sel_day}", 80 if sel_day in ["MD-4", "MD-3", "MD-2"] else 50)
            cur_preset = get_load_level_preset(active_lvl, sel_day)
            st.info(f"Nivel Preset: **{cur_preset['badge']}** — {cur_preset['title']}")

        col_sl1, col_sl2, col_sl3, col_sl4 = st.columns(4)
        with col_sl1:
            pct_td_input = st.slider(
                "🏃 % Distancia Total (DT):",
                min_value=20.0, max_value=120.0,
                value=float(cur_preset["pct_td"]),
                step=1.0,
                key=f"pre_sl_td_{sel_day}"
            )
        with col_sl2:
            pct_hsr_input = st.slider(
                "⚡ % HSR (>21 km/h):",
                min_value=10.0, max_value=120.0,
                value=float(cur_preset["pct_hsr"]),
                step=1.0,
                key=f"pre_sl_hsr_{sel_day}"
            )
        with col_sl3:
            pct_sprint_input = st.slider(
                "🚀 % Metros en Sprint:",
                min_value=10.0, max_value=120.0,
                value=float(cur_preset["pct_sprint"]),
                step=1.0,
                key=f"pre_sl_sp_{sel_day}"
            )
        with col_sl4:
            pct_eff_input = st.slider(
                "💥 % #ACC / #DCC EXPL:",
                min_value=10.0, max_value=120.0,
                value=float(cur_preset["pct_eff"]),
                step=1.0,
                key=f"pre_sl_eff_{sel_day}"
            )

        presc_result = get_cached_excel_pre_session_prescription(
            cmp_ref_id, sel_day, pct_td_input, pct_hsr_input, pct_sprint_input, pct_eff_input
        )
        df_presc_disp = presc_result.get("df_display", pd.DataFrame())

        col_tb_head, col_tb_btn = st.columns([3, 1])
        with col_tb_btn:
            if st.button("💾 Fijar Objetivos en BD", type="primary", use_container_width=True, key=f"btn_save_pre_{sel_day}"):
                with get_db() as db:
                    success_save = save_pre_session_prescription(
                        db, sel_day, pct_td_input, pct_hsr_input, pct_eff_input
                    )
                if success_save:
                    st.cache_data.clear()
                    st.toast(f"¡Prescripción para {sel_day} fijada en base de datos!", icon="💾")
                    st.success(f"✅ Prescripción para **{sel_day}** actualizada en la base de datos (TargetLoad).")

        if not df_presc_disp.empty:
            cols_p_clean = [c for c in df_presc_disp.columns if not c.startswith("_")]
            st.dataframe(df_presc_disp[cols_p_clean], width="stretch", hide_index=True)


# ==========================================
# VISTA 2: MONITOR LONGITUDINAL & ACWR
# ==========================================
elif menu == "📈 Evolución Longitudinal & ACWR":
    st.title("Evolución Longitudinal de Cargas (ACWR - EWMA)")
    st.markdown(
        "Monitorización temporal continua calculada con decaimiento exponencial (EWMA). "
        "Permite detectar picos agudos de fatiga sobre la base de aptitud física crónica."
    )

    players_data = get_cached_players_list()
    player_dict = {f"#{dorsal} - {name} ({pos})": p_id for p_id, dorsal, name, pos, _ in players_data}
    player_info = {p_id: (name, pos, vmax) for p_id, dorsal, name, pos, vmax in players_data}

    col_p1, col_p2 = st.columns([1.6, 1.4])
    with col_p1:
        selected_player_str = st.selectbox("Seleccionar Jugador para análisis longitudinal:", list(player_dict.keys()))
        selected_player_id = player_dict[selected_player_str]
    with col_p2:
        time_window = st.selectbox(
            "Ventana Temporal de Análisis:",
            ["Temporada Actual (Últimos 30 días)", "Pretemporada y Temporada (Últimos 60 días)", "Todo el Historial"],
            index=0,
            help="Enfoca el gráfico en la ventana de competición activa para visualizar las sesiones con el ancho óptimo sin huecos vacíos."
        )

    df_acwr = get_cached_player_acwr(selected_player_id, metric="total_distance")
    player_name, player_pos, player_max_speed = player_info.get(selected_player_id, ("", "", 32.0))

    if df_acwr.empty:
        st.warning("No hay suficientes registros históricos para este jugador.")
    else:
        last_row = df_acwr.iloc[-1]
        c_acute = last_row["acute_ewma"]
        c_chronic = last_row["chronic_ewma"]
        current_acwr = last_row["acwr"]
        acwr_status = last_row["acwr_status"]
        acwr_color = last_row["acwr_color"]

        # Tarjetas de resumen del jugador
        k1, k2, k3, k4 = st.columns(4)
        with k1:
            st.markdown(f"""
            <div class="metric-card">
                <div class="metric-title">Carga Aguda (EWMA 7d)</div>
                <div class="metric-value">{c_acute:.0f} m</div>
                <div class="metric-subtitle">Fatiga reciente acumulada</div>
            </div>
            """, unsafe_allow_html=True)
        with k2:
            st.markdown(f"""
            <div class="metric-card">
                <div class="metric-title">Carga Crónica (EWMA 28d)</div>
                <div class="metric-value">{c_chronic:.0f} m</div>
                <div class="metric-subtitle">Aptitud física / Fitness base</div>
            </div>
            """, unsafe_allow_html=True)
        with k3:
            st.markdown(f"""
            <div class="metric-card" style="border-left: 4px solid {acwr_color};">
                <div class="metric-title">Ratio ACWR Actual</div>
                <div class="metric-value" style="color: {acwr_color};">{current_acwr:.2f}</div>
                <div class="metric-subtitle">{acwr_status}</div>
            </div>
            """, unsafe_allow_html=True)
        with k4:
            st.markdown(f"""
            <div class="metric-card">
                <div class="metric-title">Perfil Atlético</div>
                <div class="metric-value" style="font-size: 1.3rem;">{player_pos}</div>
                <div class="metric-subtitle">Vmax teórica: {player_max_speed} km/h</div>
            </div>
            """, unsafe_allow_html=True)

        st.write("")

        # Leyenda visual del semáforo fisiológico
        st.markdown(render_semaforo_legend_html(), unsafe_allow_html=True)

        # Filtrar datos para el gráfico según la ventana temporal elegida
        max_dt = df_acwr["date"].max()
        if "30" in time_window:
            df_acwr_plot = df_acwr[df_acwr["date"] >= (max_dt - pd.Timedelta(days=30))].copy()
        elif "60" in time_window:
            df_acwr_plot = df_acwr[df_acwr["date"] >= (max_dt - pd.Timedelta(days=60))].copy()
        else:
            df_acwr_plot = df_acwr.copy()

        # Gráfico longitudinal interactivo de Plotly (ACWR EWMA)
        fig_acwr = create_acwr_longitudinal_chart(df_acwr_plot, player_name)
        st.plotly_chart(
            fig_acwr,
            width="stretch",
            config={"displaylogo": False, "modeBarButtonsToRemove": ["lasso2d", "select2d"]}
        )

        st.divider()

        # Comparativa Directa Entrenamiento vs. Partido de Máxima Exigencia y Evolución Semana a Semana
        comp_data = get_cached_player_longitudinal(selected_player_id)
        df_hist = comp_data.get("history", pd.DataFrame())
        peak_match = comp_data.get("peak")

        col_ch1, col_ch2 = st.columns(2)
        with col_ch1:
            st.subheader("⚔️ Entrenamiento vs. Partido de Máxima Exigencia")
            st.caption("Compara la carga de las sesiones contra el 100% de competición del jugador.")
            if not df_hist.empty and peak_match:
                fig_match_comp = create_training_vs_match_chart(df_hist, peak_match, player_name)
                st.plotly_chart(fig_match_comp, width="stretch")
            else:
                st.info("No hay suficientes datos de partido para este jugador.")

        with col_ch2:
            st.subheader("📅 Evolución Semana a Semana (Volumen e Intensidad)")
            st.caption("Compara el volumen total (DT) y la alta velocidad (HSR) acumulados por semana.")
            if not df_hist.empty:
                fig_weekly = create_weekly_comparison_chart(df_hist, player_name)
                st.plotly_chart(fig_weekly, width="stretch")
            else:
                st.info("No hay suficiente histórico semanal.")

        # Histórico de sesiones del jugador en tabla expandible
        with st.expander("Ver tabla histórica detallada de sesiones"):
            st.dataframe(
                df_acwr[[
                    "date", "load_value", "acute_ewma", "chronic_ewma", "acwr", "acwr_status"
                ]].rename(columns={
                    "date": "Fecha",
                    "load_value": "Carga Día (m)",
                    "acute_ewma": "Aguda (EWMA)",
                    "chronic_ewma": "Crónica (EWMA)",
                    "acwr": "Ratio ACWR",
                    "acwr_status": "Estado"
                }).sort_values(by="Fecha", ascending=False),
                width="stretch",
                hide_index=True
            )


# ==========================================
# VISTA: ASISTENTE DE IA (CUERPO TÉCNICO)
# ==========================================
elif menu == "🤖 Asistente de IA (Cuerpo Técnico)":
    st.markdown("""
    <div style="background: #1E293B; border: 1px solid #334155; border-radius: 12px; padding: 20px 24px; margin-bottom: 20px; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.2);">
        <div style="color: #38BDF8; font-size: 0.74rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em;">Inteligencia Artificial Aplicada al Deporte</div>
        <h2 style="color: #F8FAFC; margin: 3px 0 6px 0; font-size: 1.45rem; font-weight: 700; letter-spacing: -0.02em;">
            Asistente de IA para el Cuerpo Técnico
        </h2>
        <div style="color: #94A3B8; font-size: 0.85rem; line-height: 1.5;">
            Análisis de rendimiento y prescripción individual para el cuerpo técnico, seguimiento de cargas a 4 semanas y resolución de consultas fisiológicas en lenguaje natural mediante modelos LLM.
        </div>
    </div>
    """, unsafe_allow_html=True)

    import importlib
    import src.services.ai_assistant
    importlib.reload(src.services.ai_assistant)
    from src.services.ai_assistant import AIAssistant
    ai_service = AIAssistant()

    tab_ai1, tab_ai2 = st.tabs([
        "📋 Dictamen Individual por Futbolista",
        "💬 Consultas a la Plantilla (Chat IA)"
    ])

    with tab_ai1:
        st.subheader("Dictamen y Prescripción Individual por Futbolista")
        st.caption("Análisis exclusivo e individualizado para el cuerpo técnico: estado neuromuscular, evolución de 4 semanas y precauciones.")

        players_data = get_cached_players_list()
        player_dict = {f"#{dorsal} {name} ({pos})": p_id for p_id, dorsal, name, pos, _ in players_data}

        col_p1, col_p2 = st.columns([1.8, 1.2])
        with col_p1:
            sel_indiv_label = st.selectbox("Selecciona Futbolista a evaluar:", list(player_dict.keys()), key="ai_indiv_player_select")
            sel_indiv_id = player_dict[sel_indiv_label]

        if st.button("Generar Dictamen Individual para el Cuerpo Técnico", type="primary", use_container_width=True, key="btn_ai_gen_indiv"):
            with st.spinner("Analizando telemetría GPS, matriz del microciclo y generando informe individual con IA..."):
                with get_db() as db:
                    indiv_report = ai_service.generate_individual_player_report(sel_indiv_id, db)
                st.markdown(f'<div class="report-box">{indiv_report}</div>', unsafe_allow_html=True)

    with tab_ai2:
        st.subheader("Consultas Fisiológicas en Lenguaje Natural")
        st.caption("Pregunta cualquier aspecto sobre el estado de forma, fatiga o distribución de cargas del equipo.")

        user_query = st.text_area(
            "Escribe tu consulta para el preparador físico virtual:",
            placeholder="Ejemplo: ¿Qué jugadores superan el límite de riesgo de lesión tras la última sesión y cómo dosificamos su trabajo mañana?"
        )

        if st.button("Consultar al Asistente IA", type="primary", use_container_width=True):
            if user_query.strip():
                with st.spinner("Consultando base de datos de telemetría e infiriendo respuesta..."):
                    with get_db() as db:
                        ai_answer = ai_service.ask_squad_query(user_query, db)
                    st.markdown(f'<div class="report-box">{ai_answer}</div>', unsafe_allow_html=True)
            else:
                st.warning("Por favor, introduce una pregunta antes de consultar.")

