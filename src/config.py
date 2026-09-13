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
MICROCYCLE_DAYS = ["MD-4", "MD-3", "MD-2", "MD-1", "MD"]

MICROCYCLE_DESCRIPTIONS = {
    "MD-4": "Tensión y Fuerza (Espacios reducidos, alta densidad de aceleraciones)",
    "MD-3": "Duración y Resistencia (Espacios amplios, alta distancia total y HSR)",
    "MD-2": "Velocidad y Táctica (Estimulación neuromuscular, velocidad máxima)",
    "MD-1": "Activación y Balón Parado (Volumen mínimo, frescura para el partido)",
    "MD": "Competición / Partido Oficial (Carga máxima de referencia)"
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

# Umbrales de Cumplimiento Planificado vs Real
COMPLIANCE_LOW_WARNING = 75.0   # Menos del 75%: déficit notable
COMPLIANCE_OPTIMAL_MIN = 88.0   # 88% - 112%: cumplimiento óptimo
COMPLIANCE_OPTIMAL_MAX = 112.0
COMPLIANCE_HIGH_WARNING = 125.0  # Más del 125%: sobrecarga imprevista
