"""
Módulo de importación y procesamiento de informes de exportación GPS de UBIKO (.csv / .xlsx).
Diseñado específicamente para la estructura real exportada por el software UBIKO:
- Soporte para delimitador punto y coma (;) y formato numérico europeo (puntos de miles y comas decimales).
- Filtrado automático de tareas (selección de fila de consolidado 'Total' si la sesión contiene drills).
- Mapeo de demarcaciones tácticas estándar (defender/LTI -> Lateral, defender/CIZ -> Central, etc.).
"""

import re
from pathlib import Path
from datetime import date, datetime
from io import BytesIO, StringIO
from typing import Any, Dict, List, Optional, Union
import pandas as pd
from sqlalchemy.orm import Session

from src.config import DEFAULT_CLUB_ID, SAMPLES_DIR
from src.database.models import Player, TrainingSession, PlayerMetric



# Mapeo de sinónimos de columnas comunes en exportaciones de UBIKO
COLUMN_MAPPINGS = {
    "player_name": ["player", "jugador", "nombre", "atleta", "name", "futbolista"],
    "dorsal": ["dorsal", "numero", "number", "num", "#"],
    "position": ["position", "posicion", "pos", "demarcacion", "puesto"],
    "minutes_played": ["time", "minutos", "minutes", "tiempo", "time_min", "duration", "duracion"],
    "total_distance": ["total_distance", "distancia_total", "dt", "distance", "distancia_(m)", "distancia"],
    "hsr_distance": ["num_hsr", "hsr", "high_speed_running", "distancia_hsr", "distancia_>_19.8", "time_vrange5"],
    "sprint_distance": ["sprints", "sprint", "sprint_distance", "distancia_sprint", "time_vrange6"],
    "hmld": ["hmld", "high_metabolic_load_distance", "distancia_metabolica", "hmld_(m)"],
    "accelerations_eff": ["num_acc_expl", "aceleraciones", "acc", "acc_eficaces", "acc_>_3m/s2", "accelerations"],
    "decelerations_eff": ["num_dec_expl", "desaceleraciones", "dec", "dec_eficaces", "dec_<_3m/s2", "decelerations"],
    "max_speed": ["max_speed", "velocidad_maxima", "v_max", "vmax", "speed_max_(km/h)", "v_max_(km/h)"],
    "player_load": ["player_load", "playerload", "carga", "pl", "carga_mecanica"],
    "rpe": ["rpe", "borg", "esfuerzo_percibido", "rpe_sesion"]
}

# Normalizador de demarcaciones de UBIKO
UBIKO_POSITION_MAP = {
    "lti": "Lateral",
    "ltd": "Lateral",
    "ciz": "Central",
    "cde": "Central",
    "cen": "Central",
    "defender": "Central",
    "mc": "Mediocentro",
    "mp": "Mediocentro",
    "mcd": "Mediocentro",
    "midfield": "Mediocentro",
    "ed": "Extremo",
    "ei": "Extremo",
    "ext": "Extremo",
    "dc": "Delantero",
    "forward": "Delantero",
    "gk": "Portero",
    "portero": "Portero"
}


def parse_spanish_number(val: Any) -> float:
    """
    Convierte números en formato español (ej. '3.603,892' o '65,030') a float de Python.
    """
    if pd.isna(val) or val is None or val == "":
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip()
    # Si contiene punto y coma: ej. 1.022,791
    if "." in s and "," in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except (ValueError, TypeError):
        return 0.0


def map_ubiko_position(raw_pos: str) -> str:
    """
    Convierte cadenas como 'defender/LTI' o 'midfield/MC' a posiciones estándar del sistema.
    """
    if not raw_pos or pd.isna(raw_pos):
        return "Mediocentro"

    s = str(raw_pos).lower().strip()
    parts = s.split("/")
    sub_tag = parts[-1] if len(parts) > 1 else parts[0]

    for key, canonical in UBIKO_POSITION_MAP.items():
        if sub_tag == key or key in sub_tag:
            return canonical

    return "Mediocentro"


class UbikoImporter:
    """
    Parser y gestor de ingesta de sesiones GPS UBIKO.
    """

    @staticmethod
    def _normalize_col_name(col: str) -> str:
        """Normaliza un nombre de columna para matching sin acentos ni caracteres especiales."""
        c = str(col).lower().strip()
        c = c.replace(" ", "_").replace(".", "").replace("/", "_").replace("-", "_")
        c = c.replace("á", "a").replace("é", "e").replace("í", "i").replace("ó", "o").replace("ú", "u")
        return c

    @classmethod
    def parse_file(cls, file_or_path: Union[str, BytesIO], filename: str = "") -> pd.DataFrame:
        """
        Lee el archivo Excel o CSV y devuelve un DataFrame normalizado con las columnas estándar.
        """
        fname = filename.lower() if filename else str(file_or_path).lower()

        if fname.endswith(".xlsx") or fname.endswith(".xls"):
            df = pd.read_excel(file_or_path)
        else:
            # Intento de delimitador coma o punto y coma
            try:
                df = pd.read_csv(file_or_path, sep=";")
                if len(df.columns) <= 1:
                    df = pd.read_csv(file_or_path, sep=",")
            except Exception:
                df = pd.read_csv(file_or_path, sep=None, engine="python")

        # Filtrar fila de consolidado 'Total' si la sesión desglosa tareas/ejercicios
        task_col = next((c for c in df.columns if cls._normalize_col_name(c) == "task"), None)
        if task_col:
            has_total = df[task_col].astype(str).str.strip().str.lower().eq("total").any()
            if has_total:
                df = df[df[task_col].astype(str).str.strip().str.lower().eq("total")].copy()

        # Mapear columnas encontradas a las canónicas
        raw_cols = {c: cls._normalize_col_name(c) for c in df.columns}
        rename_dict = {}

        for canonical_name, aliases in COLUMN_MAPPINGS.items():
            for original_col, normalized in raw_cols.items():
                if normalized in aliases:
                    rename_dict[original_col] = canonical_name
                    break

        df_mapped = df.rename(columns=rename_dict)

        # Descartar filas vacías o de resumen global sin jugador
        if "player_name" in df_mapped.columns:
            df_mapped = df_mapped[
                df_mapped["player_name"].notna() &
                (df_mapped["player_name"].astype(str).str.strip() != "")
            ].copy()

        # Normalizar demarcaciones
        if "position" in df_mapped.columns:
            df_mapped["position"] = df_mapped["position"].apply(map_ubiko_position)

        # Convertir números con coma/punto español a float
        numeric_cols = [
            "total_distance", "hsr_distance", "sprint_distance", "hmld",
            "accelerations_eff", "decelerations_eff", "max_speed",
            "player_load", "minutes_played", "rpe"
        ]
        for col in numeric_cols:
            if col in df_mapped.columns:
                df_mapped[col] = df_mapped[col].apply(parse_spanish_number)

        # Si HSR o Sprint proceden de columnas de tiempo (time_vrange5 / time_vrange6 en minutos),
        # convertir a metros reales utilizando las velocidades estándar del rango:
        # V5 (HSR 19.8 - 25.2 km/h): ~22.5 km/h = 6.25 m/s -> minutos * 60 * 6.25 = minutos * 375 m
        # V6 (Sprint > 25.2 km/h): ~27.0 km/h = 7.50 m/s -> minutos * 60 * 7.50 = minutos * 450 m
        for orig_col, canon in rename_dict.items():
            norm_orig = raw_cols.get(orig_col, "")
            if canon == "hsr_distance" and "vrange5" in norm_orig:
                if "hsr_distance" in df_mapped.columns and df_mapped["hsr_distance"].max() < 30.0:
                    df_mapped["hsr_distance"] = (df_mapped["hsr_distance"] * 375.0).round(1)
            elif canon == "sprint_distance" and "vrange6" in norm_orig:
                if "sprint_distance" in df_mapped.columns and df_mapped["sprint_distance"].max() < 30.0:
                    df_mapped["sprint_distance"] = (df_mapped["sprint_distance"] * 450.0).round(1)

        return df_mapped

    @staticmethod
    def _normalize_name(name: str) -> str:
        """Normaliza un nombre de jugador para matching (minúsculas, sin acentos ni espacios extra)."""
        import unicodedata
        if not name:
            return ""
        s = str(name).strip().lower()
        s = unicodedata.normalize("NFKD", s)
        s = "".join(c for c in s if not unicodedata.combining(c))
        return s

    @classmethod
    def import_session_to_db(
        cls,
        db_session: Session,
        df_parsed: pd.DataFrame,
        session_date: date,
        session_name: str,
        microcycle_day: str,
        session_type: str = "Entrenamiento",
        duration_minutes: int = 75,
        notes: str = "",
        club_id: int = DEFAULT_CLUB_ID
    ) -> Dict[str, Any]:
        """
        Guarda la sesión y las métricas de los jugadores en la base de datos de manera transaccional e idempotente.
        Soporta multitenant mediante club_id.
        Si la sesión es un partido (MD o session_type='Partido'), actualiza automáticamente los techos
        del Partido de Máxima Exigencia para todos los futbolistas involucrados.
        """
        warnings = []
        players_processed = 0

        # Idempotencia: comprobar si la sesión ya existe para este club, fecha y nombre
        existing_session = (
            db_session.query(TrainingSession)
            .filter_by(club_id=club_id, date=session_date, name=session_name)
            .first()
        )

        if existing_session:
            new_session = existing_session
            new_session.microcycle_day = microcycle_day
            new_session.session_type = session_type
            new_session.duration_minutes = duration_minutes
            if notes:
                new_session.notes = notes
            # Limpiar métricas anteriores de esta sesión para evitar duplicación
            db_session.query(PlayerMetric).filter_by(session_id=new_session.id).delete()
            db_session.flush()
            warnings.append(f"Sesión existente '{session_name}' ({session_date}) actualizada; métricas previas reescritas.")
        else:
            new_session = TrainingSession(
                club_id=club_id,
                date=session_date,
                name=session_name,
                microcycle_day=microcycle_day,
                session_type=session_type,
                duration_minutes=duration_minutes,
                notes=notes
            )
            db_session.add(new_session)
            db_session.flush()

        for _, row in df_parsed.iterrows():
            player_name = str(row.get("player_name", "")).strip()
            if not player_name or player_name.lower() == "nan":
                continue

            dorsal = row.get("dorsal")
            try:
                dorsal = int(float(dorsal)) if pd.notna(dorsal) else None
            except (ValueError, TypeError):
                dorsal = None

            position = str(row.get("position", "Mediocentro")).strip()
            if not position or position.lower() == "nan":
                position = "Mediocentro"

            # Buscar jugador dentro del mismo club:
            player = None
            if dorsal is not None:
                player = db_session.query(Player).filter(Player.club_id == club_id, Player.dorsal == dorsal).first()

            if not player and player_name:
                normalized_target = cls._normalize_name(player_name)
                all_players = db_session.query(Player).filter(Player.club_id == club_id).all()
                for p in all_players:
                    norm_db = cls._normalize_name(p.name)
                    if normalized_target == norm_db or normalized_target in norm_db or norm_db in normalized_target:
                        player = p
                        break

            # Si no existe en el club, registrarlo con dorsal libre
            if not player:
                if dorsal is not None and not db_session.query(Player).filter(Player.club_id == club_id, Player.dorsal == dorsal).first():
                    assigned_dorsal = dorsal
                else:
                    used_dorsals = {p.dorsal for p in db_session.query(Player.dorsal).filter(Player.club_id == club_id).all()}
                    candidate = 1
                    while candidate in used_dorsals:
                        candidate += 1
                    assigned_dorsal = candidate

                player = Player(
                    club_id=club_id,
                    name=player_name,
                    dorsal=assigned_dorsal,
                    position=position,
                    active=True
                )
                db_session.add(player)
                db_session.flush()
                warnings.append(f"Nuevo jugador registrado: {player_name} (#{assigned_dorsal} - {position}).")

            # Parsear métricas numéricas
            total_dist = float(row.get("total_distance", 0.0) or 0.0)
            hsr_dist = float(row.get("hsr_distance", 0.0) or 0.0)
            sprint_dist = float(row.get("sprint_distance", 0.0) or 0.0)
            hmld_val = float(row.get("hmld", 0.0) or (total_dist * 0.18))
            acc_val = int(row.get("accelerations_eff", 0) or 0)
            dec_val = int(row.get("decelerations_eff", 0) or 0)
            vmax_val = float(row.get("max_speed", 0.0) or 0.0)
            pload_val = float(row.get("player_load", 0.0) or (total_dist * 0.08))
            mins_val = float(row.get("minutes_played", duration_minutes) or duration_minutes)
            rpe_val = float(row.get("rpe", 0.0)) if pd.notna(row.get("rpe")) else None

            # Evitar duplicados dentro del mismo archivo para el mismo jugador
            existing_metric = (
                db_session.query(PlayerMetric)
                .filter(PlayerMetric.session_id == new_session.id, PlayerMetric.player_id == player.id)
                .first()
            )
            if existing_metric:
                continue

            metric = PlayerMetric(
                club_id=club_id,
                player_id=player.id,
                session_id=new_session.id,
                minutes_played=mins_val,
                total_distance=round(total_dist, 1),
                hsr_distance=round(hsr_dist, 1),
                sprint_distance=round(sprint_dist, 1),
                hmld=round(hmld_val, 1),
                accelerations_eff=acc_val,
                decelerations_eff=dec_val,
                max_speed=round(vmax_val, 2),
                player_load=round(pload_val, 1),
                rpe=round(rpe_val, 1) if rpe_val is not None else None
            )
            db_session.add(metric)
            players_processed += 1

        db_session.commit()

        # Si la sesión es un partido, disparar la actualización dinámica de techos 100%
        if session_type == "Partido" or microcycle_day == "MD":
            try:
                from src.services.analytics import sync_and_update_player_match_peaks
                sync_and_update_player_match_peaks(db_session, club_id=club_id)
            except Exception as e_peaks:
                print(f"[IMPORTER AVISO] Error al actualizar techos de partido: {e_peaks}")

        return {
            "success": True,
            "session_id": new_session.id,
            "session_name": new_session.name,
            "players_processed": players_processed,
            "warnings": warnings
        }

    @classmethod
    def sync_local_csv_samples(cls, db_session: Session, force: bool = False) -> Dict[str, Any]:
        """
        Escanea la carpeta de muestras data/samples y sincroniza automáticamente
        cualquier sesión CSV que no esté todavía registrada en la base de datos (o todas si force=True).
        Actualiza además los techos de partidos de máxima exigencia.
        """
        import re
        from pathlib import Path
        from src.config import SAMPLES_DIR

        if not SAMPLES_DIR.exists():
            return {"synced_count": 0, "sessions": []}

        csv_files = sorted(list(SAMPLES_DIR.glob("*.csv")))
        synced = []

        for csv_path in csv_files:
            fname = csv_path.name
            # Extraer fecha del nombre o contenido
            date_match = re.search(r"(\d{4})(\d{2})(\d{2})", fname)
            sess_date = None
            if date_match:
                y, m, d = map(int, date_match.groups())
                try:
                    sess_date = date(y, m, d)
                except ValueError:
                    pass

            if not sess_date:
                # Intentar patrón DD-MM-YYYY
                alt_match = re.search(r"(\d{1,2})-(\d{1,2})-(\d{4})", fname)
                if alt_match:
                    d, m, y = map(int, alt_match.groups())
                    try:
                        sess_date = date(y, m, d)
                    except ValueError:
                        pass

            if not sess_date:
                sess_date = date.today()

            # Extraer nombre limpio
            clean_name = fname.replace("ubiko_", "").replace("_summary.csv", "").replace(".csv", "")
            if len(clean_name) > 9 and clean_name[:8].isdigit() and clean_name[8] == "_":
                clean_name = clean_name[9:]

            # Comprobar si ya existe en la base de datos
            existing = db_session.query(TrainingSession).filter(
                TrainingSession.date == sess_date,
                TrainingSession.name == clean_name
            ).first()

            if existing and not force:
                continue

            # Determinar microciclo
            upper_name = clean_name.upper()
            micro_day = "MD-3"
            sess_type = "Entrenamiento"
            if "MD-4" in upper_name:
                micro_day = "MD-4"
            elif "MD-3" in upper_name:
                micro_day = "MD-3"
            elif "MD-2" in upper_name:
                micro_day = "MD-2"
            elif "MD-1" in upper_name:
                micro_day = "MD-1"
            elif "MD+1" in upper_name:
                micro_day = "MD+1"
            elif "PARTIDO" in upper_name or "MD" in upper_name:
                micro_day = "MD"
                sess_type = "Partido"

            try:
                df_parsed = cls.parse_file(csv_path, fname)
                if not df_parsed.empty:
                    res = cls.import_session_to_db(
                        db_session=db_session,
                        df_parsed=df_parsed,
                        session_date=sess_date,
                        session_name=clean_name,
                        microcycle_day=micro_day,
                        session_type=sess_type,
                        duration_minutes=int(df_parsed.get("minutes_played", pd.Series([75])).max() or 75),
                        notes="Auto-sincronizado desde archivo local de telemetría"
                    )
                    synced.append(clean_name)
            except Exception as e_parse:
                print(f"[AUTO-SYNC LOCAL ERROR] Error importando {fname}: {e_parse}")

        if synced:
            try:
                from src.services.analytics import sync_and_update_player_match_peaks
                sync_and_update_player_match_peaks(db_session)
            except Exception as e_peaks:
                print(f"[AUTO-SYNC LOCAL] Error actualizando picos de partido: {e_peaks}")

        return {"synced_count": len(synced), "sessions": synced}

