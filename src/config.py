"""
Configuración global del sistema de análisis de datos GPS UBIKO.
Define rutas, constantes de microciclo, umbrales de fatiga ACWR y parámetros del motor analítico.
"""

import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

# Rutas del proyecto
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
SAMPLES_DIR = DATA_DIR / "samples"
DATABASE_PATH = DATA_DIR / "ubiko_db.sqlite3"

def _clean_database_url(raw_url: str) -> str:
    """
    Sanitiza la URL de conexión a la base de datos:
    - Normaliza prefijo postgres:// a postgresql://
    - Detecta automáticamente los controladores PostgreSQL instalados (psycopg v3 o psycopg2 v2)
    - Adapta el dialecto de SQLAlchemy dinámicamente para prevenir errores de 'No module named psycopg'
    - Elimina parámetros de query string incompatibles con libpq/psycopg DSN (como pgbouncer=true)
    """
    if not raw_url:
        return f"sqlite:///{DATABASE_PATH.as_posix()}"

    url = raw_url.strip()
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)

    # Si es SQLite, retornar tal cual
    if url.startswith("sqlite"):
        return url

    # Comprobar qué controladores PostgreSQL están disponibles en el entorno de ejecución
    try:
        import psycopg  # psycopg v3
        has_psycopg3 = True
    except ImportError:
        has_psycopg3 = False

    try:
        import psycopg2  # psycopg2 v2
        has_psycopg2 = True
    except ImportError:
        has_psycopg2 = False

    # Normalizar el controlador en el esquema de la URL:
    if "postgresql+psycopg://" in url:
        if not has_psycopg3 and has_psycopg2:
            url = url.replace("postgresql+psycopg://", "postgresql+psycopg2://", 1)
    elif "postgresql+psycopg2://" in url:
        if not has_psycopg2 and has_psycopg3:
            url = url.replace("postgresql+psycopg2://", "postgresql+psycopg://", 1)
    elif url.startswith("postgresql://") and not ("+" in url.split("://")[0]):
        # URL genérica 'postgresql://': elegir el controlador disponible
        if has_psycopg3 and not has_psycopg2:
            url = url.replace("postgresql://", "postgresql+psycopg://", 1)
        elif has_psycopg2:
            url = url.replace("postgresql://", "postgresql+psycopg2://", 1)

    # Para PostgreSQL, limpiar parámetros de consulta incompatibles con psycopg/libpq
    try:
        parsed = urlparse(url)
        if parsed.query:
            query_params = parse_qs(parsed.query, keep_blank_values=True)
            # Lista de parámetros incompatibles con psycopg/libpq DSN
            unsupported_params = {"pgbouncer", "schema", "connection_limit", "pool_timeout"}
            cleaned_params = {k: v for k, v in query_params.items() if k.lower() not in unsupported_params}
            
            # Reconstruir query string limpia
            new_query = urlencode(cleaned_params, doseq=True)
            parsed = parsed._replace(query=new_query)
            url = urlunparse(parsed)
    except Exception:
        pass

    return url


def get_configured_database_url() -> str:
    """Obtiene la URL de base de datos desde variables de entorno o st.secrets."""
    raw = os.getenv("DATABASE_URL")
    if not raw:
        try:
            import streamlit as st
            if hasattr(st, "secrets"):
                if "DATABASE_URL" in st.secrets:
                    raw = str(st.secrets["DATABASE_URL"])
                elif "connections" in st.secrets and "postgresql" in st.secrets["connections"]:
                    raw = str(st.secrets["connections"]["postgresql"].get("url", ""))
                elif "postgres" in st.secrets and "url" in st.secrets["postgres"]:
                    raw = str(st.secrets["postgres"].get("url", ""))
        except Exception:
            pass
    return _clean_database_url(raw or f"sqlite:///{DATABASE_PATH.as_posix()}")


DATABASE_URL = get_configured_database_url()

# Asegurar que las carpetas existan
DATA_DIR.mkdir(parents=True, exist_ok=True)
SAMPLES_DIR.mkdir(parents=True, exist_ok=True)

# Demarcaciones tácticas estándar en fútbol profesional
POSITIONS = [
    "Portero",
    "Central",
    "Lateral",
    "Mediocentro",
    "Extremo",
    "Delantero"
]

# Días del microciclo estructurado según metodología de periodización táctica
MICROCYCLE_DAYS = ["MD-4", "MD-3", "MD-2", "MD-1", "MD", "MD+1", "MD+2"]

MICROCYCLE_DESCRIPTIONS = {
    "MD-4": "Tensión y Fuerza (Espacios reducidos, alta densidad de aceleraciones)",
    "MD-3": "Duración y Resistencia (Espacios amplios, alta distancia total y HSR)",
    "MD-2": "Velocidad y Táctica (Estimulación neuromuscular, velocidad máxima)",
    "MD-1": "Activación y Balón Parado (Volumen mínimo, frescura para el partido)",
    "MD": "Competición / Partido Oficial (Carga máxima de referencia)",
    "MD+1": "Recuperación y Compensación (Descarga activos, compensación suplentes)",
    "MD+2": "Recuperación y Compensación (Compensatorio suplentes / descarga activos)"
}

# Parámetros del modelo ACWR (Acute:Chronic Workload Ratio) con EWMA (Williams et al., 2017)
EWMA_ACUTE_DAYS = 7
EWMA_CHRONIC_DAYS = 28
LAMBDA_ACUTE = 2.0 / (EWMA_ACUTE_DAYS + 1.0)       # 0.25
LAMBDA_CHRONIC = 2.0 / (EWMA_CHRONIC_DAYS + 1.0)   # ~0.069

# Umbrales del semáforo ACWR (Tim Gabbett, 2016)
ACWR_UNDERLOAD = 0.80     # Por debajo: Subentrenamiento / Riego de desadaptación
ACWR_SWEET_SPOT_MAX = 1.30 # Rango 0.80 - 1.30: 'Sweet Spot' (Zona segura de adaptación óptima)
ACWR_DANGER_ZONE = 1.50   # Por encima de 1.50: Zona de riesgo exponencial de lesión

# Umbrales para Z-Scores posicionales
Z_SCORE_NORMAL = 1.0
Z_SCORE_WARNING = 1.75

# Configuración Multitenant (Multiclub)
DEFAULT_CLUB_ID = int(os.getenv("DEFAULT_CLUB_ID", 1))

# Objetivos del microciclo relativos al Partido de Máxima Exigencia (100% individual)
# Según periodización táctica pactada con el preparador físico:
# MD-4 (Tensión/Fuerza): AC.E clave (objetivo ~90-95% AC.E)
# MD-3 (Resistencia/Duración): Volumen clave (objetivo ~80-85% DT)
# MD-2 (Velocidad/Táctica): Alta intensidad clave (objetivo ~65-75% HSR / picos sprint)
# MD-1 (Activación): Volumen muy reducido (40-50% DT)
MICROCYCLE_MATCH_TARGETS = {
    "MD-4": {
        "primary_metric": "acc_dec_eff",
        "primary_label": "AC.E (Acel.+Desacel. Eficaces)",
        "key_label": "AC.E (Acel.+Desacel. Eficaces)",
        "description": "Tensión y Fuerza neuromuscular (Esfuerzos máximos de aceleración y deceleración)",
        "target_pct": 92.5,     # 90% - 95%
        "pct_td": 0.58,
        "pct_hsr": 0.40,
        "pct_hmld": 0.55,
        "pct_eff": 0.925
    },
    "MD-3": {
        "primary_metric": "total_distance",
        "primary_label": "Distancia Total (DT)",
        "key_label": "Distancia Total (DT)",
        "description": "Resistencia y Duración táctica (Máximo volumen acumulado)",
        "target_pct": 82.5,     # 80% - 85%
        "pct_td": 0.825,
        "pct_hsr": 0.65,
        "pct_hmld": 0.78,
        "pct_eff": 0.65
    },
    "MD-2": {
        "primary_metric": "hsr_distance",
        "primary_label": "HSR (>21 km/h)",
        "key_label": "HSR (>21 km/h)",
        "description": "Velocidad y Reactividad neuromuscular (Picos de alta intensidad)",
        "target_pct": 70.0,     # 65% - 75%
        "pct_td": 0.52,
        "pct_hsr": 0.70,
        "pct_hmld": 0.58,
        "pct_eff": 0.50
    },
    "MD-1": {
        "primary_metric": "total_distance",
        "primary_label": "Distancia Total (Activación)",
        "key_label": "Distancia Total (Activación)",
        "description": "Activación y Balón Parado (Volumen mínimo, frescura para el partido)",
        "target_pct": 45.0,     # 40% - 50%
        "pct_td": 0.45,
        "pct_hsr": 0.25,
        "pct_hmld": 0.35,
        "pct_eff": 0.30
    },
    "MD": {
        "primary_metric": "total_distance",
        "primary_label": "Partido (100% Referencia)",
        "key_label": "Partido (100% Referencia)",
        "description": "Competición Oficial (100% de máxima exigencia)",
        "target_pct": 100.0,
        "pct_td": 1.00,
        "pct_hsr": 1.00,
        "pct_hmld": 1.00,
        "pct_eff": 1.00
    },
    "MD+1": {
        "primary_metric": "total_distance",
        "primary_label": "Recuperación / Compensación",
        "key_label": "Recuperación (DT)",
        "description": "Recuperación activa y compensación de carga",
        "target_pct": 50.0,
        "pct_td": 0.50,
        "pct_hsr": 0.20,
        "pct_hmld": 0.30,
        "pct_eff": 0.30
    },
    "MD+2": {
        "primary_metric": "total_distance",
        "primary_label": "Compensatorio / Recuperación",
        "key_label": "Compensatorio (DT)",
        "description": "Compensación de carga para suplentes y descarga activa",
        "target_pct": 50.0,
        "pct_td": 0.50,
        "pct_hsr": 0.25,
        "pct_hmld": 0.35,
        "pct_eff": 0.35
    }
}


# =============================================================================
# MATRIZ OFICIAL DE OBJETIVOS GPS MICROCICLO - SALERM PUENTE GENIL F.C.
# (Parámetros referenciales validados para Mesociclos 1 y 2 por el P.F.)
# =============================================================================
SALERM_PUENTE_GENIL_MATRIX = {
    "MD+1": {
        "day_name": "Lunes",
        "label": "MD+1 (Compensatorio)",
        "objective": "COMPENSATORIO",
        "foco": "Compensación de carga competitiva para suplentes/no convocados",
        "dist_km_min": 4.0, "dist_km_max": 6.0,
        "dist_m_min": 4000.0, "dist_m_max": 6000.0,
        "m_min_min": 60.0, "m_min_max": 80.0,
        "hsr_min": 250.0, "hsr_max": 320.0,
        "sprint_m_min": 100.0, "sprint_m_max": 190.0,
        "sprints_cnt_min": 8, "sprints_cnt_max": 15,
        "acc_target": 80, "acc_min": 65, "acc_max": 95,
        "dec_target": 120, "dec_min": 100, "dec_max": 140,
        "rpe_target": 8,
        "badge_color": "#EF4444"
    },
    "MD+2": {
        "day_name": "Martes",
        "label": "MD+2 (Descanso)",
        "objective": "RESET / DESCANSO",
        "foco": "Recuperación pasiva y regeneración biológica",
        "dist_km_min": 0.0, "dist_km_max": 0.0,
        "dist_m_min": 0.0, "dist_m_max": 0.0,
        "m_min_min": 0.0, "m_min_max": 0.0,
        "hsr_min": 0.0, "hsr_max": 0.0,
        "sprint_m_min": 0.0, "sprint_m_max": 0.0,
        "sprints_cnt_min": 0, "sprints_cnt_max": 0,
        "acc_target": 0, "acc_min": 0, "acc_max": 0,
        "dec_target": 0, "dec_min": 0, "dec_max": 0,
        "rpe_target": 0,
        "badge_color": "#10B981"
    },
    "MD-4": {
        "day_name": "Miércoles",
        "label": "MD-4 (Tensión y Fuerza)",
        "objective": "ACC / DCC (TENSIÓN Y FUERZA)",
        "foco": "Espacios reducidos, alta densidad de aceleraciones y desaceleraciones",
        "dist_km_min": 5.0, "dist_km_max": 7.0,
        "dist_m_min": 5000.0, "dist_m_max": 7000.0,
        "m_min_min": 70.0, "m_min_max": 90.0,
        "hsr_min": 100.0, "hsr_max": 250.0,
        "sprint_m_min": 50.0, "sprint_m_max": 70.0,
        "sprints_cnt_min": 6, "sprints_cnt_max": 8,
        "acc_target": 90, "acc_min": 80, "acc_max": 100,
        "dec_target": 95, "dec_min": 70, "dec_max": 120,
        "rpe_target": 7,
        "badge_color": "#881337"
    },
    "MD-3": {
        "day_name": "Jueves",
        "label": "MD-3 (Resistencia y Duración)",
        "objective": "HSR / SPRINT (ESPACIOS AMPLIOS)",
        "foco": "Espacios amplios, alta distancia total, máximo HSR y sprint acumulado",
        "dist_km_min": 8.0, "dist_km_max": 10.0,
        "dist_m_min": 8000.0, "dist_m_max": 10000.0,
        "m_min_min": 85.0, "m_min_max": 100.0,
        "hsr_min": 450.0, "hsr_max": 650.0,
        "sprint_m_min": 150.0, "sprint_m_max": 250.0,
        "sprints_cnt_min": 8, "sprints_cnt_max": 15,
        "acc_target": 85, "acc_min": 70, "acc_max": 100,
        "dec_target": 95, "dec_min": 80, "dec_max": 110,
        "rpe_target": 8,
        "badge_color": "#9A3412"
    },
    "MD-2": {
        "day_name": "Viernes",
        "label": "MD-2 (Velocidad y Táctica)",
        "objective": "VELOCIDAD / COHESIÓN / ABP",
        "foco": "Estimulación neuromuscular pura, velocidad máxima y frescura",
        "dist_km_min": 3.5, "dist_km_max": 4.0,
        "dist_m_min": 3500.0, "dist_m_max": 4000.0,
        "m_min_min": 30.0, "m_min_max": 55.0,
        "hsr_min": 100.0, "hsr_max": 200.0,
        "sprint_m_min": 10.0, "sprint_m_max": 30.0,
        "sprints_cnt_min": 3, "sprints_cnt_max": 6,
        "acc_target": 40, "acc_min": 30, "acc_max": 50,
        "dec_target": 35, "dec_min": 25, "dec_max": 45,
        "rpe_target": 3,
        "badge_color": "#0284C7"
    },
    "MD-1": {
        "day_name": "Sábado",
        "label": "MD-1 (Activación y Reactividad)",
        "objective": "REACCIÓN / EXPLOSIVIDAD",
        "foco": "Activación, balón parado y frescura neuromuscular previa a competición",
        "dist_km_min": 2.0, "dist_km_max": 3.0,
        "dist_m_min": 2000.0, "dist_m_max": 3000.0,
        "m_min_min": 40.0, "m_min_max": 60.0,
        "hsr_min": 45.0, "hsr_max": 90.0,
        "sprint_m_min": 15.0, "sprint_m_max": 40.0,
        "sprints_cnt_min": 2, "sprints_cnt_max": 4,
        "acc_target": 22, "acc_min": 15, "acc_max": 30,
        "dec_target": 17, "dec_min": 10, "dec_max": 25,
        "rpe_target": 4,
        "badge_color": "#EAB308"
    },
    "MD": {
        "day_name": "Domingo",
        "label": "MD (Competición Oficial)",
        "objective": "MÁXIMA EXIGENCIA",
        "foco": "Competición oficial de 90+ minutos (100% de referencia de partido)",
        "dist_km_min": 10.0, "dist_km_max": 14.0,
        "dist_m_min": 10000.0, "dist_m_max": 14000.0,
        "m_min_min": 50.0, "m_min_max": 90.0,
        "hsr_min": 300.0, "hsr_max": 650.0,
        "sprint_m_min": 100.0, "sprint_m_max": 200.0,
        "sprints_cnt_min": 8, "sprints_cnt_max": 15,
        "acc_target": 105, "acc_min": 80, "acc_max": 130,
        "dec_target": 110, "dec_min": 90, "dec_max": 130,
        "rpe_target": 10,
        "badge_color": "#DC2626"
    }
}


