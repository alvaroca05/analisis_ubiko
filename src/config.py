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
    - Elimina parámetros de query string incompatibles con libpq/psycopg2 DSN (como pgbouncer=true)
    """
    if not raw_url:
        return f"sqlite:///{DATABASE_PATH.as_posix()}"

    url = raw_url.strip()
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)

    # Si es SQLite, retornar tal cual
    if url.startswith("sqlite"):
        return url

    # Para PostgreSQL, limpiar parámetros de consulta incompatibles con psycopg2
    try:
        parsed = urlparse(url)
        if parsed.query:
            query_params = parse_qs(parsed.query, keep_blank_values=True)
            # Lista de parámetros incompatibles con psycopg2/libpq DSN
            unsupported_params = {"pgbouncer", "schema", "connection_limit", "pool_timeout"}
            cleaned_params = {k: v for k, v in query_params.items() if k.lower() not in unsupported_params}
            
            # Reconstruir query string limpia
            new_query = urlencode(cleaned_params, doseq=True)
            parsed = parsed._replace(query=new_query)
            url = urlunparse(parsed)
    except Exception:
        pass

    return url

DATABASE_URL = _clean_database_url(os.getenv("DATABASE_URL", f"sqlite:///{DATABASE_PATH.as_posix()}"))

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
MICROCYCLE_DAYS = ["MD-4", "MD-3", "MD-2", "MD-1", "MD", "MD+1"]

MICROCYCLE_DESCRIPTIONS = {
    "MD-4": "Tensión y Fuerza (Espacios reducidos, alta densidad de aceleraciones)",
    "MD-3": "Duración y Resistencia (Espacios amplios, alta distancia total y HSR)",
    "MD-2": "Velocidad y Táctica (Estimulación neuromuscular, velocidad máxima)",
    "MD-1": "Activación y Balón Parado (Volumen mínimo, frescura para el partido)",
    "MD": "Competición / Partido Oficial (Carga máxima de referencia)",
    "MD+1": "Recuperación y Compensación (Descarga activos, compensación suplentes)"
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
    }
}

