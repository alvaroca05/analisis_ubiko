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
        MICROCYCLE_MATCH_TARGETS
    )
    from src.database.connection import get_db, init_db
    from src.database.models import Player, TrainingSession, PlayerMetric, TargetLoad, PlayerMatchPeak
    import importlib
    import src.services.analytics
    importlib.reload(src.services.analytics)
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
        classify_session_player_states
    )
    from src.services.importer import UbikoImporter
    from src.services.report_generator import generate_tactical_report
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
    /* Ajustes base y modo oscuro */
    .main {
        background-color: #0E1117;
    }

    /* OCULTAR ENLACES A GITHUB, MENÚ STREAMLIT Y BARRA SUPERIOR POR SEGURIDAD */
    #MainMenu {visibility: hidden; display: none !important;}
    header {visibility: hidden; height: 0px !important;}
    footer {visibility: hidden; display: none !important;}
    [data-testid="stToolbar"] {visibility: hidden; display: none !important;}
    [data-testid="stDecoration"] {visibility: hidden; display: none !important;}
    [data-testid="stStatusWidget"] {visibility: hidden; display: none !important;}
    .viewerBadge_container__1QSob {display: none !important;}
    [data-testid="manage-app-button"] {display: none !important;}

    /* Contenedor fluido y márgenes adaptativos para no desperdiciar pantalla en móvil */
    .block-container {
        padding-top: 1.5rem !important;
        padding-bottom: 2.5rem !important;
        padding-left: 1rem !important;
        padding-right: 1rem !important;
        max-width: 100% !important;
    }

    /* Tarjetas de métricas KPIs responsivas */
    .metric-card {
        background: linear-gradient(135deg, #1E293B 0%, #0F172A 100%);
        border: 1px solid #334155;
        border-radius: 12px;
        padding: 14px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.3);
        margin-bottom: 10px;
        transition: transform 0.15s ease-in-out;
    }
    .metric-title {
        color: #94A3B8;
        font-size: 0.80rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }
    .metric-value {
        color: #F8FAFC;
        font-size: 1.6rem;
        font-weight: 700;
        margin-top: 4px;
    }
    .metric-subtitle {
        color: #64748B;
        font-size: 0.75rem;
        margin-top: 4px;
    }

    /* Caja de informes tácticos */
    .report-box {
        background-color: #111827;
        border: 1px solid #374151;
        border-radius: 8px;
        padding: 16px;
        font-family: 'Courier New', Courier, monospace;
        white-space: pre-wrap;
        color: #E5E7EB;
        line-height: 1.5;
        font-size: 0.85rem;
        overflow-x: auto;
    }
    .badge {
        display: inline-block;
        padding: 2px 8px;
        border-radius: 12px;
        font-size: 0.75rem;
        font-weight: bold;
    }

    /* OPTIMIZACIÓN MULTIPLATAFORMA MÓVIL Y TABLET (Breakpoints < 768px) */
    @media (max-width: 768px) {
        .block-container {
            padding-left: 0.6rem !important;
            padding-right: 0.6rem !important;
            padding-top: 1rem !important;
        }

        /* Títulos más compactos en móvil */
        h1 {
            font-size: 1.55rem !important;
            line-height: 1.25 !important;
        }
        h2 {
            font-size: 1.30rem !important;
        }
        h3 {
            font-size: 1.10rem !important;
        }

        /* Valores de métricas proporcionados a pantalla vertical */
        .metric-value {
            font-size: 1.4rem !important;
        }
        .metric-card {
            padding: 10px 12px !important;
            margin-bottom: 8px !important;
        }

        /* Forzar que las columnas de Streamlit en móvil mantengan ancho utilizable y flexwrap */
        [data-testid="column"] {
            min-width: 100% !important;
            flex: 1 1 100% !important;
            margin-bottom: 0.5rem;
        }

        /* Botones táctiles grandes y fáciles de pulsar con el pulgar */
        button[kind="primary"], button[kind="secondary"], .stButton > button {
            min-height: 46px !important;
            font-size: 0.95rem !important;
            border-radius: 10px !important;
        }

        /* Scroll horizontal fluido para tablas sin deformar la pantalla */
        [data-testid="stDataFrame"], [data-testid="stTable"] {
            overflow-x: auto !important;
            -webkit-overflow-scrolling: touch;
            width: 100% !important;
        }

        /* Ajuste de gráficos Plotly en móvil */
        .js-plotly-plot, .plot-container {
            max-width: 100% !important;
            overflow-x: hidden !important;
        }
    }
</style>

<!-- Metadatos y soporte PWA (Progressive Web App) para instalación en Móvil / Tablet -->
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="UBIKO Hub">
<meta name="theme-color" content="#0E1117">
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




# ==========================================
# SEGURIDAD & AUTENTICACIÓN DEL CUERPO TÉCNICO
# ==========================================
def check_authentication() -> bool:
    """Verifica si el usuario se ha autenticado con la contraseña de seguridad."""
    if st.session_state.get("authenticated", False):
        return True

    configured_pwd = (
        st.secrets.get("APP_PASSWORD")
        if hasattr(st, "secrets") and "APP_PASSWORD" in st.secrets
        else os.environ.get("APP_PASSWORD", "ubiko2026")
    )

    col_l1, col_l2, col_l3 = st.columns([1, 1.8, 1])
    with col_l2:
        st.write("")
        st.write("")
        st.markdown("""
        <div style="background: linear-gradient(135deg, #1E293B 0%, #0F172A 100%); border: 1px solid #334155; border-radius: 16px; padding: 26px 20px; text-align: center; box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.5);">
            <img src="https://img.icons8.com/color/96/football-ball.png" width="60" style="margin-bottom: 8px;"/>
            <h2 style="color: #F8FAFC; margin: 0 0 6px 0; font-size: 1.45rem;">UBIKO Performance Hub</h2>
            <div style="color: #94A3B8; font-size: 0.85rem; margin-bottom: 18px;">
                🔒 Portal Confidencial de Telemetría GPS y Cargas de Competición.<br>
                <span style="color: #00E676; font-weight: 600;">Acceso Restringido al Cuerpo Técnico</span>
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
            submit_btn = st.form_submit_button("🔑 Entrar al Sistema", type="primary", use_container_width=True)
            if submit_btn:
                if entered_pwd == configured_pwd:
                    st.session_state["authenticated"] = True
                    st.toast("¡Acceso concedido al Hub!", icon="⚽")
                    st.rerun()
                else:
                    st.error("⛔ Contraseña incorrecta. Acceso restringido por confidencialidad del club.")

        st.caption("🛡️ Datos protegidos con cifrado SSL y políticas de privacidad.")

    return False

if not check_authentication():
    st.stop()


# ==========================================
# BARRA LATERAL (SIDEBAR)
# ==========================================
with st.sidebar:
    st.image("https://img.icons8.com/color/96/football-ball.png", width=64)
    st.title("UBIKO Hub")
    st.caption("Monitorización de Carga GPS & Periodización Táctica")

    if "nav_menu" not in st.session_state:
        st.session_state["nav_menu"] = "📊 Panel de Sesión & Semáforo"
    elif st.session_state.get("nav_menu") == "📋 Planificación Pre-Sesión":
        st.session_state["nav_menu"] = "📋 Planificación & Comparativa (50/70/80%)"

    if st.button("⏱️ Añadir / Registrar RPE", type="primary", use_container_width=True, help="Abrir registro de percepción de esfuerzo de la sesión (Foster 1-10)"):
        st.session_state["nav_menu"] = "⏱️ Carga Interna & Registro RPE"
        st.rerun()

    st.divider()

    menu = st.radio(
        "Navegación del Sistema",
        [
            "📊 Panel de Sesión & Semáforo",
            "🏟️ Referencia Partidos (Excel P.F.)",
            "📋 Planificación & Comparativa (50/70/80%)",
            "📈 Evolución Longitudinal & ACWR",
            "📝 Informe Táctico Ejecutivo",
            "🤖 Asistente de IA (Cuerpo Técnico)",
            "⏱️ Carga Interna & Registro RPE",
            "📥 Ingesta de Datos GPS (UBIKO)",
            "⚙️ Objetivos de Carga Fisiológica"
        ],
        key="nav_menu"
    )

    st.divider()
    st.subheader("Selección de Sesión")

    cached_sessions = get_cached_sessions()
    session_options = {label: s_id for s_id, label in cached_sessions}

    if session_options:
        selected_session_label = st.selectbox("Sesión a evaluar:", list(session_options.keys()))
        selected_session_id = session_options[selected_session_label]
    else:
        st.warning("No hay sesiones en la base de datos.")
        selected_session_id = None

    st.divider()
    st.subheader("⚡ Sincronización UBIKO")
    st.caption("☁️ Base de datos activa: **Supabase (Nube)**")

    sync_from_date = st.date_input("Recopilar desde fecha:", value=date(2026, 9, 3), key="sidebar_sync_date")
    col_opt1, col_opt2 = st.columns(2)
    with col_opt1:
        force_sync = st.checkbox("Forzar todo", value=False, key="sidebar_force_sync", help="Re-descarga e ingesta sesiones en Supabase aunque ya existan.")
    with col_opt2:
        visible_sync = st.checkbox("Ver navegador", value=False, key="sidebar_visible_sync", help="Muestra la ventana del navegador para verificar el login o descargas en UBIKO.")

    if st.button("🚀 Sincronizar Sesiones Ahora", type="primary", use_container_width=True):
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
                st.success(f"✅ {msg}")
                time.sleep(1.2)
                st.rerun()
            elif is_success and synced_count == 0:
                st.info(f"ℹ️ {msg}")
            else:
                st.error(f"❌ {msg}")

    with st.expander("📁 Subir CSV de UBIKO directamente", expanded=False):
        st.caption("Si prefieres no usar la extracción web o estás en un entorno restringido, puedes subir aquí el `.csv` descargado de UBIKO:")
        sb_uploaded = st.file_uploader("Arrastra tu archivo CSV:", type=["csv", "xlsx"], key="sb_quick_csv")
        if sb_uploaded is not None:
            from src.services.importer import UbikoImporter
            with st.spinner("Procesando e insertando en Supabase..."):
                df_parsed = UbikoImporter.parse_file(sb_uploaded, sb_uploaded.name)
                with get_db() as db:
                    res_imp = UbikoImporter.import_session_to_db(db, df_parsed, original_filename=sb_uploaded.name)
                st.cache_data.clear()
                if res_imp.get("success"):
                    st.success(f"✅ {res_imp.get('message', 'Sesión importada correctamente')}")
                    time.sleep(1.2)
                    st.rerun()
                else:
                    st.error(f"❌ {res_imp.get('error', 'Error al importar archivo')}")

    col_sb1, col_sb2 = st.columns(2)
    with col_sb1:
        if st.button("🧹 Limpiar Falsos", use_container_width=True, help="Elimina sesiones y métricas simuladas de Supabase, manteniendo la plantilla y objetivos."):
            from seed_data import purge_simulated_sessions_and_metrics
            n_s, n_m = purge_simulated_sessions_and_metrics()
            st.cache_data.clear()
            st.toast(f"Limpieza completada: {n_s} sesiones y {n_m} métricas borradas.", icon="🧹")
            st.rerun()
    with col_sb2:
        if st.button("🔄 Simular Datos", use_container_width=True, help="Genera datos sintéticos de prueba."):
            from seed_data import seed_database
            seed_database(include_sessions=True)
            st.cache_data.clear()
            st.toast("Datos sintéticos generados.", icon="✅")
            st.rerun()

    st.caption("TFG Ingeniería Informática | Universidad de Córdoba")

    st.divider()
    if st.button("🔒 Cerrar Sesión", use_container_width=True, help="Bloquea el portal y cierra la sesión del cuerpo técnico."):
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

    # Cabecera de la sesión
    st.title(f"Sesión: {sess.name}")
    col_h1, col_h2, col_h3, col_h4 = st.columns(4)
    col_h1.info(f"📅 **Fecha:** {sess.date.strftime('%d/%m/%Y')}")
    col_h2.info(f"⚡ **Microciclo:** {sess.microcycle_day}")
    col_h3.info(f"⏱️ **Duración:** {sess.duration_minutes} min")
    col_h4.info(f"🏟️ **Tipo:** {sess.session_type}")

    st.markdown(f"**Enfoque de la sesión:** {MICROCYCLE_DESCRIPTIONS.get(sess.microcycle_day, '')}")
    st.write("")

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
    # 1. SEMÁFORO DE FATIGA Y RIESGO LESIONAL (ACWR - EWMA)
    # ========================================================
    st.markdown("### 🚦 Semáforo de Fatiga y Riesgo Lesional (ACWR)")
    st.caption("Control de fatiga aguda acumulada sobre aptitud física crónica (Gabbett EWMA).")

    if "acwr" not in df_metrics.columns:
        df_metrics["acwr"] = 1.0
    if "acwr_status" not in df_metrics.columns:
        df_metrics["acwr_status"] = "Óptimo Sweet Spot (0.80-1.30)"

    danger_players = df_metrics[df_metrics["acwr"] > 1.5]
    caution_players = df_metrics[(df_metrics["acwr"] > 1.3) & (df_metrics["acwr"] <= 1.5)]
    optimal_players = df_metrics[(df_metrics["acwr"] >= 0.8) & (df_metrics["acwr"] <= 1.3)]
    under_players = df_metrics[df_metrics["acwr"] < 0.8]

    sem1, sem2, sem3 = st.columns(3)
    with sem1:
        st.markdown(f"""
        <div class="metric-card" style="border-left: 5px solid #10B981; background: rgba(16, 185, 129, 0.08);">
            <div class="metric-title" style="color: #6EE7B7;">🟢 Óptimo (Sweet Spot 0.8 - 1.3)</div>
            <div class="metric-value" style="color: #10B981;">{len(optimal_players)} <span style="font-size:0.9rem; color:#94A3B8;">jugadores</span></div>
            <div class="metric-subtitle">Carga asimilable. Mínimo riesgo lesional.</div>
        </div>
        """, unsafe_allow_html=True)

    with sem2:
        caution_names = ", ".join([f"#{row.dorsal} {row.player_name.split()[0]}" for _, row in caution_players.iterrows()]) if not caution_players.empty else "Ninguno"
        st.markdown(f"""
        <div class="metric-card" style="border-left: 5px solid #F59E0B; background: rgba(245, 158, 11, 0.08);">
            <div class="metric-title" style="color: #FCD34D;">🟡 Alerta Fatiga (1.3 - 1.5)</div>
            <div class="metric-value" style="color: #F59E0B;">{len(caution_players)} <span style="font-size:0.9rem; color:#94A3B8;">jugadores</span></div>
            <div class="metric-subtitle"><b>Atención:</b> {caution_names}</div>
        </div>
        """, unsafe_allow_html=True)

    with sem3:
        danger_names = ", ".join([f"#{row.dorsal} {row.player_name.split()[0]}" for _, row in danger_players.iterrows()]) if not danger_players.empty else "Ninguno"
        danger_bg = "rgba(239, 68, 68, 0.15)" if not danger_players.empty else "rgba(239, 68, 68, 0.05)"
        st.markdown(f"""
        <div class="metric-card" style="border-left: 5px solid #EF4444; background: {danger_bg};">
            <div class="metric-title" style="color: #FCA5A5;">🔴 Riesgo Alto (> 1.5)</div>
            <div class="metric-value" style="color: #EF4444;">{len(danger_players)} <span style="font-size:0.9rem; color:#94A3B8;">jugadores</span></div>
            <div class="metric-subtitle"><b>Peligro lesión:</b> {danger_names}</div>
        </div>
        """, unsafe_allow_html=True)

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
            "dorsal", "player_name", "position",
            "comp_pct_td", "comp_pct_hsr", "comp_pct_eff",
            "diagnosis", "val_real_formatted", "val_target_formatted", "val_match_100_formatted", "peak_match_name"
        ]].copy()
        df_table_ci.columns = [
            "Dorsal", "Jugador", "Posición",
            "% Cumpl. DT", "% Cumpl. HSR", "% Cumpl. AC.E",
            "Diagnóstico de Estímulo", f"Real ({day_metric_label})",
            f"Prescrito ({day_pct}%)", "Partido Récord (100%)", "Partido Referencia"
        ]

        def highlight_diag(val):
            s = str(val)
            if "Déficit" in s:
                return "background-color: rgba(239, 68, 68, 0.25); color: #FCA5A5; font-weight: bold;"
            elif "Sobre" in s or "Exceso" in s or "Sobrecarga" in s:
                return "background-color: rgba(245, 158, 11, 0.25); color: #FCD34D; font-weight: bold;"
            elif "Cumplido" in s or "Correcta" in s or "Óptimo" in s or "Adecuada" in s:
                return "background-color: rgba(16, 185, 129, 0.25); color: #6EE7B7; font-weight: bold;"
            return ""

        def highlight_metric_pct(val):
            try:
                v = float(val)
                if v < 80.0:
                    return "background-color: rgba(239, 68, 68, 0.18); color: #F87171; font-weight: bold;"
                elif v > 115.0:
                    return "background-color: rgba(245, 158, 11, 0.18); color: #FBBF24; font-weight: bold;"
                else:
                    return "background-color: rgba(16, 185, 129, 0.18); color: #34D399; font-weight: bold;"
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
                            return "background-color: rgba(239, 68, 68, 0.25); color: #FCA5A5; font-weight: bold;"
                        elif v > 115.0:
                            return "background-color: rgba(245, 158, 11, 0.25); color: #FCD34D; font-weight: bold;"
                        else:
                            return "background-color: rgba(16, 185, 129, 0.25); color: #6EE7B7; font-weight: bold;"
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
            return "background-color: rgba(239, 68, 68, 0.25); color: #FCA5A5; font-weight: bold;"
        elif "Precaución" in str(val) or "Fatiga" in str(val):
            return "background-color: rgba(245, 158, 11, 0.25); color: #FCD34D; font-weight: bold;"
        elif "Óptimo" in str(val) or "Sweet" in str(val):
            return "background-color: rgba(16, 185, 129, 0.25); color: #6EE7B7; font-weight: bold;"
        elif "Subentrenamiento" in str(val):
            return "background-color: rgba(59, 130, 246, 0.25); color: #93C5FD; font-weight: bold;"
        return ""

    def highlight_compliance(val):
        try:
            v = float(val)
            if v < 75.0 or v > 125.0:
                return "background-color: rgba(239, 68, 68, 0.20); color: #F87171; font-weight: bold;"
            elif v < 88.0 or v > 112.0:
                return "background-color: rgba(245, 158, 11, 0.20); color: #FBBF24; font-weight: bold;"
            else:
                return "background-color: rgba(16, 185, 129, 0.20); color: #34D399; font-weight: bold;"
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
# VISTA: REFERENCIA PARTIDOS (EXCEL PREPARADOR FÍSICO)
# ==========================================
elif menu == "🏟️ Referencia Partidos (Excel P.F.)":
    st.markdown("""
    <div style="background: linear-gradient(90deg, #1E3A8A 0%, #0F172A 100%); padding: 18px 24px; border-radius: 12px; border: 1px solid #3B82F6; margin-bottom: 20px;">
        <h2 style="color: #F8FAFC; margin: 0; font-size: 1.35rem; letter-spacing: 0.04em;">
            🏟️ TEMPORADA 26/27 SALERM COSMETIC PUENTE GENIL REFERENCIA DATOS DE PARTIDOS
        </h2>
        <p style="color: #93C5FD; margin: 6px 0 0 0; font-size: 0.88rem;">
            Estructura de control oficial del preparador físico | Máxima exigencia competitiva por demarcación y datos generales del equipo
        </p>
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
            <div style="background: rgba(239, 68, 68, 0.12); border: 1px solid rgba(239, 68, 68, 0.4); border-radius: 8px; padding: 10px 16px; margin-bottom: 15px; display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap;">
                <div>
                    <span style="color: #EF4444; font-weight: bold; font-size: 0.95rem;">⭐ JUGADOR TOP DE LA SESIÓN:</span>
                    <span style="color: #F8FAFC; font-weight: 700; margin-left: 8px;">#{top_p['dorsal']} {top_p['player_name'].upper()} ({top_p['position']})</span>
                </div>
                <div style="color: #FCA5A5; font-size: 0.85rem; font-weight: 600;">
                    Distancia: <b>{top_p['distance_km']:.2f} km</b> | Vmax: <b>{top_p['max_speed']:.2f} km/h</b> | HSR: <b>{top_p['hsr_m']:.0f} m</b> | Esfuerzos: <b>{top_p['acc_expl'] + top_p['dcc_expl']}</b>
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
                return ["background-color: rgba(239, 68, 68, 0.22); color: #FCA5A5; font-weight: bold; border-top: 1px solid #EF4444; border-bottom: 1px solid #EF4444;"] * len(row)
            elif row_type == "team" or "EQUIPO" in pos:
                return ["background-color: rgba(37, 99, 235, 0.28); color: #93C5FD; font-weight: bold; border-top: 2px solid #3B82F6;"] * len(row)
            elif row_type == "player_top":
                return ["background-color: rgba(239, 68, 68, 0.12); font-weight: 600;"] * len(row)
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
                pdf_data = generate_match_reference_pdf(
                    match_title=selected_match_label,
                    df_rows=df_view
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
        col_m1, col_m2, col_m3, col_m4 = st.columns(4)
        col_m1.info(f"📅 **Fecha:** {s_obj.date.strftime('%d/%m/%Y')}")
        col_m2.info(f"⚡ **Microciclo:** {s_obj.microcycle_day}")
        col_m3.info(f"⏱️ **Duración:** {s_obj.duration_minutes} min")
        col_m4.info(f"👥 **Futbolistas con GPS:** {len(m_list)}")

    # 2. Filtros Interactivos (colocados arriba de las pestañas)
    col_f1, col_f2 = st.columns([1.2, 1.2])
    with col_f1:
        pos_filter = st.multiselect(
            "Filtrar por Demarcación:",
            ["CENTRAL", "LATERAL", "MEDIOCENTRO", "EXTREMO", "DELANTERO", "PORTERO"],
            default=["CENTRAL", "LATERAL", "MEDIOCENTRO", "EXTREMO", "DELANTERO"],
            key="cmp_global_pos_filter"
        )
    with col_f2:
        status_filter = st.selectbox(
            "Filtrar por Estado de Estímulo:",
            ["Todos", "🟢 Cumplieron Objetivo", "🔴 En Déficit", "🟠 Sobre-estímulo"],
            key="cmp_global_status_filter"
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
        if status_filter == "🟢 Cumplieron Objetivo":
            df_view = df_view[df_view["Estado"] == "Óptimo"]
        elif status_filter == "🔴 En Déficit":
            df_view = df_view[df_view["Estado"] == "Déficit"]
        elif status_filter == "🟠 Sobre-estímulo":
            df_view = df_view[df_view["Estado"] == "Sobre-estímulo"]

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
                <div class="metric-title">🟢 Cumplieron Objetivo</div>
                <div class="metric-value" style="color: #10B981;">{n_opt}</div>
                <div class="metric-subtitle">En rango óptimo (80-115%)</div>
            </div>
            """, unsafe_allow_html=True)
        with k3:
            st.markdown(f"""
            <div class="metric-card" style="border-left: 4px solid #EF4444;">
                <div class="metric-title">🔴 En Déficit</div>
                <div class="metric-value" style="color: #EF4444;">{n_def}</div>
                <div class="metric-subtitle">< 80% de meta {lvl_val}%</div>
            </div>
            """, unsafe_allow_html=True)
        with k4:
            st.markdown(f"""
            <div class="metric-card" style="border-left: 4px solid #F59E0B;">
                <div class="metric-title">🟠 Sobre-estímulo</div>
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
                return "background-color: rgba(239, 68, 68, 0.25); color: #FCA5A5; font-weight: bold;"
            elif "Sobre" in s or "🟠" in s or "Exceso" in s:
                return "background-color: rgba(245, 158, 11, 0.25); color: #FCD34D; font-weight: bold;"
            elif "Cumplido" in s or "🟢" in s or "Óptimo" in s:
                return "background-color: rgba(16, 185, 129, 0.25); color: #6EE7B7; font-weight: bold;"
            return ""

        def highlight_comp_cell(val):
            try:
                v = float(val)
                if v < 80.0:
                    return "background-color: rgba(239, 68, 68, 0.20); color: #F87171; font-weight: bold;"
                elif v > 115.0:
                    return "background-color: rgba(245, 158, 11, 0.20); color: #FBBF24; font-weight: bold;"
                else:
                    return "background-color: rgba(16, 185, 129, 0.20); color: #34D399; font-weight: bold;"
            except Exception:
                return ""

        display_cols = [
            "Dorsal", "Jugador", "Posición",
            "DT Real (km)", "DT Meta (km)", "% DT",
            "HSR Real (m)", "HSR Meta (m)", "% HSR",
            "Sprint Real (m)", "Sprint Meta (m)", "% Sprint",
            "ACC Real", "ACC Meta", "% ACC",
            "DCC Real", "DCC Meta", "% DCC",
            "Diagnóstico de Estímulo"
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
# VISTA 3: INFORME TÁCTICO EJECUTIVO
# ==========================================
elif menu == "📝 Informe Táctico Ejecutivo":
    st.title("Generador de Informe Diario para el Cuerpo Técnico")
    st.markdown(
        "Módulo de síntesis automatizada en lenguaje natural. "
        "Traduce las métricas complejas de telemetría GPS en recomendaciones tácticas y de salud deportiva inmediatas."
    )

    if not selected_session_id:
        st.warning("Selecciona una sesión en la barra lateral.")
        st.stop()

    summary = get_cached_session_summary(selected_session_id)

    report_text = generate_tactical_report(summary)

    st.markdown(f'<div class="report-box">{report_text}</div>', unsafe_allow_html=True)

    st.write("")
    col_d1, col_d2 = st.columns([1, 4])
    with col_d1:
        st.download_button(
            label="💾 Descargar Informe (.txt)",
            data=report_text,
            file_name=f"informe_ubiko_{summary['session'].date}_{summary['session'].microcycle_day}.txt",
            mime="text/plain"
        )


# ==========================================
# VISTA: ASISTENTE DE IA (CUERPO TÉCNICO)
# ==========================================
elif menu == "🤖 Asistente de IA (Cuerpo Técnico)":
    st.title("Asistente de IA para el Cuerpo Técnico")
    st.markdown(
        "Módulo de Inteligencia Artificial para análisis de rendimiento, comparativa de futbolistas en pugna posicional "
        "y resolución de consultas técnico-tácticas mediante modelos LLM (Groq / Gemini)."
    )

    import importlib
    import src.services.ai_assistant
    importlib.reload(src.services.ai_assistant)
    from src.services.ai_assistant import AIAssistant
    ai_service = AIAssistant()

    tab_ai1, tab_ai2 = st.tabs(["⚔️ Comparativa Directa de Futbolistas", "💬 Consulta a la Plantilla"])

    with tab_ai1:
        st.subheader("Comparativa Fisiológica y Riesgo Lesional entre Jugadores")
        st.caption("Contrasta el ratio EWMA ACWR, carga aguda/crónica y medias de alta intensidad para decidir alineaciones o rotaciones.")

        players_data = get_cached_players_list()
        player_dict = {f"#{dorsal} {name} ({pos})": p_id for p_id, dorsal, name, pos, _ in players_data}

        if len(player_dict) >= 2:
            col_p1, col_p2 = st.columns(2)
            player_keys = list(player_dict.keys())
            with col_p1:
                sel_p1 = st.selectbox("Selecciona Primer Futbolista:", player_keys, index=0)
            with col_p2:
                sel_p2 = st.selectbox("Selecciona Segundo Futbolista:", player_keys, index=1 if len(player_keys) > 1 else 0)

            id_a = player_dict[sel_p1]
            id_b = player_dict[sel_p2]

            if st.button("🔍 Generar Comparativa de Rendimiento con IA", use_container_width=True):
                with st.spinner("Analizando historial de telemetría y generando dictamen técnico..."):
                    with get_db() as db:
                        ai_result = ai_service.compare_players(id_a, id_b, db)
                    st.markdown(f'<div class="report-box">{ai_result}</div>', unsafe_allow_html=True)
        else:
            st.info("Se necesitan al menos 2 futbolistas registrados para realizar una comparativa.")

    with tab_ai2:
        st.subheader("Consultas Fisiológicas en Lenguaje Natural")
        st.caption("Pregunta cualquier aspecto sobre el estado de forma, fatiga o distribución de cargas del equipo.")

        user_query = st.text_area(
            "Escribe tu consulta para el preparador físico virtual:",
            placeholder="Ejemplo: ¿Qué jugadores superan el límite de riesgo de lesión tras la última sesión y cómo dosificamos su trabajo mañana?"
        )

        if st.button("💡 Consultar al Asistente IA", use_container_width=True):
            if user_query.strip():
                with st.spinner("Consultando base de datos de telemetría e infiriendo respuesta..."):
                    with get_db() as db:
                        ai_answer = ai_service.ask_squad_query(user_query, db)
                    st.markdown(f'<div class="report-box">{ai_answer}</div>', unsafe_allow_html=True)
            else:
                st.warning("Por favor, introduce una pregunta antes de consultar.")


# ==========================================
# VISTA: CONTROL DE CARGA INTERNA & REGISTRO RPE
# ==========================================
elif menu == "⏱️ Carga Interna & Registro RPE":
    st.title("⏱️ Control de Carga Interna & Registro de RPE")
    st.markdown(
        "Protocolo de Percepción Subjetiva del Esfuerzo (Escala de Foster / Borg modificada 1-10). "
        "Permite registrar la muestra de futbolistas encuestados post-entrenamiento (habitualmente entre 8 y 10 jugadores), "
        "calcular el **RPE promedio de la sesión** y cuantificar la **Carga Interna individual (sRPE = RPE × Duración en min)**."
    )

    # 1. Selector de sesión
    cached_sessions = get_cached_sessions()
    session_options = {label: s_id for s_id, label in cached_sessions}

    if not session_options:
        st.warning("No hay sesiones disponibles en la base de datos para registrar RPE.")
        st.stop()

    default_idx = 0
    if selected_session_id and selected_session_id in session_options.values():
        for idx, (lbl, sid) in enumerate(session_options.items()):
            if sid == selected_session_id:
                default_idx = idx
                break

    col_s1, col_s2 = st.columns([3, 1])
    with col_s1:
        target_session_label = st.selectbox(
            "Selecciona la sesión a evaluar:",
            list(session_options.keys()),
            index=default_idx
        )
        target_session_id = session_options[target_session_label]

    with get_db() as db:
        sess_obj = db.query(TrainingSession).filter(TrainingSession.id == target_session_id).first()
        duration_min = sess_obj.duration_minutes if sess_obj else 75
        sess_name = sess_obj.name if sess_obj else ""
        sess_date = sess_obj.date if sess_obj else date.today()
        micro_day = sess_obj.microcycle_day if sess_obj else "MD-3"

        # Obtener los jugadores que participaron en esta sesión
        players_in_session = (
            db.query(Player.id, Player.dorsal, Player.name, Player.position, PlayerMetric.total_distance, PlayerMetric.rpe)
            .join(PlayerMetric, Player.id == PlayerMetric.player_id)
            .filter(PlayerMetric.session_id == target_session_id)
            .order_by(Player.dorsal.asc())
            .all()
        )

    with col_s2:
        st.info(f"⏱️ **Duración:** {duration_min} min  \n📅 **Fecha:** {sess_date.strftime('%d/%m/%Y')}")

    if not players_in_session:
        st.warning(f"La sesión '{sess_name}' no tiene métricas de jugadores registradas.")
        st.stop()

    # Pre-identificar quiénes ya tenían RPE guardado
    # 2. Construcción de la tabla recta con todos los jugadores
    has_any_saved = any(p[5] is not None and p[5] > 0 for p in players_in_session)

    st.divider()
    st.subheader("📋 Tabla de Futbolistas (Marca la fila e introduce el RPE)")
    st.caption(
        "Marca con la casilla los jugadores a los que has preguntado el esfuerzo (muestra habitual de 8 a 10) "
        "y escribe en el recuadro su nota del 1 al 10 (Escala Foster / Borg)."
    )

    # Botones de acción rápida
    col_b1, col_b2, col_b3 = st.columns([1, 1, 2])
    btn_mark10 = col_b1.button("☑️ Marcar Primeros 10")
    btn_clear = col_b2.button("⬜ Desmarcar Todos")

    # Guía fisiológica desplegable
    with st.expander("📖 Ver Guía de Referencia Fisiológica RPE (Foster 1-10)"):
        st.markdown("""
        * **1 - 2 (Muy fácil):** Tareas regenerativas, paseos, calentamientos suaves o rondos livianos.
        * **3 - 4 (Moderado):** Trabajo aeróbico continuo, ruedas de pase con pausa, ritmo cómodo.
        * **5 - 6 (Duro / Umbral):** Posesiones tácticas a espacio amplio, partidos condicionados exigentes.
        * **7 - 8 (Muy duro):** Juegos reducidos de alta intensidad (3v3, 4v4), series de sprints y transiciones.
        * **9 - 10 (Máximo / Extenuante):** Partido oficial de máxima exigencia o test de esfuerzo hasta el agotamiento.
        """)

    # Preparar datos para la tabla recta (st.data_editor)
    rows = []
    for idx, p in enumerate(players_in_session):
        pid = p[0]
        dorsal = p[1]
        name = p[2]
        pos = p[3]
        td = int(round(p[4]))
        curr_rpe = p[5]

        if btn_mark10:
            is_sel = (idx < 10)
        elif btn_clear:
            is_sel = False
        else:
            is_sel = (curr_rpe is not None and curr_rpe > 0) or (not has_any_saved and idx < 10)

        val_rpe = float(curr_rpe) if curr_rpe is not None and curr_rpe > 0 else 6.0

        rows.append({
            "Seleccionar": is_sel,
            "Dorsal": dorsal,
            "Jugador": name,
            "Posición": pos,
            "Distancia GPS (m)": td,
            "RPE (1-10)": val_rpe,
            "_player_id": pid
        })

    df_table = pd.DataFrame(rows)

    # Renderizar la tabla recta interactiva con casillas y recuadros de RPE
    editor_key = f"rpe_editor_{target_session_id}_{btn_mark10}_{btn_clear}"
    edited_df = st.data_editor(
        df_table,
        column_config={
            "Seleccionar": st.column_config.CheckboxColumn(
                "Seleccionar",
                help="Marca la casilla para incluir al futbolista en el RPE de la sesión",
                default=False
            ),
            "Dorsal": st.column_config.NumberColumn("Dorsal", format="%d", disabled=True),
            "Jugador": st.column_config.TextColumn("Jugador", disabled=True),
            "Posición": st.column_config.TextColumn("Posición", disabled=True),
            "Distancia GPS (m)": st.column_config.NumberColumn("Distancia GPS (m)", format="%d m", disabled=True),
            "RPE (1-10)": st.column_config.NumberColumn(
                "RPE (1-10)",
                help="Recuadro para introducir el número de esfuerzo (1.0 = Muy suave, 10.0 = Máximo)",
                min_value=1.0,
                max_value=10.0,
                step=0.5,
                format="%.1f"
            ),
            "_player_id": None
        },
        disabled=["Dorsal", "Jugador", "Posición", "Distancia GPS (m)"],
        hide_index=True,
        width="stretch",
        key=editor_key
    )

    st.write("")
    col_save, col_del = st.columns([3, 1])
    with col_save:
        save_btn = st.button("💾 Registrar y Guardar RPE de la Sesión", type="primary", use_container_width=True)
    with col_del:
        delete_btn = st.button("🗑️ Eliminar RPE de la Sesión", type="secondary", use_container_width=True, help="Borra las calificaciones de RPE guardadas en esta sesión.")

    if delete_btn:
        with get_db() as db:
            metrics = (
                db.query(PlayerMetric)
                .filter(PlayerMetric.session_id == target_session_id)
                .all()
            )
            count_cleared = 0
            for m in metrics:
                if m.rpe is not None:
                    m.rpe = None
                    count_cleared += 1
            db.commit()

        st.cache_data.clear()
        st.toast(f"¡RPE de la sesión eliminado! ({count_cleared} registros limpiados)", icon="🗑️")
        st.success(f"Se han eliminado todas las notas de RPE de la sesión '{sess_name}'.")
        time.sleep(1)
        st.rerun()

    if save_btn:
        selected_rows = edited_df[edited_df["Seleccionar"] == True]

        if selected_rows.empty:
            st.warning("⚠️ No has marcado ningún jugador con la casilla. Marca al menos una fila para registrar el RPE.")
        else:
            selected_dict = {
                int(row["_player_id"]): float(row["RPE (1-10)"])
                for _, row in selected_rows.iterrows()
            }

            with get_db() as db:
                for p in players_in_session:
                    pid = p[0]
                    metric = (
                        db.query(PlayerMetric)
                        .filter(PlayerMetric.session_id == target_session_id, PlayerMetric.player_id == pid)
                        .first()
                    )
                    if metric:
                        if pid in selected_dict:
                            metric.rpe = selected_dict[pid]
                        else:
                            metric.rpe = None
                db.commit()

            st.cache_data.clear()
            st.toast("¡RPE registrado y guardado con éxito!", icon="✅")
            st.balloons()

            rpe_vals = list(selected_dict.values())
            avg_rpe = sum(rpe_vals) / len(rpe_vals)
            avg_srpe = avg_rpe * duration_min
            cat_text, cat_color = get_rpe_category(avg_rpe)

            st.success(f"¡Cálculos completados con éxito para la sesión '{sess_name}'!")

            # 4 KPIs principales
            r1, r2, r3, r4 = st.columns(4)
            with r1:
                st.markdown(f"""
                <div class="metric-card">
                    <div class="metric-title">RPE Promedio de la Sesión</div>
                    <div class="metric-value" style="color: {cat_color};">{avg_rpe:.2f} / 10</div>
                    <div class="metric-subtitle">Muestra: {len(rpe_vals)} futbolistas</div>
                </div>
                """, unsafe_allow_html=True)

            with r2:
                st.markdown(f"""
                <div class="metric-card">
                    <div class="metric-title">Percepción Cualitativa</div>
                    <div class="metric-value" style="font-size: 1.15rem; color: {cat_color};">{cat_text}</div>
                    <div class="metric-subtitle">Intensidad global del grupo</div>
                </div>
                """, unsafe_allow_html=True)

            with r3:
                st.markdown(f"""
                <div class="metric-card">
                    <div class="metric-title">Carga Interna Media (sRPE)</div>
                    <div class="metric-value">{avg_srpe:.0f} AU</div>
                    <div class="metric-subtitle">{avg_rpe:.1f} RPE × {duration_min} min</div>
                </div>
                """, unsafe_allow_html=True)

            with r4:
                max_rpe_val = max(rpe_vals)
                max_p_row = selected_rows[selected_rows["RPE (1-10)"] == max_rpe_val].iloc[0]
                st.markdown(f"""
                <div class="metric-card">
                    <div class="metric-title">Pico de Esfuerzo Máximo</div>
                    <div class="metric-value" style="color: #EF4444;">{max_rpe_val:.1f} / 10</div>
                    <div class="metric-subtitle">#{int(max_p_row['Dorsal'])} {max_p_row['Jugador']}</div>
                </div>
                """, unsafe_allow_html=True)

            # Desglose en tabla resumen
            st.subheader("Desglose de Futbolistas Encuestados (Foster)")
            summary_rows = []
            for _, row in selected_rows.iterrows():
                val = float(row["RPE (1-10)"])
                c_cat, _ = get_rpe_category(val)
                p_srpe = val * duration_min
                td_val = float(row["Distancia GPS (m)"])
                eff_ratio = (td_val / val) if val > 0 else 0.0
                summary_rows.append({
                    "Dorsal": int(row["Dorsal"]),
                    "Futbolista": row["Jugador"],
                    "Posición": row["Posición"],
                    "Distancia GPS (m)": f"{td_val:.0f}",
                    "RPE (1-10)": f"{val:.1f}",
                    "Carga Interna (sRPE AU)": f"{p_srpe:.0f}",
                    "Eficiencia (m/RPE)": f"{eff_ratio:.0f}",
                    "Percepción": c_cat
                })

            df_rpe_summary = pd.DataFrame(summary_rows).sort_values(by="RPE (1-10)", ascending=False)
            st.dataframe(df_rpe_summary, width="stretch", hide_index=True)


# ==========================================
# VISTA 4: INGESTA DE ARCHIVO UBIKO
# ==========================================
elif menu == "📥 Ingesta de Datos GPS (UBIKO)":
    st.title("Ingesta y Procesamiento de Sesiones GPS UBIKO")
    st.markdown("Sube una exportación de chalecos GPS UBIKO en formato **.xlsx** o **.csv** para integrarla en la base de datos.")

    uploaded_file = st.file_uploader("Arrastra o selecciona el informe GPS:", type=["csv", "xlsx"])

    col_i1, col_i2, col_i3 = st.columns(3)
    with col_i1:
        ingest_date = st.date_input("Fecha de la Sesión:", value=date.today())
    with col_i2:
        ingest_micro = st.selectbox("Día del Microciclo:", MICROCYCLE_DAYS, index=1)
    with col_i3:
        ingest_type = st.selectbox("Tipo de Sesión:", ["Entrenamiento", "Partido"])

    col_i4, col_i5 = st.columns([1, 2])
    with col_i4:
        ingest_duration = st.number_input("Duración de la Sesión (min):", min_value=10, max_value=150, value=75)
    with col_i5:
        ingest_notes = st.text_input("Observaciones de la sesión:", placeholder="Ej. Tareas reducidas con alta intensidad y posesión 6v6")

    if uploaded_file is not None:
        try:
            df_parsed = UbikoImporter.parse_file(uploaded_file, uploaded_file.name)
            st.success(f"Archivo parseado correctamente: {len(df_parsed)} filas encontradas.")

            st.subheader("Previsualización de Columnas Mapeadas:")
            st.dataframe(df_parsed.head(8), width="stretch")

            if st.button("🚀 Guardar Sesión en Base de Datos"):
                with get_db() as db:
                    sess_name = f"{ingest_type} - {ingest_micro} ({ingest_date.strftime('%d/%m')})"
                    res = UbikoImporter.import_session_to_db(
                        db_session=db,
                        df_parsed=df_parsed,
                        session_date=ingest_date,
                        session_name=sess_name,
                        microcycle_day=ingest_micro,
                        session_type=ingest_type,
                        duration_minutes=ingest_duration,
                        notes=ingest_notes
                    )

                st.balloons()
                st.success(f"¡Sesión registrada con éxito! {res['players_processed']} jugadores procesados.")
                if res.get("warnings"):
                    for w in res["warnings"]:
                        st.info(w)

        except Exception as e:
            st.error(f"Error procesando el archivo: {e}")

    # Carga rápida de la sesión real del Salerm Puente Genil
    st.divider()
    st.subheader("⚡ Carga Rápida: Sesión Real Salerm Cosmetics Puente Genil")
    st.caption("Prueba de ingesta inmediata con el archivo exportado de UBIKO (MD+1 Compensatorio).")

    real_csv_path = SAMPLES_DIR / "sesion_real_puente_genil.csv"
    if real_csv_path.exists():
        if st.button("📥 Importar Sesión Real del Puente Genil ahora"):
            try:
                df_real = UbikoImporter.parse_file(str(real_csv_path), real_csv_path.name)
                with get_db() as db:
                    res_real = UbikoImporter.import_session_to_db(
                        db_session=db,
                        df_parsed=df_real,
                        session_date=date(2026, 9, 7),
                        session_name="SESIÓN 26 - MD+1 COMPENSATORIO",
                        microcycle_day="MD+1",
                        session_type="Entrenamiento",
                        duration_minutes=65,
                        notes="Sesión compensatoria real de los chalecos GPS UBIKO del Salerm Puente Genil"
                    )
                st.balloons()
                st.success(f"¡Sesión real del Salerm Puente Genil importada! {res_real['players_processed']} futbolistas cargados.")
                st.info("Ya puedes seleccionarla en el desplegable de la izquierda para ver su informe y semáforos.")
            except Exception as ex:
                st.error(f"Error al importar: {ex}")

    # Sincronización Automática con UBIKO Web (Playwright)
    st.divider()
    st.subheader("🌐 Sincronización Directa con UBIKO Web (Bot Playwright)")
    st.markdown("""
    Conecta automáticamente con la web de UBIKO, localiza todas las sesiones computadas desde la fecha seleccionada, 
    descarga los archivos **CSV** de telemetría de forma desatendida y genera los informes tácticos para el cuerpo técnico.
    """)

    col_w1, col_w2, col_w3 = st.columns([2, 1, 1])
    with col_w1:
        ubiko_url_input = st.text_input("URL del portal UBIKO:", value="https://admin.ubikosports.com/team/sessions")
    with col_w2:
        sync_since_tab = st.date_input("Recopilar desde:", value=date(2026, 9, 3), key="tab_sync_date")
    with col_w3:
        visible_browser = st.checkbox("Navegador visible", value=True, help="Recomendado activo para verificar el proceso o iniciar sesión.")
        force_sync_tab = st.checkbox("Forzar re-descarga", value=False, key="tab_force_sync")

    if st.button("🚀 Iniciar Recopilación Masiva desde UBIKO Web"):
        with st.spinner(f"Conectando a UBIKO Web y recopilando todas las sesiones desde {sync_since_tab.strftime('%d/%m/%Y')}..."):
            try:
                import importlib
                import ubiko_sync
                importlib.reload(ubiko_sync)
                service = ubiko_sync.UbikoSyncService(base_url=ubiko_url_input, headless=not visible_browser)
                res_web = service.fetch_and_sync(force=force_sync_tab, min_date=sync_since_tab)

                if res_web.get("success"):
                    st.balloons()
                    st.success(res_web.get("message", "Sincronizado con éxito"))
                    if res_web.get("sessions"):
                        st.subheader("Sesiones Integradas:")
                        st.dataframe(pd.DataFrame(res_web["sessions"]).rename(columns={
                            "id": "ID Sesión",
                            "name": "Nombre",
                            "date": "Fecha",
                            "players_count": "Jugadores Procesados",
                            "status": "Estado"
                        }), width="stretch", hide_index=True)
                    if res_web.get("report"):
                        st.subheader("Último Informe Táctico Generado:")
                        st.markdown(f'<div class="report-box">{res_web["report"]}</div>', unsafe_allow_html=True)
                else:
                    st.warning(res_web.get("message", "Aviso durante la sincronización"))

            except Exception as e_bot:
                st.error(f"Error al ejecutar la sincronización: {e_bot}")

    # Mantenimiento y Purga de Datos Falsos
    st.divider()
    st.subheader("🧹 Mantenimiento de Base de Datos: Limpiar Datos Simulados")
    st.info(
        "Si generaste datos de prueba anteriormente y ahora deseas que Supabase contenga **exclusivamente** "
        "las sesiones y métricas reales de UBIKO (eliminando cualquier registro falso para que porteros como Estepa y Luengo "
        "no tengan datos ficticios de carrera), pulsa el botón a continuación. La plantilla de 26 jugadores y objetivos permanecerá intacta."
    )
    if st.button("🗑️ Purgar Sesiones y Métricas Simuladas de Supabase", type="secondary"):
        from seed_data import purge_simulated_sessions_and_metrics
        n_s, n_m = purge_simulated_sessions_and_metrics()
        st.success(f"¡Base de datos limpia! Se han eliminado {n_s} sesiones y {n_m} registros de métricas. Ya puedes sincronizar desde UBIKO.")
        st.rerun()


# ==========================================
# VISTA 5: OBJETIVOS DE CARGA FISIOLÓGICA
# ==========================================
elif menu == "⚙️ Objetivos de Carga Fisiológica":
    st.title("Configuración de Objetivos de Carga por Microciclo")
    st.markdown(
        "Parámetros de referencia prescritos por el preparador físico para cada demarcación táctica según el día de la semana. "
        "El sistema los utiliza como estándar para calcular el porcentaje de cumplimiento real de las tareas de entrenamiento."
    )

    with get_db() as db:
        targets_all = db.query(TargetLoad).all()
        target_rows = [
            {
                "Microciclo": t.microcycle_day,
                "Posición": t.position,
                "Distancia Total (m)": t.target_td,
                "HSR (m)": t.target_hsr,
                "HMLD (m)": t.target_hmld,
                "Acc. Eficaces": t.target_acc_eff,
                "Dec. Eficaces": t.target_dec_eff,
                "Total AC.E": t.target_acc_eff + t.target_dec_eff
            }
            for t in targets_all
        ]

    if target_rows:
        df_tgt = pd.DataFrame(target_rows)
        selected_day = st.selectbox("Filtrar por Día de Microciclo:", ["Todos"] + MICROCYCLE_DAYS)
        if selected_day != "Todos":
            df_tgt = df_tgt[df_tgt["Microciclo"] == selected_day]

        st.dataframe(df_tgt, width="stretch", hide_index=True)
    else:
        st.info("No hay objetivos configurados en la base de datos.")
