"""
Módulo analítico de ciencias del deporte aplicadas al fútbol.
Implementa:
- ACWR mediante EWMA (Exponentially Weighted Moving Average) según Williams et al. (2017) y Gabbett (2016).
- Partido de Máxima Exigencia (Carga 100% Dinámica Individual): Actualización automática de techos individuales.
- Prescripción y % de Cumplimiento individual respecto al 100% del partido según el día del microciclo (MD-4 a MD-1).
- Z-scores normalizados por demarcación táctica y tipo de microciclo.
- Sistema de semáforos ejecutivos: Estado de fatiga (ACWR) y Semáforo de Cumplimiento del Día.
"""

from collections import defaultdict
from datetime import date, datetime, timedelta
from types import SimpleNamespace
from typing import Dict, List, Optional, Tuple, Any
import numpy as np
import pandas as pd
from sqlalchemy import func
from sqlalchemy.orm import Session

from src.config import (
    DEFAULT_CLUB_ID,
    EWMA_ACUTE_DAYS,
    EWMA_CHRONIC_DAYS,
    LAMBDA_ACUTE,
    LAMBDA_CHRONIC,
    ACWR_UNDERLOAD,
    ACWR_SWEET_SPOT_MAX,
    ACWR_DANGER_ZONE,
    Z_SCORE_NORMAL,
    Z_SCORE_WARNING,
    MICROCYCLE_MATCH_TARGETS,
)
from src.database.models import Player, TrainingSession, PlayerMetric, PlayerMatchPeak, TargetLoad


def get_acwr_status(acwr: float) -> Tuple[str, str, str]:
    """
    Retorna (estado, color_hex, etiqueta_semaforo) según el valor de ACWR (Gabbett, 2016).
    """
    if pd.isna(acwr) or acwr <= 0:
        return "Sin datos", "#9E9E9E", "Gris"
    elif acwr < ACWR_UNDERLOAD:
        return "Subentrenamiento (<0.80)", "#3B82F6", "Azul"
    elif acwr <= ACWR_SWEET_SPOT_MAX:
        return "Óptimo Sweet Spot (0.80-1.30)", "#10B981", "Verde"
    elif acwr <= ACWR_DANGER_ZONE:
        return "Alerta Fatiga (1.30-1.50)", "#F59E0B", "Amarillo"
    else:
        return "Riesgo Alto Sobrecarga (>1.50)", "#EF4444", "Rojo"


LOAD_LEVEL_PRESETS: Dict[int, Dict[str, Any]] = {
    50: {
        "level": 50,
        "name": "Nivel 50%",
        "title": "Carga Baja / Regenerativa / Compensatorio",
        "badge": "🟢 Carga Baja (50%)",
        "factor": 0.50,
        "description": "50% de intensidad objetivo sobre el partido de máxima exigencia. Adecuado para MD+1, sesiones regenerativas, post-partido o compensatorias de suplentes.",
        "defaults_by_day": {
            "MD-4": {"pct_td": 40.0, "pct_hsr": 25.0, "pct_sprint": 20.0, "pct_eff": 50.0},
            "MD-3": {"pct_td": 50.0, "pct_hsr": 35.0, "pct_sprint": 30.0, "pct_eff": 40.0},
            "MD-2": {"pct_td": 35.0, "pct_hsr": 50.0, "pct_sprint": 45.0, "pct_eff": 35.0},
            "MD-1": {"pct_td": 35.0, "pct_hsr": 20.0, "pct_sprint": 15.0, "pct_eff": 25.0},
            "MD+1": {"pct_td": 45.0, "pct_hsr": 20.0, "pct_sprint": 15.0, "pct_eff": 30.0},
            "MD+2": {"pct_td": 45.0, "pct_hsr": 20.0, "pct_sprint": 15.0, "pct_eff": 30.0},
            "MD":   {"pct_td": 50.0, "pct_hsr": 50.0, "pct_sprint": 50.0, "pct_eff": 50.0},
        }
    },
    70: {
        "level": 70,
        "name": "Nivel 70%",
        "title": "Carga Media",
        "badge": "🟡 Carga Media (70%)",
        "factor": 0.70,
        "description": "70% de intensidad objetivo sobre el partido de máxima exigencia. Estimulación equilibrada sin acumular fatiga residual previa al fin de semana.",
        "defaults_by_day": {
            "MD-4": {"pct_td": 50.0, "pct_hsr": 35.0, "pct_sprint": 30.0, "pct_eff": 70.0},
            "MD-3": {"pct_td": 70.0, "pct_hsr": 55.0, "pct_sprint": 45.0, "pct_eff": 55.0},
            "MD-2": {"pct_td": 45.0, "pct_hsr": 70.0, "pct_sprint": 65.0, "pct_eff": 45.0},
            "MD-1": {"pct_td": 45.0, "pct_hsr": 25.0, "pct_sprint": 20.0, "pct_eff": 30.0},
            "MD+1": {"pct_td": 50.0, "pct_hsr": 25.0, "pct_sprint": 20.0, "pct_eff": 35.0},
            "MD+2": {"pct_td": 50.0, "pct_hsr": 25.0, "pct_sprint": 20.0, "pct_eff": 35.0},
            "MD":   {"pct_td": 70.0, "pct_hsr": 70.0, "pct_sprint": 70.0, "pct_eff": 70.0},
        }
    },
    80: {
        "level": 80,
        "name": "Nivel 80%",
        "title": "Carga Alta / Máxima Estimulación Semanal",
        "badge": "🔴 Carga Alta (80%)",
        "factor": 0.80,
        "description": "80% de intensidad objetivo sobre el partido de máxima exigencia. Máxima sobrecarga adaptativa del microciclo (MD-4 en tensión, MD-3 en volumen o MD-2 en velocidad).",
        "defaults_by_day": {
            "MD-4": {"pct_td": 60.0, "pct_hsr": 45.0, "pct_sprint": 40.0, "pct_eff": 80.0},
            "MD-3": {"pct_td": 80.0, "pct_hsr": 70.0, "pct_sprint": 55.0, "pct_eff": 65.0},
            "MD-2": {"pct_td": 55.0, "pct_hsr": 80.0, "pct_sprint": 75.0, "pct_eff": 55.0},
            "MD-1": {"pct_td": 50.0, "pct_hsr": 30.0, "pct_sprint": 25.0, "pct_eff": 35.0},
            "MD+1": {"pct_td": 55.0, "pct_hsr": 30.0, "pct_sprint": 25.0, "pct_eff": 40.0},
            "MD+2": {"pct_td": 55.0, "pct_hsr": 30.0, "pct_sprint": 25.0, "pct_eff": 40.0},
            "MD":   {"pct_td": 80.0, "pct_hsr": 80.0, "pct_sprint": 80.0, "pct_eff": 80.0},
        }
    }
}


def get_load_level_preset(level: int, microcycle_day: str = "MD-3") -> Dict[str, Any]:
    """
    Retorna los porcentajes de prescripción ({pct_td, pct_hsr, pct_sprint, pct_eff})
    para el nivel seleccionado (50, 70, 80) y el día de microciclo correspondiente.
    """
    lvl_cfg = LOAD_LEVEL_PRESETS.get(level, LOAD_LEVEL_PRESETS[70])
    day_key = microcycle_day.upper().strip() if microcycle_day else "MD-3"
    day_defaults = lvl_cfg["defaults_by_day"].get(day_key, lvl_cfg["defaults_by_day"].get("MD-3", {}))
    return {
        "pct_td": float(day_defaults.get("pct_td", float(level))),
        "pct_hsr": float(day_defaults.get("pct_hsr", float(level))),
        "pct_sprint": float(day_defaults.get("pct_sprint", float(level))),
        "pct_eff": float(day_defaults.get("pct_eff", float(level))),
        "factor": lvl_cfg["factor"],
        "level": level,
        "title": lvl_cfg["title"],
        "badge": lvl_cfg["badge"]
    }


def get_stimulus_compliance_status(pct: float) -> Tuple[str, str, str]:
    """
    Evalúa el cumplimiento de la carga prescrita según los requerimientos del preparador físico:
    - Verde: Cumplido (80% - 115%)
    - Rojo: Déficit de estímulo (<80%)
    - Naranja/Rojo: Sobrecarga / Sobre-estímulo (>115%)
    """
    if pd.isna(pct) or pct <= 0:
        return "Sin datos", "#9E9E9E", "Gris"
    elif pct < 80.0:
        return "Déficit de Estímulo (<80%)", "#EF4444", "Rojo"
    elif pct <= 115.0:
        return "Objetivo Cumplido (80-115%)", "#10B981", "Verde"
    elif pct <= 130.0:
        return "Sobre-estímulo / Fatiga (115-130%)", "#F59E0B", "Naranja"
    else:
        return "Sobrecarga Crítica (>130%)", "#DC2626", "Rojo Oscuro"


def evaluate_multivariable_deficit(
    microcycle_day: str,
    comp_pct_td: float,
    comp_pct_hsr: float,
    comp_pct_eff: float
) -> Tuple[str, str, str, str]:
    """
    Diagnóstico de Déficit de Estímulo Multivariable según la demanda específica del día de microciclo:
    - MD-4 (Tensión neuromuscular / Espacios reducidos): Métrica crítica = AC.E.
    - MD-3 (Duración / Volumen / Resistencia): Métrica crítica = DT.
    - MD-2 (Velocidad / Reactividad neuromuscular): Métrica crítica = HSR (>21 km/h).
    - MD-1 (Activación y Balón Parado): Volumen controlado (DT 40-50%).
    - MD+1 (Recuperación / Compensación): Carga moderada.
    - MD (Competición Oficial): Demanda máxima 100%.

    Retorna: (diagnostico_completo, estado_simplificado, color_hex, color_label)
    """
    day = microcycle_day.upper().strip() if microcycle_day else "MD-3"

    if day == "MD-4":
        # Métrica crítica del día de tensión: AC.E (aceleraciones y desaceleraciones > 3 m/s²) y HMLD
        if comp_pct_eff < 80.0:
            return (
                f"🔴 Déficit neuromuscular (AC.E: {comp_pct_eff:.0f}%)",
                "Déficit AC.E",
                "#EF4444",
                "Rojo"
            )
        elif comp_pct_eff > 115.0:
            return (
                f"🟠 Sobre-estímulo neuromuscular (AC.E: {comp_pct_eff:.0f}%)",
                "Sobre-estímulo AC.E",
                "#F97316",
                "Naranja"
            )
        else:
            # En MD-4, la DT o HSR reducida es fisiológicamente normal en espacio reducido; NO es déficit
            dt_note = f" (DT reducida {comp_pct_td:.0f}% normal)" if comp_pct_td < 75.0 else ""
            return (
                f"🟢 Estímulo Neuromuscular Óptimo (AC.E: {comp_pct_eff:.0f}%{dt_note})",
                "Cumplido",
                "#10B981",
                "Verde"
            )

    elif day == "MD-3":
        # Métrica crítica del día de resistencia: DT (volumen total) y capacidad aeróbica
        if comp_pct_td < 80.0:
            return (
                f"🔴 Déficit de volumen (DT: {comp_pct_td:.0f}%)",
                "Déficit DT",
                "#EF4444",
                "Rojo"
            )
        elif comp_pct_td > 115.0:
            return (
                f"🟠 Sobre-estímulo de volumen (DT: {comp_pct_td:.0f}%)",
                "Sobre-estímulo DT",
                "#F97316",
                "Naranja"
            )
        else:
            return (
                f"🟢 Estímulo de Volumen Óptimo (DT: {comp_pct_td:.0f}%)",
                "Cumplido",
                "#10B981",
                "Verde"
            )

    elif day == "MD-2":
        # Métrica crítica del día de velocidad: HSR (>21 km/h) y picos de sprint
        if comp_pct_hsr < 80.0:
            return (
                f"🔴 Déficit de velocidad (HSR: {comp_pct_hsr:.0f}%)",
                "Déficit HSR",
                "#EF4444",
                "Rojo"
            )
        elif comp_pct_hsr > 115.0:
            return (
                f"🟠 Sobre-estímulo de velocidad (HSR: {comp_pct_hsr:.0f}%)",
                "Sobre-estímulo HSR",
                "#F97316",
                "Naranja"
            )
        else:
            return (
                f"🟢 Estímulo de Velocidad Cumplido (HSR: {comp_pct_hsr:.0f}%)",
                "Cumplido",
                "#10B981",
                "Verde"
            )

    elif day == "MD-1":
        # Activación: volumen muy reducido
        if comp_pct_td > 120.0:
            return (
                f"🟠 Exceso de volumen para activación (DT: {comp_pct_td:.0f}%)",
                "Sobre-estímulo Activación",
                "#F97316",
                "Naranja"
            )
        elif comp_pct_td < 65.0:
            return (
                f"🟡 Activación muy corta (DT: {comp_pct_td:.0f}%)",
                "Déficit leve",
                "#FBBF24",
                "Amarillo"
            )
        else:
            return (
                f"🟢 Activación Correcta ({comp_pct_td:.0f}%)",
                "Cumplido",
                "#10B981",
                "Verde"
            )

    elif day in ["MD+1", "MD+2"]:
        if comp_pct_td > 125.0:
            return (
                f"🟠 Sobrecarga en recuperación (DT: {comp_pct_td:.0f}%)",
                "Sobre-estímulo Recuperación",
                "#F97316",
                "Naranja"
            )
        else:
            return (
                f"🟢 Recuperación Adecuada ({comp_pct_td:.0f}%)",
                "Cumplido",
                "#10B981",
                "Verde"
            )

    else:  # MD (Competición u otro)
        return (
            f"🏟️ Competición Oficial ({comp_pct_td:.0f}% DT | {comp_pct_hsr:.0f}% HSR)",
            "Competición",
            "#3B82F6",
            "Azul"
        )


def get_rpe_category(rpe_val: Optional[float]) -> Tuple[str, str]:
    """
    Retorna (descripción, color_hex) para la escala Borg/Foster RPE (1 a 10).
    """
    if rpe_val is None or pd.isna(rpe_val) or rpe_val <= 0:
        return "Sin registrar", "#9E9E9E"
    elif rpe_val <= 2.5:
        return "Muy Suave / Recuperación", "#3B82F6"
    elif rpe_val <= 4.5:
        return "Moderado / Aeróbico", "#10B981"
    elif rpe_val <= 6.5:
        return "Duro / Umbral", "#F59E0B"
    elif rpe_val <= 8.5:
        return "Muy Duro / Alta Intensidad", "#EF4444"
    else:
        return "Máximo / Extenuante", "#991B1B"


def is_official_league_match(session: TrainingSession) -> bool:
    """
    Filtra estrictamente para que SOLO se consideren Partidos Oficiales de Liga regular:
    - Excluye entrenamientos (incluso si tienen día 'MD' o 'Pre-partido').
    - Excluye sesiones y amistosos de pretemporada (agosto o con etiqueta PRETEMPORADA).
    """
    name_upper = (session.name or "").upper().strip()

    # 1. Excluir entrenamientos y pretemporada
    if any(tag in name_upper for tag in ["PRETEMPORADA", "PRE-TEMPORADA", "PRE_PARTIDO", "PRE-PARTIDO", "ENTRENAMIENTO", "COMPENSATORIO"]):
        return False

    # 2. Excluir amistosos de pretemporada disputados en agosto (Granada B, Linares, Pozoblanco, etc.)
    if session.date and session.date < date(2026, 9, 1):
        return False

    # 3. Debe ser tipo 'Partido' o microciclo 'MD'
    if session.session_type != "Partido" and session.microcycle_day != "MD":
        return False

    return True


# ==============================================================================
# 1. GESTIÓN DEL "PARTIDO DE MÁXIMA EXIGENCIA" (CARGA 100% DINÁMICA INDIVIDUAL)
# ==============================================================================

def sync_and_update_player_match_peaks(db: Session, club_id: int = DEFAULT_CLUB_ID) -> Dict[str, Any]:
    """
    Examina todos los partidos oficiales de Liga regular (session_type='Partido' o microcycle_day='MD') del club.
    Para cada jugador:
    1. Localiza sus valores máximos alcanzados en partido de liga (DT, HSR, Sprint, HMLD, AC.E, Vmax).
    2. Si en jornadas posteriores un nuevo partido supera esos máximos, actualiza automáticamente
       ese nuevo techo del 100% en la tabla `player_match_peaks`.
    OPTIMIZADO: Consultas batch de partidos, picos existentes y entrenamientos para evitar N*M roundtrips.
    """
    players = db.query(Player).filter(Player.club_id == club_id, Player.active == True).all()
    if not players:
        return {"created": 0, "updated": 0}

    # Partidos oficiales de Liga del club ordenados cronológicamente
    candidate_sessions = (
        db.query(TrainingSession)
        .filter(
            TrainingSession.club_id == club_id,
            (TrainingSession.session_type == "Partido") | (TrainingSession.microcycle_day == "MD")
        )
        .order_by(TrainingSession.date.asc())
        .all()
    )
    matches = [m for m in candidate_sessions if is_official_league_match(m)]
    match_ids = [m.id for m in matches]
    match_dict = {m.id: m for m in matches}

    # 1. Cargar picos existentes en 1 consulta
    existing_peaks = {
        pk.player_id: pk
        for pk in db.query(PlayerMatchPeak).filter(PlayerMatchPeak.club_id == club_id).all()
    }

    # 2. Cargar métricas de partidos en 1 consulta
    match_metrics_by_player = defaultdict(list)
    if match_ids:
        all_match_metrics = (
            db.query(PlayerMetric)
            .filter(PlayerMetric.session_id.in_(match_ids))
            .all()
        )
        for mm in all_match_metrics:
            match_metrics_by_player[mm.player_id].append(mm)

    # 3. Cargar métricas de entrenamientos en 1 consulta (fallback si no jugó partidos)
    all_train_metrics = (
        db.query(PlayerMetric, TrainingSession)
        .join(TrainingSession, PlayerMetric.session_id == TrainingSession.id)
        .filter(
            TrainingSession.club_id == club_id,
            TrainingSession.session_type != "Partido",
            TrainingSession.microcycle_day != "MD"
        )
        .all()
    )
    train_metrics_by_player = defaultdict(list)
    for tm, ts in all_train_metrics:
        train_metrics_by_player[tm.player_id].append((tm, ts))

    updated_count = 0
    created_count = 0

    def _calc_demand_score(m):
        return (
            (m.total_distance or 0.0) * 0.30 +
            (m.hsr_distance or 0.0) * 0.25 +
            (m.sprint_distance or 0.0) * 0.20 +
            ((m.accelerations_eff or 0) + (m.decelerations_eff or 0)) * 20.0
        )

    for p in players:
        current_peak = existing_peaks.get(p.id)
        p_match_metrics = match_metrics_by_player.get(p.id, [])

        # Partidos donde disputó minutos significativos (>= 3000m y >= 30 min)
        full_matches = [
            m for m in p_match_metrics
            if (m.total_distance or 0) >= 3000 and (m.minutes_played or 0) >= 30
        ]

        if full_matches:
            # Caso 1: Ha jugado partido oficial con minutos significativos -> Seleccionar el partido donde más haya rendido
            best_metric = max(full_matches, key=_calc_demand_score)
            best_session = match_dict.get(best_metric.session_id)
            sess_name = best_session.name if best_session else "Partido Oficial"
            sess_date = best_session.date if best_session else date.today()
            sess_type = "Partido"
            mins_val = float(best_metric.minutes_played or 90.0)

            max_td = float(best_metric.total_distance or 0.0)
            max_hsr = float(best_metric.hsr_distance or 0.0)
            max_sprint = float(best_metric.sprint_distance or 0.0)
            max_hmld = float(best_metric.hmld or 0.0)
            max_acc = int(best_metric.accelerations_eff or 0)
            max_dec = int(best_metric.decelerations_eff or 0)
            max_vmax = max(float(best_metric.max_speed or 0.0), p.max_speed_kmh or 30.0)
        else:
            # Caso 2: No ha jugado >=30 min en liga -> Usar su entrenamiento con mayor exigencia física (pico AC.E / carga metabólica)
            train_metrics = train_metrics_by_player.get(p.id, [])
            valid_train = [
                pair for pair in train_metrics
                if (pair[0].total_distance or 0) >= 2000 and (pair[0].minutes_played or 0) >= 25
            ]
            if valid_train:
                best_tm, best_ts = max(valid_train, key=lambda pair: _calc_demand_score(pair[0]))
                sess_name = f"Entreno {best_ts.microcycle_day} ({best_ts.date.strftime('%d/%m/%Y')})"
                sess_date = best_ts.date
                sess_type = "Entrenamiento"
                mins_val = float(best_tm.minutes_played or 70.0)

                max_td = float(best_tm.total_distance or 0.0)
                max_hsr = float(best_tm.hsr_distance or 0.0)
                max_sprint = float(best_tm.sprint_distance or 0.0)
                max_hmld = float(best_tm.hmld or 0.0)
                max_acc = int(best_tm.accelerations_eff or 0)
                max_dec = int(best_tm.decelerations_eff or 0)
                max_vmax = max(float(best_tm.max_speed or 0.0), p.max_speed_kmh or 30.0)
            else:
                # Caso 3: Jugador sin telemetría registrada -> Perfil posicional estándar
                pos = (p.position or "Mediocentro").upper()
                sess_name = "Perfil Posicional Estándar"
                sess_date = date.today()
                sess_type = "Teórico"
                mins_val = 90.0
                max_td = 10200.0 if "CENTRAL" not in pos else 9500.0
                max_hsr = 400.0
                max_sprint = 120.0
                max_hmld = 1700.0
                max_acc = 50
                max_dec = 50
                max_vmax = p.max_speed_kmh or 31.0

        if not current_peak:
            new_peak = PlayerMatchPeak(
                club_id=club_id,
                player_id=p.id,
                peak_td=max_td,
                peak_hsr=max_hsr,
                peak_sprint=max_sprint,
                peak_hmld=max_hmld,
                peak_acc_eff=max_acc,
                peak_dec_eff=max_dec,
                peak_max_speed=max_vmax,
                peak_session_name=sess_name,
                peak_session_date=sess_date,
                peak_session_type=sess_type,
                peak_minutes=round(mins_val, 1),
                last_updated=datetime.utcnow()
            )
            db.add(new_peak)
            created_count += 1
        else:
            current_peak.peak_td = max_td
            current_peak.peak_hsr = max_hsr
            current_peak.peak_sprint = max_sprint
            current_peak.peak_hmld = max_hmld
            current_peak.peak_acc_eff = max_acc
            current_peak.peak_dec_eff = max_dec
            current_peak.peak_max_speed = max_vmax
            current_peak.peak_session_name = sess_name
            current_peak.peak_session_date = sess_date
            current_peak.peak_session_type = sess_type
            current_peak.peak_minutes = round(mins_val, 1)
            current_peak.last_updated = datetime.utcnow()
            updated_count += 1

    db.commit()
    return {"created": created_count, "updated": updated_count}


def get_player_match_peak(db: Session, player_id: int, club_id: int = DEFAULT_CLUB_ID) -> Optional[PlayerMatchPeak]:
    """Retorna el registro del Partido de Máxima Exigencia para un jugador."""
    peak = (
        db.query(PlayerMatchPeak)
        .filter(PlayerMatchPeak.club_id == club_id, PlayerMatchPeak.player_id == player_id)
        .first()
    )
    if not peak:
        sync_and_update_player_match_peaks(db, club_id=club_id)
        peak = (
            db.query(PlayerMatchPeak)
            .filter(PlayerMatchPeak.club_id == club_id, PlayerMatchPeak.player_id == player_id)
            .first()
        )
    return peak


# ==============================================================================
# 2. CÁLCULO DE CUMPLIMIENTO INDIVIDUAL RELATIVO AL PARTIDO (MICROCICLO)
# ==============================================================================

def calculate_individual_microcycle_compliance(
    db: Session,
    session_id: int,
    club_id: int = DEFAULT_CLUB_ID
) -> pd.DataFrame:
    """
    Calcula el Semáforo de Cumplimiento Individual del Día para cada futbolista en la sesión:
    1. Identifica el día del microciclo (MD-4, MD-3, MD-2, MD-1, MD).
    2. Determina la MÉTRICA CLAVE del día:
       - MD-4: Aceleraciones + Desaceleraciones Eficaces (AC.E) -> Objetivo: ~90-95% del partido.
       - MD-3: Distancia Total (DT) -> Objetivo: ~80-85% del partido.
       - MD-2: High Speed Running (HSR >21 km/h) -> Objetivo: ~70% del partido.
       - MD-1: Distancia Total (Activación) -> Objetivo: ~40-50% del partido.
       - MD: Partido completo (100% de referencia).
    3. Compara el Valor Real con el Objetivo Prescrito individual (calculado sobre el 100% de su partido).
    4. Asigna el estado del semáforo:
       - Verde: Objetivo Cumplido (80% - 115%)
       - Rojo: Déficit de Estímulo (<80%)
       - Naranja: Sobre-estímulo (>115%)
    """
    sess = db.query(TrainingSession).filter(TrainingSession.id == session_id, TrainingSession.club_id == club_id).first()
    if not sess:
        return pd.DataFrame()

    # Cargar picos del 100% en 1 sola consulta batch
    peaks_list = db.query(PlayerMatchPeak).filter(PlayerMatchPeak.club_id == club_id).all()
    if not peaks_list:
        sync_and_update_player_match_peaks(db, club_id=club_id)
        peaks_list = db.query(PlayerMatchPeak).filter(PlayerMatchPeak.club_id == club_id).all()
    peaks_by_player = {p.player_id: p for p in peaks_list}

    micro_cfg = MICROCYCLE_MATCH_TARGETS.get(sess.microcycle_day, MICROCYCLE_MATCH_TARGETS["MD-3"])
    key_metric = micro_cfg["primary_metric"]
    key_label = micro_cfg["primary_label"]
    target_pct = micro_cfg["target_pct"]

    metrics = (
        db.query(
            Player.id.label("player_id"),
            Player.dorsal,
            Player.name.label("player_name"),
            Player.position,
            PlayerMetric.total_distance,
            PlayerMetric.hsr_distance,
            PlayerMetric.sprint_distance,
            PlayerMetric.hmld,
            PlayerMetric.accelerations_eff,
            PlayerMetric.decelerations_eff,
            (PlayerMetric.accelerations_eff + PlayerMetric.decelerations_eff).label("acc_dec_eff"),
            PlayerMetric.max_speed,
            PlayerMetric.minutes_played,
            PlayerMetric.rpe
        )
        .join(PlayerMetric, Player.id == PlayerMetric.player_id)
        .filter(PlayerMetric.session_id == session_id, Player.club_id == club_id)
        .order_by(Player.dorsal.asc())
        .all()
    )

    rows = []
    for m in metrics:
        peak = peaks_by_player.get(m.player_id)
        if not peak:
            continue

        # Valores reales registrados
        val_real_td = float(m.total_distance or 0.0)
        val_real_hsr = float(m.hsr_distance or 0.0)
        val_real_eff = float(m.acc_dec_eff or 0)

        # Techos del 100% individual
        peak_td = float(peak.peak_td)
        peak_hsr = float(peak.peak_hsr)
        peak_eff = float(peak.peak_eff)

        # Porcentajes prescritos para el microciclo
        pct_td_cfg = micro_cfg.get("pct_td", 0.825) * 100.0
        pct_hsr_cfg = micro_cfg.get("pct_hsr", 0.65) * 100.0
        pct_eff_cfg = micro_cfg.get("pct_eff", 0.65) * 100.0

        # Metas cuantitativas individuales prescritas
        target_td = peak_td * (pct_td_cfg / 100.0)
        target_hsr = peak_hsr * (pct_hsr_cfg / 100.0)
        target_eff = peak_eff * (pct_eff_cfg / 100.0)

        # % Cumplimiento multivariable
        comp_pct_td = (val_real_td / target_td * 100.0) if target_td > 0 else 0.0
        comp_pct_hsr = (val_real_hsr / target_hsr * 100.0) if target_hsr > 0 else 0.0
        comp_pct_eff = (val_real_eff / target_eff * 100.0) if target_eff > 0 else 0.0

        # Métrica diana del día de microciclo
        if key_metric == "acc_dec_eff":
            val_real = val_real_eff
            val_target = target_eff
            val_match_100 = peak_eff
            compliance_pct = comp_pct_eff
            unit = " esfuerzos"
        elif key_metric == "hsr_distance":
            val_real = val_real_hsr
            val_target = target_hsr
            val_match_100 = peak_hsr
            compliance_pct = comp_pct_hsr
            unit = " m"
        else:  # total_distance
            val_real = val_real_td
            val_target = target_td
            val_match_100 = peak_td
            compliance_pct = comp_pct_td
            unit = " m"

        match_share_pct = (val_real / val_match_100 * 100.0) if val_match_100 > 0 else 0.0

        # Diagnóstico multivariable según el día de microciclo
        diagnosis, status, color_hex, color_label = evaluate_multivariable_deficit(
            sess.microcycle_day, comp_pct_td, comp_pct_hsr, comp_pct_eff
        )

        rows.append({
            "player_id": m.player_id,
            "dorsal": m.dorsal,
            "player_name": m.player_name,
            "position": m.position,
            "key_metric": key_metric,
            "key_label": key_label,
            "val_real": round(val_real, 1),
            "val_real_formatted": f"{val_real:.0f}{unit}" if unit == " m" else f"{int(val_real)}{unit}",
            "val_target": round(val_target, 1),
            "val_target_formatted": f"{val_target:.0f}{unit}" if unit == " m" else f"{int(val_target)}{unit}",
            "val_match_100": round(val_match_100, 1),
            "val_match_100_formatted": f"{val_match_100:.0f}{unit}" if unit == " m" else f"{int(val_match_100)}{unit}",
            # Desglose multivariable
            "comp_pct_td": round(comp_pct_td, 1),
            "comp_pct_hsr": round(comp_pct_hsr, 1),
            "comp_pct_eff": round(comp_pct_eff, 1),
            "val_real_td": round(val_real_td, 0),
            "target_td": round(target_td, 0),
            "val_real_hsr": round(val_real_hsr, 0),
            "target_hsr": round(target_hsr, 0),
            "val_real_eff": int(val_real_eff),
            "target_eff": int(target_eff),
            # Cumplimiento y diagnósticos
            "compliance_pct": round(compliance_pct, 1),
            "match_share_pct": round(match_share_pct, 1),
            "diagnosis": diagnosis,
            "status": status,
            "color_hex": color_hex,
            "color_label": color_label,
            "peak_match_name": peak.peak_session_name or "Oficial",
            "minutes": m.minutes_played,
            "rpe": m.rpe
        })

    return pd.DataFrame(rows)


def calculate_pre_session_prescription(
    db: Session,
    microcycle_day: str = "MD-4",
    pct_td: float = 58.0,
    pct_hsr: float = 40.0,
    pct_eff: float = 92.5,
    club_id: int = DEFAULT_CLUB_ID
) -> pd.DataFrame:
    """
    Herramienta de Planificación Pre-Sesión:
    Calcula las metas cuantitativas mínimas requeridas para toda la plantilla ANTES del entrenamiento
    aplicando los porcentajes configurados por el preparador físico al 100% individual del partido récord.
    """
    peaks_list = db.query(PlayerMatchPeak).filter(PlayerMatchPeak.club_id == club_id).all()
    if not peaks_list:
        sync_and_update_player_match_peaks(db, club_id=club_id)
        peaks_list = db.query(PlayerMatchPeak).filter(PlayerMatchPeak.club_id == club_id).all()
    peaks_by_player = {p.player_id: p for p in peaks_list}

    players = (
        db.query(Player)
        .filter(Player.club_id == club_id, Player.active == True)
        .order_by(Player.dorsal.asc())
        .all()
    )

    rows = []
    for p in players:
        peak = peaks_by_player.get(p.id)
        if not peak:
            continue

        min_td = round(peak.peak_td * (pct_td / 100.0), 0)
        min_hsr = round(peak.peak_hsr * (pct_hsr / 100.0), 0)
        min_eff = round(peak.peak_eff * (pct_eff / 100.0), 0)

        rows.append({
            "player_id": p.id,
            "dorsal": p.dorsal,
            "player_name": p.name,
            "position": p.position,
            "min_td": min_td,
            "min_hsr": min_hsr,
            "min_eff": int(min_eff),
            "peak_td": peak.peak_td,
            "peak_hsr": peak.peak_hsr,
            "peak_eff": peak.peak_eff,
            "peak_session_name": peak.peak_session_name or "Oficial",
            "microcycle_day": microcycle_day,
            "pct_td": pct_td,
            "pct_hsr": pct_hsr,
            "pct_eff": pct_eff
        })

    return pd.DataFrame(rows)


def save_pre_session_prescription(
    db: Session,
    microcycle_day: str,
    pct_td: float,
    pct_hsr: float,
    pct_eff: float,
    club_id: int = DEFAULT_CLUB_ID
) -> bool:
    """
    Guarda y actualiza los objetivos de carga fisiológica (TargetLoad) en la base de datos
    para cada demarcación posicional a partir de la prescripción pre-sesión fijada por el cuerpo técnico.
    """
    df_plan = calculate_pre_session_prescription(db, microcycle_day, pct_td, pct_hsr, pct_eff, club_id=club_id)
    if df_plan.empty:
        return False

    for pos in df_plan["position"].unique():
        sub = df_plan[df_plan["position"] == pos]
        mean_td = float(sub["min_td"].mean())
        mean_hsr = float(sub["min_hsr"].mean())
        mean_eff = int(sub["min_eff"].mean())

        tl = db.query(TargetLoad).filter(
            TargetLoad.club_id == club_id,
            TargetLoad.microcycle_day == microcycle_day,
            TargetLoad.position == pos
        ).first()

        if not tl:
            tl = TargetLoad(
                club_id=club_id,
                microcycle_day=microcycle_day,
                position=pos,
                target_td=mean_td,
                target_hsr=mean_hsr,
                target_hmld=round(mean_td * 0.18, 0),
                target_acc_eff=int(mean_eff // 2),
                target_dec_eff=int(mean_eff - (mean_eff // 2))
            )
            db.add(tl)
        else:
            tl.target_td = mean_td
            tl.target_hsr = mean_hsr
            tl.target_hmld = round(mean_td * 0.18, 0)
            tl.target_acc_eff = int(mean_eff // 2)
            tl.target_dec_eff = int(mean_eff - (mean_eff // 2))

    db.commit()
    return True


# ==============================================================================
# 3. CARGA AGUDA/CRÓNICA EWMA Y ESTADO ACWR
# ==============================================================================

def calculate_ewma_acwr(
    session: Session,
    player_id: int,
    load_metric: str = "total_distance",
    club_id: int = DEFAULT_CLUB_ID
) -> pd.DataFrame:
    """
    Calcula la serie temporal de Carga Aguda, Carga Crónica y ACWR con EWMA para un jugador.
    Crea un calendario continuo rellenando los días sin sesión con carga 0.
    """
    query = (
        session.query(
            TrainingSession.date,
            TrainingSession.id.label("session_id"),
            TrainingSession.microcycle_day,
            TrainingSession.session_type,
            getattr(PlayerMetric, load_metric).label("load_value"),
            PlayerMetric.total_distance,
            PlayerMetric.hsr_distance,
            PlayerMetric.hmld,
            (PlayerMetric.accelerations_eff + PlayerMetric.decelerations_eff).label("acc_dec_eff"),
            PlayerMetric.max_speed,
            PlayerMetric.rpe
        )
        .join(PlayerMetric, TrainingSession.id == PlayerMetric.session_id)
        .filter(PlayerMetric.player_id == player_id, TrainingSession.club_id == club_id)
        .order_by(TrainingSession.date.asc())
    )

    df_sessions = pd.read_sql(query.statement, session.bind)
    if df_sessions.empty:
        return pd.DataFrame()

    df_sessions["date"] = pd.to_datetime(df_sessions["date"])

    numeric_cols = ["load_value", "total_distance", "hsr_distance", "hmld", "acc_dec_eff"]
    agg_dict = {col: "sum" for col in numeric_cols if col in df_sessions.columns}
    if "max_speed" in df_sessions.columns:
        agg_dict["max_speed"] = "max"
    if "rpe" in df_sessions.columns:
        agg_dict["rpe"] = "mean"
    if "microcycle_day" in df_sessions.columns:
        agg_dict["microcycle_day"] = "last"
    if "session_type" in df_sessions.columns:
        agg_dict["session_type"] = "last"
    if "session_id" in df_sessions.columns:
        agg_dict["session_id"] = "last"

    df_daily_agg = df_sessions.groupby("date").agg(agg_dict)

    start_date = df_sessions["date"].min()
    end_date = df_sessions["date"].max()
    full_idx = pd.date_range(start_date, end_date, freq="D", name="date")

    df_daily = df_daily_agg.reindex(full_idx)
    df_daily["load_value"] = df_daily["load_value"].fillna(0.0)

    acute_series = []
    chronic_series = []

    acute_prev = df_daily["load_value"].iloc[0]
    chronic_prev = df_daily["load_value"].iloc[0]

    for val in df_daily["load_value"]:
        acute_curr = (val * LAMBDA_ACUTE) + ((1.0 - LAMBDA_ACUTE) * acute_prev)
        chronic_curr = (val * LAMBDA_CHRONIC) + ((1.0 - LAMBDA_CHRONIC) * chronic_prev)
        acute_series.append(acute_curr)
        chronic_series.append(chronic_curr)
        acute_prev = acute_curr
        chronic_prev = chronic_curr

    df_daily["acute_ewma"] = acute_series
    df_daily["chronic_ewma"] = chronic_series

    df_daily["acwr"] = np.where(
        df_daily["chronic_ewma"] > 1e-3,
        df_daily["acute_ewma"] / df_daily["chronic_ewma"],
        np.nan
    )

    df_result = df_daily.reset_index()
    status_info = df_result["acwr"].apply(get_acwr_status)
    df_result["acwr_status"] = [s[0] for s in status_info]
    df_result["acwr_color"] = [s[1] for s in status_info]

    return df_result


def get_latest_player_acwr(session: Session, target_date: Optional[date] = None, club_id: int = DEFAULT_CLUB_ID) -> pd.DataFrame:
    """
    Calcula el ACWR más reciente de todos los futbolistas del club a una fecha determinada.
    OPTIMIZADO: Carga todas las sesiones en 1 sola consulta batch y computa EWMA por jugador en memoria.
    """
    players = session.query(Player).filter(Player.club_id == club_id, Player.active == True).all()
    if not players:
        return pd.DataFrame()

    query = (
        session.query(
            PlayerMetric.player_id,
            TrainingSession.date,
            TrainingSession.id.label("session_id"),
            TrainingSession.microcycle_day,
            TrainingSession.session_type,
            PlayerMetric.total_distance.label("load_value"),
            PlayerMetric.total_distance,
            PlayerMetric.hsr_distance,
            PlayerMetric.hmld,
            (PlayerMetric.accelerations_eff + PlayerMetric.decelerations_eff).label("acc_dec_eff"),
            PlayerMetric.max_speed,
            PlayerMetric.rpe
        )
        .join(PlayerMetric, TrainingSession.id == PlayerMetric.session_id)
        .filter(TrainingSession.club_id == club_id)
        .order_by(TrainingSession.date.asc())
    )
    df_all = pd.read_sql(query.statement, session.bind)
    if df_all.empty:
        return pd.DataFrame()

    df_all["date"] = pd.to_datetime(df_all["date"])
    records = []
    grouped = df_all.groupby("player_id")

    for p in players:
        if p.id not in grouped.groups:
            continue
        df_p = grouped.get_group(p.id)
        if df_p.empty:
            continue

        numeric_cols = ["load_value", "total_distance", "hsr_distance", "hmld", "acc_dec_eff"]
        agg_dict = {col: "sum" for col in numeric_cols if col in df_p.columns}
        if "max_speed" in df_p.columns:
            agg_dict["max_speed"] = "max"
        if "rpe" in df_p.columns:
            agg_dict["rpe"] = "mean"
        if "microcycle_day" in df_p.columns:
            agg_dict["microcycle_day"] = "last"
        if "session_type" in df_p.columns:
            agg_dict["session_type"] = "last"
        if "session_id" in df_p.columns:
            agg_dict["session_id"] = "last"

        df_daily_agg = df_p.groupby("date").agg(agg_dict)

        start_date = df_p["date"].min()
        end_date = df_p["date"].max()
        full_idx = pd.date_range(start_date, end_date, freq="D", name="date")

        df_daily = df_daily_agg.reindex(full_idx)
        df_daily["load_value"] = df_daily["load_value"].fillna(0.0)

        acute_series = []
        chronic_series = []

        acute_prev = df_daily["load_value"].iloc[0]
        chronic_prev = df_daily["load_value"].iloc[0]

        for val in df_daily["load_value"]:
            acute_curr = (val * LAMBDA_ACUTE) + ((1.0 - LAMBDA_ACUTE) * acute_prev)
            chronic_curr = (val * LAMBDA_CHRONIC) + ((1.0 - LAMBDA_CHRONIC) * chronic_prev)
            acute_series.append(acute_curr)
            chronic_series.append(chronic_curr)
            acute_prev = acute_curr
            chronic_prev = chronic_curr

        df_daily["acute_ewma"] = acute_series
        df_daily["chronic_ewma"] = chronic_series

        df_daily["acwr"] = np.where(
            df_daily["chronic_ewma"] > 1e-3,
            df_daily["acute_ewma"] / df_daily["chronic_ewma"],
            np.nan
        )

        df_result = df_daily.reset_index()
        status_info = df_result["acwr"].apply(get_acwr_status)
        df_result["acwr_status"] = [s[0] for s in status_info]
        df_result["acwr_color"] = [s[1] for s in status_info]

        if target_date:
            df_sub = df_result[df_result["date"].dt.date <= target_date]
            if df_sub.empty:
                continue
            last_row = df_sub.iloc[-1]
        else:
            last_row = df_result.iloc[-1]

        records.append({
            "player_id": p.id,
            "dorsal": p.dorsal,
            "player_name": p.name,
            "position": p.position,
            "acute_load": last_row["acute_ewma"],
            "chronic_load": last_row["chronic_ewma"],
            "acwr": last_row["acwr"],
            "acwr_status": last_row["acwr_status"],
            "acwr_color": last_row["acwr_color"],
            "last_active_date": last_row["date"].date()
        })

    return pd.DataFrame(records)


# ==============================================================================
# 4. RESUMEN COMPLETO DE LA SESIÓN PARA EL CUERPO TÉCNICO
# ==============================================================================

def calculate_session_summary(session: Session, session_id: int, club_id: int = DEFAULT_CLUB_ID) -> Dict[str, Any]:
    """
    Obtiene el resumen consolidado de una sesión: datos por jugador, comparativa con objetivos y alertas.
    """
    sess_obj = session.query(TrainingSession).filter(
        TrainingSession.id == session_id,
        TrainingSession.club_id == club_id
    ).first()
    if not sess_obj:
        return {}

    sess_info = SimpleNamespace(
        id=sess_obj.id,
        name=sess_obj.name,
        date=sess_obj.date,
        microcycle_day=sess_obj.microcycle_day,
        session_type=sess_obj.session_type,
        duration_minutes=sess_obj.duration_minutes,
        pitch_condition=sess_obj.pitch_condition,
        notes=sess_obj.notes
    )

    query = (
        session.query(
            Player.id.label("player_id"),
            Player.name.label("player_name"),
            Player.dorsal,
            Player.position,
            PlayerMetric.minutes_played,
            PlayerMetric.total_distance,
            PlayerMetric.hsr_distance,
            PlayerMetric.sprint_distance,
            PlayerMetric.hmld,
            PlayerMetric.accelerations_eff,
            PlayerMetric.decelerations_eff,
            (PlayerMetric.accelerations_eff + PlayerMetric.decelerations_eff).label("acc_dec_eff"),
            PlayerMetric.max_speed,
            PlayerMetric.player_load,
            PlayerMetric.rpe
        )
        .join(PlayerMetric, Player.id == PlayerMetric.player_id)
        .filter(PlayerMetric.session_id == session_id, Player.club_id == club_id)
        .order_by(Player.dorsal.asc())
    )
    df_metrics = pd.read_sql(query.statement, session.bind)
    if df_metrics.empty:
        return {"session": sess_info, "metrics": pd.DataFrame(), "team_kpis": {}}

    # Calcular Z-scores posicionales
    df_metrics = calculate_position_z_scores(df_metrics)

    # Cruzar con el ACWR del día de la sesión
    df_acwr = get_latest_player_acwr(session, target_date=sess_info.date, club_id=club_id)
    if not df_acwr.empty:
        df_metrics = df_metrics.merge(
            df_acwr[["player_id", "acute_load", "chronic_load", "acwr", "acwr_status", "acwr_color"]],
            on="player_id",
            how="left"
        )
    else:
        df_metrics["acute_load"] = 0.0
        df_metrics["chronic_load"] = 0.0
        df_metrics["acwr"] = 1.0
        df_metrics["acwr_status"] = "Óptimo Sweet Spot (0.80-1.30)"
        df_metrics["acwr_color"] = "#10B981"

    # Calcular sRPE de Foster
    df_metrics["srpe"] = df_metrics.apply(
        lambda r: (float(r["rpe"]) * (float(r["minutes_played"]) if float(r["minutes_played"]) > 0 else float(sess_info.duration_minutes)))
        if pd.notna(r.get("rpe")) and r.get("rpe") is not None and float(r["rpe"]) > 0
        else np.nan,
        axis=1
    )

    # Cruzar con el cumplimiento individual respecto al partido
    df_comp_indiv = calculate_individual_microcycle_compliance(session, session_id, club_id=club_id)
    if not df_comp_indiv.empty:
        df_metrics = df_metrics.merge(
            df_comp_indiv[[
                "player_id", "key_metric", "key_label", "val_real", "val_target",
                "val_match_100", "compliance_pct", "status", "color_hex", "color_label"
            ]],
            on="player_id",
            how="left"
        )
        df_metrics["compliance_pct"] = df_metrics["compliance_pct"].fillna(100.0)
        df_metrics["global_compliance"] = df_metrics["compliance_pct"]
    else:
        df_metrics["compliance_pct"] = 100.0
        df_metrics["global_compliance"] = 100.0

    rpe_valid = df_metrics["rpe"].dropna()
    rpe_valid = rpe_valid[rpe_valid > 0]
    srpe_valid = df_metrics["srpe"].dropna()

    team_kpis = {
        "num_players": len(df_metrics),
        "mean_distance": float(df_metrics["total_distance"].mean()),
        "mean_hsr": float(df_metrics["hsr_distance"].mean()),
        "mean_hmld": float(df_metrics["hmld"].mean()),
        "mean_acc_dec": float(df_metrics["acc_dec_eff"].mean()),
        "mean_compliance": float(df_metrics["compliance_pct"].dropna().mean()) if "compliance_pct" in df_metrics.columns else 100.0,
        "players_in_danger": int((df_metrics.get("acwr", pd.Series()) > ACWR_DANGER_ZONE).sum()),
        "players_in_caution": int((
            (df_metrics.get("acwr", pd.Series()) > ACWR_SWEET_SPOT_MAX) &
            (df_metrics.get("acwr", pd.Series()) <= ACWR_DANGER_ZONE)
        ).sum()),
        "players_in_underload": int((df_metrics.get("acwr", pd.Series()) < ACWR_UNDERLOAD).sum()),
        "players_in_optimal": int((
            (df_metrics.get("acwr", pd.Series()) >= ACWR_UNDERLOAD) &
            (df_metrics.get("acwr", pd.Series()) <= ACWR_SWEET_SPOT_MAX)
        ).sum()),
        "mean_rpe": float(rpe_valid.mean()) if not rpe_valid.empty else None,
        "count_rpe": int(len(rpe_valid)),
        "mean_srpe": float(srpe_valid.mean()) if not srpe_valid.empty else None
    }

    # Cargar objetivos teóricos por posición para comparativas tácticas
    target_objs = session.query(TargetLoad).filter(
        TargetLoad.microcycle_day == sess_info.microcycle_day,
        TargetLoad.club_id == club_id
    ).all()
    targets_dict = {
        t.position: {
            "target_td": getattr(t, "target_td", 0.0),
            "target_hsr": getattr(t, "target_hsr", 0.0),
            "target_hmld": getattr(t, "target_hmld", 0.0),
            "target_eff": (getattr(t, "target_acc_eff", 0) or 0) + (getattr(t, "target_dec_eff", 0) or 0)
        }
        for t in target_objs
    }

    return {
        "session": sess_info,
        "metrics": df_metrics,
        "team_kpis": team_kpis,
        "compliance_indiv": df_comp_indiv,
        "targets": targets_dict
    }


def calculate_position_z_scores(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calcula los Z-scores de cada métrica normalizados dentro de la misma demarcación posicional.
    Z = (X - mean_pos) / std_pos
    """
    metrics_to_normalize = ["total_distance", "hsr_distance", "hmld", "acc_dec_eff"]

    for col in metrics_to_normalize:
        z_col = f"z_{col}"
        df[z_col] = 0.0

        for pos in df["position"].unique():
            idx = df["position"] == pos
            sub = df.loc[idx, col]
            std = sub.std(ddof=0)
            mean = sub.mean()

            if std > 1e-4:
                df.loc[idx, z_col] = (sub - mean) / std
            else:
                df.loc[idx, z_col] = 0.0

    return df


def get_player_longitudinal_comparison(
    session: Session,
    player_id: int,
    club_id: int = DEFAULT_CLUB_ID
) -> Dict[str, Any]:
    """
    Extrae la evolución longitudinal completa de un jugador:
    - Todas sus sesiones con fecha, tipo y métricas.
    - Comparativa directa Entrenamiento vs Partido.
    - Datos de su Partido de Máxima Exigencia (100% individual).
    """
    query = (
        session.query(
            TrainingSession.date,
            TrainingSession.name.label("session_name"),
            TrainingSession.microcycle_day,
            TrainingSession.session_type,
            PlayerMetric.total_distance,
            PlayerMetric.hsr_distance,
            PlayerMetric.sprint_distance,
            PlayerMetric.hmld,
            (PlayerMetric.accelerations_eff + PlayerMetric.decelerations_eff).label("acc_dec_eff"),
            PlayerMetric.max_speed,
            PlayerMetric.rpe
        )
        .join(PlayerMetric, TrainingSession.id == PlayerMetric.session_id)
        .filter(PlayerMetric.player_id == player_id, TrainingSession.club_id == club_id)
        .order_by(TrainingSession.date.asc())
    )
    df_long = pd.read_sql(query.statement, session.bind)
    peak = get_player_match_peak(session, player_id, club_id=club_id)

    return {
        "history": df_long,
        "peak": peak
    }


def calculate_compliance_table(df_metrics: pd.DataFrame, targets_dict: Optional[Dict[str, Dict[str, float]]] = None) -> pd.DataFrame:
    """
    Genera un DataFrame resumido de Comparativa Real vs Planificado agrupado por demarcación.
    """
    if df_metrics.empty:
        return pd.DataFrame()

    summary_rows = []
    positions = df_metrics["position"].unique()

    for pos in positions:
        sub = df_metrics[df_metrics["position"] == pos]
        real_td = sub["total_distance"].mean() if "total_distance" in sub else 0.0
        real_hsr = sub["hsr_distance"].mean() if "hsr_distance" in sub else 0.0
        real_hmld = sub["hmld"].mean() if "hmld" in sub else 0.0
        real_eff = sub["acc_dec_eff"].mean() if "acc_dec_eff" in sub else 0.0

        target = (targets_dict or {}).get(pos, {})
        tgt_td = target.get("target_td", 0.0)
        tgt_hsr = target.get("target_hsr", 0.0)
        tgt_hmld = target.get("target_hmld", 0.0)
        tgt_eff = target.get("target_eff", 0.0)

        summary_rows.append({
            "Posición": pos,
            "Jugadores": len(sub),
            "DT Real (m)": round(real_td, 1),
            "DT Objetivo (m)": round(tgt_td, 1),
            "% Cumpl. DT": round((real_td / tgt_td * 100) if tgt_td else 0, 1),
            "HSR Real (m)": round(real_hsr, 1),
            "HSR Objetivo (m)": round(tgt_hsr, 1),
            "% Cumpl. HSR": round((real_hsr / tgt_hsr * 100) if tgt_hsr else 0, 1),
            "HMLD Real (m)": round(real_hmld, 1),
            "HMLD Objetivo (m)": round(tgt_hmld, 1),
            "% Cumpl. HMLD": round((real_hmld / tgt_hmld * 100) if tgt_hmld else 0, 1),
            "AC.E Real": round(real_eff, 1),
            "AC.E Objetivo": round(tgt_eff, 1),
            "% Cumpl. AC.E": round((real_eff / tgt_eff * 100) if tgt_eff else 0, 1),
        })

    return pd.DataFrame(summary_rows)


# ==============================================================================
# 5. METODOLOGÍA DEL PREPARADOR FÍSICO: TABLAS DE REFERENCIA EXCEL DE PARTIDOS
# ==============================================================================

def get_all_reference_matches(
    db: Session,
    club_id: int = DEFAULT_CLUB_ID,
    include_individual_peaks: bool = True,
    *args,
    **kwargs
) -> List[Dict[str, Any]]:
    """
    Recupera exclusivamente los partidos oficiales de Liga regular (Temporada 26/27).
    - Si include_individual_peaks=False (Referencia Partidos P.F.): lista ÚNICAMENTE partidos oficiales de liga.
    - Si include_individual_peaks=True (Planificación Pre-Sesión): incluye además la Máxima Exigencia Individual.
    """
    all_sessions = (
        db.query(TrainingSession)
        .filter(
            TrainingSession.club_id == club_id,
            (TrainingSession.session_type == "Partido") | (TrainingSession.microcycle_day == "MD")
        )
        .order_by(TrainingSession.date.asc())
        .all()
    )

    # Filtrar exclusivamente partidos oficiales de Liga (excluyendo pretemporada y entrenamientos)
    league_sessions = [s for s in all_sessions if is_official_league_match(s)]
    sess_ids = [s.id for s in league_sessions]

    # Pre-cargar estadísticas por sesión en 1 sola consulta batch agrupada
    stats_by_sess = {}
    if sess_ids:
        agg_rows = (
            db.query(
                PlayerMetric.session_id,
                func.count(PlayerMetric.id),
                func.sum(PlayerMetric.total_distance)
            )
            .filter(PlayerMetric.session_id.in_(sess_ids))
            .group_by(PlayerMetric.session_id)
            .all()
        )
        for s_id, cnt, dist in agg_rows:
            stats_by_sess[s_id] = (cnt, dist or 0.0)

    # Deduplicar por rival / fecha, priorizando la sesión oficial importada de Ubiko con datos reales
    deduped_matches = {}
    for s in league_sessions:
        p_count, _ = stats_by_sess.get(s.id, (0, 0.0))
        if p_count == 0:
            continue

        s_upper = s.name.upper()
        if "MIJAS" in s_upper or "LAGUNAS" in s_upper:
            key = "MIJAS"
        elif "RECREATIVO" in s_upper or "HUELVA" in s_upper:
            key = "HUELVA"
        else:
            key = str(s.date)

        is_ubiko_import = "FÚTBOL 11" in s_upper or "FUTBOL 11" in s_upper or "CONTRA" in s_upper
        score = p_count + (100 if is_ubiko_import else 0)

        if key not in deduped_matches:
            deduped_matches[key] = (s, score)
        else:
            if score > deduped_matches[key][1]:
                deduped_matches[key] = (s, score)

    sorted_league_matches = sorted([item[0] for item in deduped_matches.values()], key=lambda x: x.date)

    res: List[Dict[str, Any]] = []

    # Opción 0: Máxima Exigencia Individual (SOLO si se solicita explícitamente para planificación pre-sesión)
    if include_individual_peaks:
        active_player_count = db.query(Player.id).filter(Player.club_id == club_id, Player.active == True).count()
        res.append({
            "session_id": None,
            "key": "PEAK_CONSOLIDATED",
            "order": 0,
            "name": "Máxima Exigencia Individual (100% de cada jugador)",
            "label": "⭐ Máxima Exigencia Individual (100% Techo Dinámico de cada jugador)",
            "date": date.today(),
            "num_players": active_player_count,
            "total_distance_km": 0.0
        })

    for idx, m in enumerate(sorted_league_matches, 1):
        p_count, tot_dist_m = stats_by_sess.get(m.id, (0, 0.0))

        clean_name = m.name.upper()
        if "MIJAS" in clean_name or "LAGUNAS" in clean_name:
            opponent = "CP Mijas Las Lagunas"
        elif "RECREATIVO" in clean_name or "HUELVA" in clean_name:
            opponent = "Recreativo de Huelva"
        else:
            if "CONTRA" in clean_name:
                parts = m.name.split("contra")
                opponent = parts[-1].split("_")[0].strip()
            else:
                opponent = m.name.strip()

        # Formato exacto: "Jornada 1: Partido contra X"
        label = f"🏟️ Jornada {idx}: Partido contra {opponent} ({m.date.strftime('%d/%m/%Y')})"

        res.append({
            "session_id": m.id,
            "key": f"MATCH_{m.id}",
            "order": idx,
            "name": m.name,
            "label": label,
            "date": m.date,
            "num_players": p_count,
            "total_distance_km": round(tot_dist_m / 1000.0, 2)
        })

    return res


def get_match_reference_table_data(
    db: Session,
    session_id: Optional[int] = None,
    club_id: int = DEFAULT_CLUB_ID,
    top_player_id: Optional[int] = None,
    *args,
    **kwargs
) -> Dict[str, Any]:
    """
    Genera la tabla de referencia de datos de partido idéntica al formato Excel del preparador físico:
    - Columnas exactas:
      [POSICIÓN | JUGADOR | TIEMPO | DISTANCIA TOTAL (km) | VELOCIDAD MAX (km/h) | HSR (m) | METROS EN SPRINT | #SPRINTS | #ACC EXPL | #DCC EXPL]
    - Filas estructuradas exactamente según la plantilla del club (6 Roles + Resumen Equipo):
      * JUGADOR TOP (Fila destacada con fondo rojo suave: mayor rendimiento global de la sesión)
      * CENTRAL (ej. Ginés)
      * LATERAL (ej. Rafa en P1 / Manu Viana en P2)
      * MEDIOCENTRO (ej. Lalo)
      * EXTREMO (ej. Cellou)
      * DELANTERO (ej. Salva)
      * DATOS REFERENCIA GENERALES EQUIPO (Fila inferior con fondo azul distintivo)
    - Proporciona además 'df_full' con todos los convocados para inspección detallada.
    """
    pos_order = {
        "CENTRAL": 1,
        "LATERAL": 2,
        "MEDIOCENTRO": 3,
        "EXTREMO": 4,
        "DELANTERO": 5,
        "PORTERO": 6
    }

    players_data = []

    if session_id is not None:
        # Extraer métricas reales de la sesión de partido seleccionada
        metrics = (
            db.query(
                PlayerMetric.player_id,
                PlayerMetric.minutes_played,
                PlayerMetric.total_distance,
                PlayerMetric.max_speed,
                PlayerMetric.hsr_distance,
                PlayerMetric.sprint_distance,
                PlayerMetric.accelerations_eff,
                PlayerMetric.decelerations_eff
            )
            .filter(PlayerMetric.session_id == session_id)
            .all()
        )
        metrics_by_player = {m.player_id: m for m in metrics}

        # Cargar todos los futbolistas activos y mapa de techos de máxima exigencia para fallback
        all_players = (
            db.query(Player)
            .filter(Player.club_id == club_id, Player.active == True)
            .order_by(Player.dorsal.asc())
            .all()
        )
        peaks_map = {
            pk.player_id: pk
            for pk in db.query(PlayerMatchPeak).filter(PlayerMatchPeak.club_id == club_id).all()
        }
        if not peaks_map:
            sync_and_update_player_match_peaks(db, club_id=club_id)
            peaks_map = {
                pk.player_id: pk
                for pk in db.query(PlayerMatchPeak).filter(PlayerMatchPeak.club_id == club_id).all()
            }

        for p in all_players:
            pos_norm = p.position.upper().strip() if p.position else ""
            if pos_norm == "PORTERO":
                continue

            m = metrics_by_player.get(p.id)
            # Si participó en este partido específico con minutos registrados
            if m is not None and (m.minutes_played or 0) > 0 and (m.total_distance or 0) > 0:
                td_m = float(m.total_distance or 0.0)
                hsr_m = float(m.hsr_distance or 0.0)
                vmax = float(m.max_speed or 0.0)
                mins = float(m.minutes_played or 0.0)
                acc = int(m.accelerations_eff or 0)
                dec = int(m.decelerations_eff or 0)
                raw_sp = float(m.sprint_distance or 0.0)
                sess_type = "Partido"
                base_source = f"⚽ Partido ({mins:.0f}')"
            else:
                # No convocado o sin minutos en este partido específico
                td_m = 0.0
                hsr_m = 0.0
                vmax = 0.0
                mins = 0.0
                acc = 0
                dec = 0
                raw_sp = 0.0
                sess_type = "No convocado"
                base_source = "📋 No convocado"

            if raw_sp <= 35.0:
                sprints_cnt = int(raw_sp)
                sprint_m = round(raw_sp * 18.0, 1)
            else:
                sprint_m = round(raw_sp, 1)
                sprints_cnt = max(1, int(round(raw_sp / 18.0))) if raw_sp > 0 else 0

            # Índice de rendimiento físico ponderado (Score de Exigencia Competitiva)
            if td_m > 0:
                perf_score = (
                    (td_m / 10000.0) * 0.35 +
                    (hsr_m / 450.0) * 0.25 +
                    (sprint_m / 200.0) * 0.20 +
                    ((acc + dec) / 200.0) * 0.20
                )
            else:
                perf_score = 0.0

            players_data.append({
                "player_id": p.id,
                "dorsal": p.dorsal,
                "player_name": p.name,
                "position_raw": p.position,
                "position": pos_norm,
                "session_type": sess_type,
                "base_source": base_source,
                "minutes": mins,
                "total_distance_m": td_m,
                "distance_km": round(td_m / 1000.0, 2),
                "max_speed": round(vmax, 2),
                "hsr_m": round(hsr_m, 1),
                "sprint_m": sprint_m,
                "sprints_cnt": sprints_cnt,
                "acc_expl": acc,
                "dcc_expl": dec,
                "total_eff": acc + dec,
                "perf_score": perf_score
            })
    else:
        # Usar Partido Récord / Techo Dinámico individual (100%)
        has_peaks = db.query(PlayerMatchPeak.id).filter(PlayerMatchPeak.club_id == club_id).first()
        if not has_peaks:
            sync_and_update_player_match_peaks(db, club_id=club_id)
        peaks = (
            db.query(
                Player.id.label("player_id"),
                Player.dorsal,
                Player.name.label("player_name"),
                Player.position,
                PlayerMatchPeak.peak_td,
                PlayerMatchPeak.peak_hsr,
                PlayerMatchPeak.peak_sprint,
                PlayerMatchPeak.peak_acc_eff,
                PlayerMatchPeak.peak_dec_eff,
                PlayerMatchPeak.peak_max_speed,
                PlayerMatchPeak.peak_session_name,
                PlayerMatchPeak.peak_session_type,
                PlayerMatchPeak.peak_minutes
            )
            .join(PlayerMatchPeak, Player.id == PlayerMatchPeak.player_id)
            .filter(Player.club_id == club_id, Player.active == True)
            .all()
        )

        for p in peaks:
            pos_norm = p.position.upper().strip()
            if pos_norm == "PORTERO":
                continue

            td_m = float(p.peak_td) if p.peak_td is not None else 0.0
            hsr_m = float(p.peak_hsr) if p.peak_hsr is not None else 0.0
            vmax = float(p.peak_max_speed) if p.peak_max_speed is not None else 0.0
            acc = int(p.peak_acc_eff) if p.peak_acc_eff is not None else 0
            dec = int(p.peak_dec_eff) if p.peak_dec_eff is not None else 0
            raw_sp = float(p.peak_sprint) if p.peak_sprint is not None else 0.0

            if raw_sp <= 35.0:
                sprints_cnt = int(raw_sp)
                sprint_m = round(raw_sp * 18.0, 1)
            else:
                sprint_m = round(raw_sp, 1)
                sprints_cnt = max(1, int(round(raw_sp / 18.0))) if raw_sp > 0 else 0

            has_played = td_m > 0.0
            sess_type = p.peak_session_type or ("Partido" if "Partido" in str(p.peak_session_name) else "Entrenamiento")
            real_mins = float(p.peak_minutes) if p.peak_minutes else (90.0 if sess_type == "Partido" else 70.0)
            mins = real_mins if has_played else 0.0
            base_source_label = f"⚽ Partido ({real_mins:.0f}')" if sess_type == "Partido" else (f"🏃 Entreno ({real_mins:.0f}')" if sess_type == "Entrenamiento" else f"📋 Teórico ({real_mins:.0f}')")

            perf_score = (
                (td_m / 10000.0) * 0.35 +
                (hsr_m / 450.0) * 0.25 +
                (sprint_m / 200.0) * 0.20 +
                ((acc + dec) / 200.0) * 0.20
            ) if has_played else 0.0

            players_data.append({
                "player_id": p.player_id,
                "dorsal": p.dorsal,
                "player_name": p.player_name,
                "position_raw": p.position,
                "position": pos_norm,
                "session_type": sess_type,
                "base_source": base_source_label,
                "minutes": mins,
                "total_distance_m": td_m,
                "distance_km": round(td_m / 1000.0, 2),
                "max_speed": round(vmax, 2),
                "hsr_m": round(hsr_m, 1),
                "sprint_m": sprint_m,
                "sprints_cnt": sprints_cnt,
                "acc_expl": acc,
                "dcc_expl": dec,
                "total_eff": acc + dec,
                "perf_score": perf_score
            })

    if not players_data:
        return {
            "df_display": pd.DataFrame(),
            "df_full": pd.DataFrame(),
            "df_raw": pd.DataFrame(),
            "top_player": None,
            "top_candidates": [],
            "team_summary": {}
        }

    # =========================================================================
    # 1. LOCALIZAR AL JUGADOR TOP
    # Metodología del Preparador Físico: "por distancias, minutos y a ojo cualitativo y posición"
    # =========================================================================
    max_session_mins = max([p["minutes"] for p in players_data if p["minutes"] > 0], default=90.0)
    # Umbral de minutos representativos (partido completo / titulares habituales: >= 65 min o 70% del máx)
    threshold_mins = min(65.0, max_session_mins * 0.70) if max_session_mins > 30.0 else 0.0

    # Candidatos ordenados según el criterio del P.F.:
    # 1) Haber cumplido los minutos requeridos (prioridad a titulares)
    # 2) Mayor Distancia Total (km)
    # 3) Mayor volumen de Alta Intensidad (HSR)
    top_candidates = sorted(
        [p for p in players_data if p["distance_km"] > 0],
        key=lambda x: (x["minutes"] >= threshold_mins, x["distance_km"], x["hsr_m"]),
        reverse=True
    )

    top_player_item = None
    # A) Criterio cualitativo manual ("a ojo cualitativo"): si el P.F. seleccionó a un jugador específico
    if top_player_id is not None:
        top_player_item = next((p for p in players_data if p["player_id"] == top_player_id), None)

    # B) Si no hay selección manual, sugerir automáticamente al candidato #1 según minutos y distancia:
    if not top_player_item and top_candidates:
        top_player_item = top_candidates[0]
    elif not top_player_item and players_data:
        top_player_item = players_data[0]

    top_player_id = top_player_item["player_id"] if top_player_item else None

    # 2. Ordenar por Bloque Posicional y dorsal
    players_sorted = sorted(
        players_data,
        key=lambda x: (pos_order.get(x["position"], 99), x["dorsal"])
    )

    # 3. Cálculos globales del equipo para la fila inferior (exclusivamente futbolistas que jugaron)
    team_played = [p for p in players_data if p["minutes"] > 0 and p["distance_km"] > 0]
    team_mean_time = float(np.mean([p["minutes"] for p in team_played])) if team_played else 90.0
    team_tot_dist_km = float(np.sum([p["distance_km"] for p in team_played]))
    team_peak_speed = float(np.max([p["max_speed"] for p in team_played])) if team_played else 0.0
    team_tot_hsr = float(np.sum([p["hsr_m"] for p in team_played]))
    team_tot_sprint_m = float(np.sum([p["sprint_m"] for p in team_played]))
    team_tot_sprints = int(np.sum([p["sprints_cnt"] for p in team_played]))
    team_tot_acc = int(np.sum([p["acc_expl"] for p in team_played]))
    team_tot_dec = int(np.sum([p["dcc_expl"] for p in team_played]))

    team_row = {
        "POSICIÓN": "EQUIPO",
        "JUGADOR": "DATOS REFERENCIA GENERALES EQUIPO",
        "TIEMPO": f"{team_mean_time:.0f}' (Media)",
        "DISTANCIA TOTAL (km)": f"{team_tot_dist_km:.2f} KM",
        "VELOCIDAD MAX (km/h)": f"{team_peak_speed:.2f} KM/H",
        "HSR (m)": f"{team_tot_hsr / 1000.0:.3f} KM" if team_tot_hsr >= 1000 else f"{team_tot_hsr:.0f} m",
        "METROS EN SPRINT": f"{team_tot_sprint_m / 1000.0:.3f} KM" if team_tot_sprint_m >= 1000 else f"{team_tot_sprint_m:.0f} m",
        "#SPRINTS": str(team_tot_sprints),
        "#ACC EXPL": str(team_tot_acc),
        "#DCC EXPL": str(team_tot_dec),
        "_row_type": "team",
        "_player_id": 0
    }

    # =========================================================================
    # A) TABLA OFICIAL P.F.: EXACTAMENTE 6 ROLES + RESUMEN EQUIPO (FORMATO EXCEL)
    # =========================================================================
    target_roles = ["CENTRAL", "LATERAL", "MEDIOCENTRO", "EXTREMO", "DELANTERO"]
    official_rows = []

    # Fila 1: ⭐ JUGADOR TOP
    official_rows.append({
        "POSICIÓN": "⭐ JUGADOR TOP",
        "JUGADOR": f"#{top_player_item['dorsal']} {top_player_item['player_name'].upper()} ({top_player_item['position']})",
        "TIEMPO": f"{top_player_item['minutes']:.0f}'",
        "DISTANCIA TOTAL (km)": f"{top_player_item['distance_km']:.2f}",
        "VELOCIDAD MAX (km/h)": f"{top_player_item['max_speed']:.2f}",
        "HSR (m)": f"{top_player_item['hsr_m']:.1f}",
        "METROS EN SPRINT": f"{top_player_item['sprint_m']:.1f}",
        "#SPRINTS": str(top_player_item["sprints_cnt"]),
        "#ACC EXPL": str(top_player_item["acc_expl"]),
        "#DCC EXPL": str(top_player_item["dcc_expl"]),
        "_row_type": "top",
        "_player_id": top_player_item["player_id"]
    })

    # Filas 2 a 6: Una por cada demarcación posicional clave
    for role in target_roles:
        cands_all = [
            p for p in players_data
            if p["minutes"] > 0 and p["distance_km"] > 0 and (
                p["position"] == role or
                (role == "LATERAL" and p["player_name"].upper() in ["MANU VIANA", "VIANA", "RAFA", "PAJUELO", "TALARN", "A. TALARN", "CONNOR"]) or
                (role == "EXTREMO" and p["player_name"].upper() in ["CELLOU", "ALAN", "RAFITA"]) or
                (role == "MEDIOCENTRO" and p["player_name"].upper() in ["LALO", "POLACO", "JUAN MARIA", "PEPELU", "VIRTUDES", "TOPO"]) or
                (role == "CENTRAL" and p["player_name"].upper() in ["GINÉS", "GINES", "SALVI", "SALVI VERA", "MARCOS PEREZ"]) or
                (role == "DELANTERO" and p["player_name"].upper() in ["SALVA", "SALVA VEGAS", "LOREN", "BIANCO", "JOSEMI", "SETH VEGA", "MORO"])
            )
        ]
        cands_no_top = [p for p in cands_all if p["player_id"] != top_player_item["player_id"]]
        cands_pool = cands_no_top if cands_no_top else cands_all

        # Preferir candidatos cuya posición natural en BD sea exactamente 'role'
        cands_exact = [p for p in cands_pool if p["position"] == role]
        if any(p["minutes"] >= 65 for p in cands_exact):
            cands = [p for p in cands_exact if p["minutes"] >= 65]
        elif cands_exact:
            # Si hay futbolistas en esa demarcación que jugaron, seleccionarlos con prioridad
            cands = cands_exact
        elif any(p["minutes"] >= 65 for p in cands_pool):
            cands = [p for p in cands_pool if p["minutes"] >= 65]
        else:
            cands = cands_pool

        best_p = max(cands, key=lambda x: (x["minutes"] >= 65, x["distance_km"], x["hsr_m"])) if cands else None
        if not best_p:
            best_p = next((p for p in players_data if p["position"] == role and p["minutes"] > 0 and p["distance_km"] > 0), None)

        if best_p:
            official_rows.append({
                "POSICIÓN": role,
                "JUGADOR": f"#{best_p['dorsal']} {best_p['player_name'].upper()}",
                "TIEMPO": f"{best_p['minutes']:.0f}'",
                "DISTANCIA TOTAL (km)": f"{best_p['distance_km']:.2f}",
                "VELOCIDAD MAX (km/h)": f"{best_p['max_speed']:.2f}",
                "HSR (m)": f"{best_p['hsr_m']:.1f}",
                "METROS EN SPRINT": f"{best_p['sprint_m']:.1f}",
                "#SPRINTS": str(best_p["sprints_cnt"]),
                "#ACC EXPL": str(best_p["acc_expl"]),
                "#DCC EXPL": str(best_p["dcc_expl"]),
                "_row_type": "player_top" if best_p["player_id"] == top_player_item["player_id"] else "player",
                "_player_id": best_p["player_id"]
            })

    official_rows.append(team_row)

    # =========================================================================
    # B) TABLA CONVOCATORIA COMPLETA (TODOS LOS JUGADORES REGISTRADOS)
    # =========================================================================
    full_rows = []
    full_rows.append(official_rows[0])  # ⭐ JUGADOR TOP
    for p in players_sorted:
        is_top = (p["player_id"] == top_player_item["player_id"])
        time_str = f"{p['minutes']:.0f}'" if p["minutes"] > 0 else "0'"
        name_str = f"#{p['dorsal']} {p['player_name'].upper()}" + (" (Sin minutos)" if p["minutes"] == 0 else "")
        full_rows.append({
            "POSICIÓN": p["position"],
            "JUGADOR": name_str,
            "TIEMPO": time_str,
            "DISTANCIA TOTAL (km)": f"{p['distance_km']:.2f}",
            "VELOCIDAD MAX (km/h)": f"{p['max_speed']:.2f}",
            "HSR (m)": f"{p['hsr_m']:.1f}",
            "METROS EN SPRINT": f"{p['sprint_m']:.1f}",
            "#SPRINTS": str(p["sprints_cnt"]),
            "#ACC EXPL": str(p["acc_expl"]),
            "#DCC EXPL": str(p["dcc_expl"]),
            "_row_type": "player_top" if is_top else "player",
            "_player_id": p["player_id"]
        })
    full_rows.append(team_row)

    df_display = pd.DataFrame(official_rows)
    df_full = pd.DataFrame(full_rows)

    team_summary = {
        "num_players": len(team_played),
        "mean_time": team_mean_time,
        "tot_distance_km": team_tot_dist_km,
        "peak_max_speed": team_peak_speed,
        "tot_hsr_m": team_tot_hsr,
        "tot_sprint_m": team_tot_sprint_m,
        "tot_sprints": team_tot_sprints,
        "tot_acc_expl": team_tot_acc,
        "tot_dcc_expl": team_tot_dec
    }

    return {
        "df_display": df_display,
        "df_full": df_full,
        "df_raw": pd.DataFrame(players_data),
        "top_player": top_player_item,
        "top_candidates": [
            {
                "player_id": p["player_id"],
                "dorsal": p["dorsal"],
                "player_name": p["player_name"],
                "position": p["position"],
                "distance_km": p["distance_km"],
                "minutes": p["minutes"],
                "label": f"#{p['dorsal']} {p['player_name'].upper()} ({p['position']}) — {p['distance_km']:.2f} km ({p['minutes']:.0f}')"
            }
            for p in top_candidates
        ],
        "team_summary": team_summary
    }


def calculate_excel_pre_session_prescription(
    db: Session,
    reference_session_id: Optional[int],
    microcycle_day: str,
    pct_td: float,
    pct_hsr: float,
    pct_sprint: float,
    pct_eff: float,
    club_id: int = DEFAULT_CLUB_ID
) -> Dict[str, Any]:
    """
    Calculadora Pre-Sesión con la estructura visual exacta del Excel del club:
    Aplica los porcentajes configurados por el preparador físico sobre el partido de referencia
    para obtener la tabla de metas mínimas cuantitativas para el entrenamiento de hoy:
    [POSICIÓN | JUGADOR | TIEMPO | DISTANCIA TOTAL (km) | VELOCIDAD MAX (km/h) | HSR (m) | METROS EN SPRINT | #SPRINTS | #ACC EXPL | #DCC EXPL]
    """
    # 1. Obtener datos base del partido de referencia (o techo individual)
    ref_data = get_match_reference_table_data(db, session_id=reference_session_id, club_id=club_id)
    df_raw = ref_data.get("df_raw", pd.DataFrame())

    if df_raw.empty:
        return {"df_display": pd.DataFrame(), "team_targets": {}}

    pos_order = {
        "CENTRAL": 1,
        "LATERAL": 2,
        "MEDIOCENTRO": 3,
        "EXTREMO": 4,
        "DELANTERO": 5,
        "PORTERO": 6
    }

    # Tiempos de entrenamiento estándar por día de microciclo
    day_durations = {
        "MD-4": 70,
        "MD-3": 85,
        "MD-2": 60,
        "MD-1": 45,
        "MD+1": 50,
        "MD+2": 50,
        "MD": 90
    }
    target_duration = day_durations.get(microcycle_day.upper().strip(), 75)

    players_list = df_raw.to_dict("records")
    players_sorted = sorted(
        players_list,
        key=lambda x: (pos_order.get(x["position"], 99), x["dorsal"])
    )

    rows = []
    tot_min_td_km = 0.0
    tot_min_hsr = 0.0
    tot_min_sprint_m = 0.0
    tot_min_sprints = 0
    tot_min_acc = 0
    tot_min_dec = 0

    peaks_map = {
        pk.player_id: pk
        for pk in db.query(PlayerMatchPeak).filter(PlayerMatchPeak.club_id == club_id).all()
    }

    for p in players_sorted:
        p_dist_km = float(p.get("distance_km", 0.0))
        p_hsr_m = float(p.get("hsr_m", 0.0))
        p_sprint_m = float(p.get("sprint_m", 0.0))
        p_sprints_cnt = int(p.get("sprints_cnt", 0))
        p_acc = int(p.get("acc_expl", 0))
        p_dec = int(p.get("dcc_expl", 0))
        p_vmax = float(p.get("max_speed", 0.0))
        p_sess_type = p.get("session_type", "Partido")
        p_base_source = p.get("base_source", f"⚽ Partido ({p.get('minutes', 90):.0f}')")

        if p_dist_km == 0.0:
            # Jugador que no disputó minutos en el partido de referencia: fallback a su Techo de Entrenamiento
            pk = peaks_map.get(p["player_id"])
            if pk and (pk.peak_td or 0) >= 3000.0:
                p_dist_km = round(float(pk.peak_td or 0.0) / 1000.0, 2)
                p_hsr_m = float(pk.peak_hsr or 0.0)
                p_sprint_m = float(pk.peak_sprint or 0.0)
                p_sprints_cnt = max(1, int(round(p_sprint_m / 18.0))) if p_sprint_m > 0 else 0
                p_acc = int(pk.peak_acc_eff or 0)
                p_dec = int(pk.peak_dec_eff or 0)
                p_vmax = float(pk.peak_max_speed or 31.0)
                p_sess_type = pk.peak_session_type or "Entrenamiento"
                p_base_source = "🏃 Techo Entreno (No convocado)"
            else:
                continue

        # Proporcionalidad según metodología del preparador físico:
        # - Evaluados por PARTIDO: porcentaje directo sobre el partido (ej. 40% DT de partido).
        # - Evaluados por ENTRENAMIENTO: su 100% ya proviene de un entrenamiento de máxima exigencia.
        #   Se ajusta proporcionalmente a la intensidad del entrenamiento para alcanzar metas realistas de sesión:
        if p_sess_type == "Entrenamiento":
            # Factores estándar del microciclo (proporción normal de un entreno vs partido)
            std_td_day = 45.0
            std_hsr_day = 30.0
            std_sprint_day = 25.0
            std_eff_day = 80.0

            f_td = min(1.20, max(0.40, pct_td / std_td_day))
            f_hsr = min(1.25, max(0.40, pct_hsr / std_hsr_day))
            f_sprint = min(1.25, max(0.40, pct_sprint / std_sprint_day))
            f_eff = min(1.25, max(0.40, pct_eff / std_eff_day))

            min_dist_km = round(p_dist_km * f_td, 2)
            min_hsr = round(p_hsr_m * f_hsr, 1)
            min_sprint_m = round(p_sprint_m * f_sprint, 1)
            min_sprints = max(1, int(round(p_sprints_cnt * f_sprint))) if p_sprints_cnt > 0 else 0
            min_acc = max(1, int(round(p_acc * f_eff))) if p_acc > 0 else 0
            min_dec = max(1, int(round(p_dec * f_eff))) if p_dec > 0 else 0
        else:
            min_dist_km = round(p_dist_km * (pct_td / 100.0), 2)
            min_hsr = round(p_hsr_m * (pct_hsr / 100.0), 1)
            min_sprint_m = round(p_sprint_m * (pct_sprint / 100.0), 1)
            min_sprints = max(1, int(round(p_sprints_cnt * (pct_sprint / 100.0)))) if p_sprints_cnt > 0 else 0
            min_acc = max(1, int(round(p_acc * (pct_eff / 100.0)))) if p_acc > 0 else 0
            min_dec = max(1, int(round(p_dec * (pct_eff / 100.0)))) if p_dec > 0 else 0

        # Velocidad pico objetivo: 85-90% de su velocidad punta en partido
        target_vmax = round(p_vmax * 0.88, 2)

        tot_min_td_km += min_dist_km
        tot_min_hsr += min_hsr
        tot_min_sprint_m += min_sprint_m
        tot_min_sprints += min_sprints
        tot_min_acc += min_acc
        tot_min_dec += min_dec

        rows.append({
            "POSICIÓN": p["position"],
            "JUGADOR": f"#{p['dorsal']} {p['player_name'].upper()}",
            "TIEMPO": f"{target_duration}'",
            "BASE EVALUACIÓN": p_base_source,
            "DISTANCIA TOTAL (km)": f"{min_dist_km:.2f}",
            "VELOCIDAD MAX (km/h)": f"{target_vmax:.2f}",
            "HSR (m)": f"{min_hsr:.1f}",
            "METROS EN SPRINT": f"{min_sprint_m:.1f}",
            "#SPRINTS": str(min_sprints),
            "#ACC EXPL": str(min_acc),
            "#DCC EXPL": str(min_dec),
            "_row_type": "player",
            "_player_id": p["player_id"]
        })

    # Fila inferior de resumen del equipo (Objetivos Mínimos Colectivos)
    rows.append({
        "POSICIÓN": "EQUIPO",
        "JUGADOR": "DATOS REFERENCIA GENERALES EQUIPO (OBJETIVOS MÍNIMOS)",
        "TIEMPO": f"{target_duration}'",
        "BASE EVALUACIÓN": "PLANTILLA",
        "DISTANCIA TOTAL (km)": f"{tot_min_td_km:.2f} KM",
        "VELOCIDAD MAX (km/h)": f"{round(df_raw['max_speed'].max() * 0.90, 2):.2f} KM/H",
        "HSR (m)": f"{tot_min_hsr:.0f} m",
        "METROS EN SPRINT": f"{tot_min_sprint_m:.0f} m",
        "#SPRINTS": str(tot_min_sprints),
        "#ACC EXPL": str(tot_min_acc),
        "#DCC EXPL": str(tot_min_dec),
        "_row_type": "team",
        "_player_id": 0
    })

    return {
        "df_display": pd.DataFrame(rows),
        "team_targets": {
            "tot_min_td_km": round(tot_min_td_km, 2),
            "tot_min_hsr": round(tot_min_hsr, 1),
            "tot_min_sprint_m": round(tot_min_sprint_m, 1),
            "tot_min_sprints": tot_min_sprints,
            "tot_min_acc": tot_min_acc,
            "tot_min_dec": tot_min_dec
        }
    }


def get_post_session_multivariable_table(
    db: Session,
    session_id: int,
    reference_session_id: Optional[int] = None,
    club_id: int = DEFAULT_CLUB_ID,
    level: Optional[int] = None,
    custom_pcts: Optional[Dict[str, float]] = None
) -> pd.DataFrame:
    """
    Genera la tabla comparativa post-sesión de UBIKO:
    Contrasta Valor Real vs. Mínimo Prescrito para las métricas clave:
    * #ACC EXPL y #DCC EXPL (Crítica en MD-4)
    * Distancia Total (km) (Crítica en MD-3)
    * HSR (m) y Metros en Sprint (Crítica en MD-2)
    Aplica el semáforo multivariable según el nivel objetivo (50%, 70%, 80% de partido o día del microciclo).
    """
    sess = db.query(TrainingSession).filter(TrainingSession.id == session_id, TrainingSession.club_id == club_id).first()
    if not sess:
        return pd.DataFrame()

    day = sess.microcycle_day.upper().strip()
    day_cfg = MICROCYCLE_MATCH_TARGETS.get(day, MICROCYCLE_MATCH_TARGETS.get("MD-3", {}))
    if custom_pcts:
        pct_td = float(custom_pcts.get("pct_td", float(level or 70)))
        pct_hsr = float(custom_pcts.get("pct_hsr", float(level or 70)))
        pct_sprint = float(custom_pcts.get("pct_sprint", float(level or 70)))
        pct_eff = float(custom_pcts.get("pct_eff", float(level or 70)))
    elif level is not None:
        pct_td = float(level)
        pct_hsr = float(level)
        pct_sprint = float(level)
        pct_eff = float(level)
    else:
        pct_td = float(day_cfg.get("pct_td", 0.80) * 100.0)
        pct_hsr = float(day_cfg.get("pct_hsr", 0.65) * 100.0)
        pct_sprint = float(day_cfg.get("pct_sprint", 0.50) * 100.0)
        pct_eff = float(day_cfg.get("pct_eff", 0.65) * 100.0)

    # 1. Obtener prescripción meta para el día
    presc = calculate_excel_pre_session_prescription(
        db, reference_session_id, day, pct_td, pct_hsr, pct_sprint, pct_eff, club_id=club_id
    )
    df_presc = presc.get("df_display", pd.DataFrame())
    if df_presc.empty:
        return pd.DataFrame()

    # Mapear objetivos por player_id
    target_by_player = {}
    for _, r in df_presc[df_presc["_row_type"] == "player"].iterrows():
        p_id = r["_player_id"]
        try:
            target_by_player[p_id] = {
                "min_td_km": float(r["DISTANCIA TOTAL (km)"]),
                "min_hsr": float(r["HSR (m)"]),
                "min_sprint_m": float(r["METROS EN SPRINT"]),
                "min_sprints": int(r["#SPRINTS"]),
                "min_acc": int(r["#ACC EXPL"]),
                "min_dec": int(r["#DCC EXPL"])
            }
        except Exception:
            pass

    # 2. Obtener métricas reales de la sesión
    real_metrics = (
        db.query(
            Player.id.label("player_id"),
            Player.dorsal,
            Player.name.label("player_name"),
            Player.position,
            PlayerMetric.total_distance,
            PlayerMetric.hsr_distance,
            PlayerMetric.sprint_distance,
            PlayerMetric.accelerations_eff,
            PlayerMetric.decelerations_eff,
            PlayerMetric.max_speed
        )
        .join(PlayerMetric, Player.id == PlayerMetric.player_id)
        .filter(PlayerMetric.session_id == session_id, Player.club_id == club_id)
        .order_by(Player.dorsal.asc())
        .all()
    )

    comparison_rows = []

    for m in real_metrics:
        p_id = m.player_id
        tgt = target_by_player.get(p_id)
        if not tgt:
            continue

        real_td_km = round((m.total_distance or 0.0) / 1000.0, 2)
        real_hsr = round(m.hsr_distance or 0.0, 1)
        raw_sp = float(m.sprint_distance or 0.0)
        if raw_sp <= 35.0:
            real_sprints = int(raw_sp)
            real_sprint_m = round(raw_sp * 18.0, 1)
        else:
            real_sprint_m = round(raw_sp, 1)
            real_sprints = max(1, int(round(raw_sp / 18.0))) if raw_sp > 0 else 0

        real_acc = int(m.accelerations_eff or 0)
        real_dec = int(m.decelerations_eff or 0)

        # Porcentajes de cumplimiento
        comp_td = (real_td_km / tgt["min_td_km"] * 100.0) if tgt["min_td_km"] > 0 else 0.0
        comp_hsr = (real_hsr / tgt["min_hsr"] * 100.0) if tgt["min_hsr"] > 0 else 0.0
        comp_sprint = (real_sprint_m / tgt["min_sprint_m"] * 100.0) if tgt["min_sprint_m"] > 0 else 0.0
        comp_acc = (real_acc / tgt["min_acc"] * 100.0) if tgt["min_acc"] > 0 else 0.0
        comp_dec = (real_dec / tgt["min_dec"] * 100.0) if tgt["min_dec"] > 0 else 0.0
        comp_eff = ((real_acc + real_dec) / (tgt["min_acc"] + tgt["min_dec"]) * 100.0) if (tgt["min_acc"] + tgt["min_dec"]) > 0 else 0.0

        # Diagnóstico de estímulo según la jerarquía metodológica del día de microciclo:
        # * MD-4: La métrica crítica es % AC.E (% ACC / % DCC), NO la distancia (% DT).
        # * MD-3: La métrica crítica es % DT.
        # * MD-2: La métrica crítica es % HSR y % Sprint.
        if day == "MD-4":
            crit_metric = "AC.E"
            comp_eval = comp_eff
        elif day == "MD-3":
            crit_metric = "DT"
            comp_eval = comp_td
        elif day == "MD-2":
            crit_metric = "HSR/Sprint"
            comp_eval = max(comp_hsr, comp_sprint) if comp_sprint > 0 else comp_hsr
        else:
            crit_metric = "DT"
            comp_eval = comp_td

        if level is not None:
            if comp_eval < 80.0:
                diag = f"🔴 Déficit {crit_metric} ({comp_eval:.0f}% de meta {level}%)"
                status = "Déficit"
                color_hex = "#EF4444"
            elif comp_eval > 115.0:
                diag = f"🟠 Sobre-estímulo {crit_metric} ({comp_eval:.0f}% de meta {level}%)"
                status = "Sobre-estímulo"
                color_hex = "#F59E0B"
            else:
                diag = f"🟢 Cumplido {crit_metric} ({comp_eval:.0f}%)"
                status = "Óptimo"
                color_hex = "#10B981"
        else:
            diag, status, color_hex, color_lbl = evaluate_multivariable_deficit(
                day, comp_td, comp_hsr, comp_eff
            )

        comparison_rows.append({
            "Dorsal": m.dorsal,
            "Jugador": f"#{m.dorsal} {m.player_name.upper()}",
            "Posición": m.position.upper(),
            # Distancia Total
            "DT Real (km)": real_td_km,
            "DT Meta (km)": tgt["min_td_km"],
            "% DT": round(comp_td, 1),
            # HSR
            "HSR Real (m)": real_hsr,
            "HSR Meta (m)": tgt["min_hsr"],
            "% HSR": round(comp_hsr, 1),
            # Sprint
            "Sprint Real (m)": real_sprint_m,
            "Sprint Meta (m)": tgt["min_sprint_m"],
            "% Sprint": round(comp_sprint, 1),
            # #ACC EXPL
            "ACC Real": real_acc,
            "ACC Meta": tgt["min_acc"],
            "% ACC": round(comp_acc, 1),
            # #DCC EXPL
            "DCC Real": real_dec,
            "DCC Meta": tgt["min_dec"],
            "% DCC": round(comp_dec, 1),
            # Diagnóstico
            "Diagnóstico de Estímulo": diag,
            "Estado": status,
            "Color": color_hex
        })

    return pd.DataFrame(comparison_rows)


def classify_session_player_states(
    db: Session,
    session_id: int,
    reference_session_id: Optional[int] = None,
    club_id: int = DEFAULT_CLUB_ID
) -> Dict[str, Any]:
    """
    Clasifica a los jugadores de la sesión en los 3 estados operativos definidos por el preparador físico:
    - ESTADO 1 (ROJO | DÉFICIT DE ESTÍMULO): <80% en la métrica diana del día.
      Muestra qué faltó cuantitativamente (ej: '#ACC EXPL: 48 de 72 requeridas (-33%)').
    - ESTADO 2 (VERDE | EN RANGO ÓPTIMO): 80% - 115% de la métrica diana.
    - ESTADO 3 (AMARILLO/NARANJA-ROJO | SOBRE-ESTÍMULO / RIESGO): >115% de la métrica prescrita (alerta fatiga).

    Aplica rigurosamente la jerarquía condicional de métricas:
    * MD-4: Métrica crítica = #ACC EXPL (#ACC/#DCC EXPL).
      El bajo volumen de carrera (DT o HSR) es fisiológicamente normal y deseable en espacios reducidos;
      no computa déficit.
    * MD-3: Métrica crítica = Distancia Total (DT).
    * MD-2: Métrica crítica = High Speed Running (HSR >21 km/h) y picos de velocidad.
    * MD-1 / MD+1: Métrica crítica = Distancia Total controlada (DT).
    """
    sess = db.query(TrainingSession).filter(
        TrainingSession.id == session_id,
        TrainingSession.club_id == club_id
    ).first()

    if not sess:
        return {
            "microcycle_day": "MD",
            "critical_metric": "total_distance",
            "critical_label": "Distancia Total",
            "secondary_note": "",
            "counts": {"deficit": 0, "optimal": 0, "excess": 0, "total": 0},
            "groups": {"deficit": [], "optimal": [], "excess": []},
            "players_summary": []
        }

    day = (sess.microcycle_day or "MD-3").upper().strip()
    day_cfg = MICROCYCLE_MATCH_TARGETS.get(day, MICROCYCLE_MATCH_TARGETS.get("MD-3", {}))
    pct_td = float(day_cfg.get("pct_td", 0.80) * 100.0)
    pct_hsr = float(day_cfg.get("pct_hsr", 0.65) * 100.0)
    pct_sprint = float(day_cfg.get("pct_sprint", 0.50) * 100.0)
    pct_eff = float(day_cfg.get("pct_eff", 0.65) * 100.0)

    # 1. Obtener prescripción meta para el día
    presc = calculate_excel_pre_session_prescription(
        db, reference_session_id, day, pct_td, pct_hsr, pct_sprint, pct_eff, club_id=club_id
    )
    df_presc = presc.get("df_display", pd.DataFrame())

    target_by_player = {}
    if not df_presc.empty:
        for _, r in df_presc[df_presc["_row_type"] == "player"].iterrows():
            p_id = r["_player_id"]
            try:
                target_by_player[p_id] = {
                    "min_td_km": float(r["DISTANCIA TOTAL (km)"]),
                    "min_hsr": float(r["HSR (m)"]),
                    "min_sprint_m": float(r["METROS EN SPRINT"]),
                    "min_sprints": int(r["#SPRINTS"]),
                    "min_acc": int(r["#ACC EXPL"]),
                    "min_dec": int(r["#DCC EXPL"])
                }
            except Exception:
                pass

    # 2. Obtener métricas reales registradas
    real_metrics = (
        db.query(
            Player.id.label("player_id"),
            Player.dorsal,
            Player.name.label("player_name"),
            Player.position,
            PlayerMetric.total_distance,
            PlayerMetric.hsr_distance,
            PlayerMetric.sprint_distance,
            PlayerMetric.accelerations_eff,
            PlayerMetric.decelerations_eff,
            PlayerMetric.max_speed,
            PlayerMetric.minutes_played
        )
        .join(PlayerMetric, Player.id == PlayerMetric.player_id)
        .filter(PlayerMetric.session_id == session_id, Player.club_id == club_id)
        .order_by(Player.dorsal.asc())
        .all()
    )

    # Definir métrica crítica y notas según el día
    if day == "MD-4":
        critical_metric = "accelerations_eff"
        critical_label = "#ACC EXPL"
        secondary_note = "En MD-4 el bajo volumen de carrera (DT/HSR) es normal y deseable en espacios reducidos para evitar fatiga residual."
    elif day == "MD-3":
        critical_metric = "total_distance"
        critical_label = "Distancia Total (DT)"
        secondary_note = "En MD-3 el objetivo táctico-condicional prioritario es el volumen total (resistencia en espacios amplios)."
    elif day == "MD-2":
        critical_metric = "hsr_distance"
        critical_label = "HSR (>21 km/h)"
        secondary_note = "En MD-2 la prioridad metodológica son los picos de alta velocidad (>21 km/h) y aceleraciones explosivas."
    elif day in ["MD-1", "MD+1", "MD+2"]:
        critical_metric = "total_distance"
        critical_label = "Distancia Total (DT)"
        secondary_note = f"Sesión de {('activación pre-partido' if day == 'MD-1' else 'compensación/recuperación')} con volumen controlado."
    else:
        critical_metric = "total_distance"
        critical_label = "Distancia Total (DT)"
        secondary_note = "Competición oficial / Máxima exigencia."

    deficit_group = []
    optimal_group = []
    excess_group = []
    all_summary = []

    for m in real_metrics:
        p_id = m.player_id
        tgt = target_by_player.get(p_id)
        if not tgt:
            continue

        real_td_km = round((m.total_distance or 0.0) / 1000.0, 2)
        real_hsr = round(m.hsr_distance or 0.0, 1)
        raw_sp = float(m.sprint_distance or 0.0)
        real_sprint_m = round(raw_sp if raw_sp > 35.0 else raw_sp * 18.0, 1)
        real_acc = int(m.accelerations_eff or 0)
        real_dec = int(m.decelerations_eff or 0)
        minutes = float(m.minutes_played or 0.0)

        # Si el jugador no entrenó o tiene 0 minutos y 0 distancia, omitir
        if minutes == 0 and real_td_km == 0:
            continue

        # Evaluación según la métrica crítica del día
        if day == "MD-4":
            real_val = real_acc
            tgt_val = tgt["min_acc"]
            comp_pct = (real_val / tgt_val * 100.0) if tgt_val > 0 else 100.0
            diff_abs = real_val - tgt_val
            diff_pct = comp_pct - 100.0
            unit = "req."
            detail_str = f"#ACC EXPL: {real_val} de {tgt_val} requeridas ({diff_pct:+.0f}%)"
            secondary_str = f"DT: {real_td_km:.2f} km (normal en MD-4) | DCC: {real_dec}/{tgt['min_dec']}"
        elif day == "MD-3":
            real_val = real_td_km
            tgt_val = tgt["min_td_km"]
            comp_pct = (real_val / tgt_val * 100.0) if tgt_val > 0 else 100.0
            diff_abs = round(real_val - tgt_val, 2)
            diff_pct = comp_pct - 100.0
            unit = "km"
            detail_str = f"DT: {real_val:.2f} de {tgt_val:.2f} km requeridos ({diff_pct:+.0f}%)"
            secondary_str = f"HSR: {real_hsr:.0f} m (meta {tgt['min_hsr']:.0f}) | #ACC: {real_acc}/{tgt['min_acc']}"
        elif day == "MD-2":
            real_val = real_hsr
            tgt_val = tgt["min_hsr"]
            comp_pct = (real_val / tgt_val * 100.0) if tgt_val > 0 else 100.0
            diff_abs = round(real_val - tgt_val, 1)
            diff_pct = comp_pct - 100.0
            unit = "m"
            detail_str = f"HSR: {real_val:.0f} de {tgt_val:.0f} m requeridos ({diff_pct:+.0f}%)"
            secondary_str = f"Sprint: {real_sprint_m:.0f} m (meta {tgt['min_sprint_m']:.0f}) | Vmax: {m.max_speed:.1f} km/h"
        else:
            real_val = real_td_km
            tgt_val = tgt["min_td_km"]
            comp_pct = (real_val / tgt_val * 100.0) if tgt_val > 0 else 100.0
            diff_abs = round(real_val - tgt_val, 2)
            diff_pct = comp_pct - 100.0
            unit = "km"
            detail_str = f"DT: {real_val:.2f} de {tgt_val:.2f} km ({diff_pct:+.0f}%)"
            secondary_str = f"HSR: {real_hsr:.0f} m | ACC: {real_acc}"

        item = {
            "player_id": p_id,
            "dorsal": m.dorsal,
            "name": m.player_name,
            "position": m.position,
            "real_val": real_val,
            "target_val": tgt_val,
            "comp_pct": round(comp_pct, 1),
            "diff_abs": diff_abs,
            "diff_pct": round(diff_pct, 1),
            "detail_str": detail_str,
            "secondary_str": secondary_str,
            "minutes": minutes,
            "unit": unit
        }

        # Clasificación en 3 Estados:
        # ESTADO 1: <80% (Déficit de estímulo)
        # ESTADO 2: 80% - 115% (En rango óptimo)
        # ESTADO 3: >115% (Sobre-estímulo / Riesgo fatiga)
        if comp_pct < 80.0:
            item["state"] = 1
            item["state_label"] = "Déficit de Estímulo (<80%)"
            item["badge_color"] = "#EF4444"
            item["badge_class"] = "deficit"
            deficit_group.append(item)
        elif comp_pct <= 115.0:
            item["state"] = 2
            item["state_label"] = "En Rango Óptimo (80-115%)"
            item["badge_color"] = "#10B981"
            item["badge_class"] = "optimal"
            optimal_group.append(item)
        else:
            item["state"] = 3
            item["state_label"] = "Sobre-estímulo / Riesgo (>115%)"
            item["badge_color"] = "#F59E0B"
            item["badge_class"] = "excess"
            excess_group.append(item)

        all_summary.append(item)

    return {
        "microcycle_day": day,
        "critical_metric": critical_metric,
        "critical_label": critical_label,
        "secondary_note": secondary_note,
        "counts": {
            "deficit": len(deficit_group),
            "optimal": len(optimal_group),
            "excess": len(excess_group),
            "total": len(all_summary)
        },
        "groups": {
            "deficit": deficit_group,
            "optimal": optimal_group,
            "excess": excess_group
        },
        "players_summary": all_summary
    }


# ==============================================================================
# 9. INFORME SEMANAL PARA EL PRIMER ENTRENADOR (AGRUPACIÓN POR MICROCICLOS)
# ==============================================================================

def get_available_microcycles(db: Session, club_id: int = DEFAULT_CLUB_ID) -> List[Dict[str, Any]]:
    """
    Detecta y agrupa los microciclos competitivos de la temporada a partir de los partidos oficiales de Liga:
    Cada microciclo abarca desde el día posterior al partido anterior (MD+1/MD-4) hasta el día de partido (MD).
    """
    all_sessions = (
        db.query(TrainingSession)
        .filter(TrainingSession.club_id == club_id)
        .order_by(TrainingSession.date.asc())
        .all()
    )
    if not all_sessions:
        return []

    matches = [s for s in all_sessions if is_official_league_match(s)]
    
    # Desduplicar partidos por fecha (para evitar duplicados por re-importaciones)
    unique_matches_by_date = {}
    for m in matches:
        if m.date not in unique_matches_by_date or m.id > unique_matches_by_date[m.date].id:
            unique_matches_by_date[m.date] = m
    unique_matches = sorted(unique_matches_by_date.values(), key=lambda x: x.date)

    microcycles = []
    for idx, match in enumerate(unique_matches):
        if idx > 0:
            start_date = unique_matches[idx - 1].date + timedelta(days=1)
        else:
            start_date = match.date - timedelta(days=6)
        end_date = match.date

        rival = "Partido Oficial"
        name_clean = (match.name or "").replace("Partido fútbol 11'", "").replace("Partido futbol 11'", "")
        if "contra" in name_clean.lower():
            rival = name_clean.lower().split("contra")[-1].replace("_total", "").split("_")[0].strip().title()
        else:
            rival = name_clean.strip() or "Competición"

        lbl = f"Microciclo vs {rival} ({start_date.strftime('%d/%m')} - {end_date.strftime('%d/%m/%Y')})"
        microcycles.append({
            "id": f"micro_{match.id}",
            "label": lbl,
            "start_date": start_date,
            "end_date": end_date,
            "match_name": match.name,
            "match_id": match.id,
            "rival": rival
        })

    # Ordenar los microciclos del más reciente al más antiguo para comodidad del cuerpo técnico
    microcycles.reverse()

    # Añadir opción de últimos 7 días como comodín dinámico
    today = date.today()
    microcycles.append({
        "id": "last_7_days",
        "label": f"📅 Últimos 7 Días ({ (today - timedelta(days=6)).strftime('%d/%m') } - { today.strftime('%d/%m/%Y') })",
        "start_date": today - timedelta(days=6),
        "end_date": today,
        "match_name": "Ventana Móvil 7 Días",
        "match_id": None,
        "rival": "Ventana Reciente"
    })

    return microcycles


def get_weekly_microcycle_summary(
    db: Session,
    start_date: date,
    end_date: date,
    club_id: int = DEFAULT_CLUB_ID
) -> Dict[str, Any]:
    """
    Genera el desglose completo del microciclo semanal para el Primer Entrenador:
    1. Resumen del Microciclo: Estímulo principal planificado vs. carga total acumulada (DT, HSR, AC.E y desglose diario).
    2. Futbolistas en Estado Óptimo: Cumplieron metas sin sobrecarga (ACWR 0.8 - 1.3).
    3. Futbolistas en Déficit de Estímulo: Suplentes / No convocados / Subentrenados con propuesta de compensatorio pre/post partido.
    4. Alertas de Fatiga y Riesgo Lesional: Jugadores con fatiga crítica (ACWR > 1.35 o picos agudos) con recomendaciones tácticas.
    """
    sessions = (
        db.query(TrainingSession)
        .filter(
            TrainingSession.club_id == club_id,
            TrainingSession.date >= start_date,
            TrainingSession.date <= end_date
        )
        .order_by(TrainingSession.date.asc(), TrainingSession.id.asc())
        .all()
    )

    if not sessions:
        return {
            "start_date": start_date,
            "end_date": end_date,
            "sessions_count": 0,
            "sessions_breakdown": [],
            "team_kpis": {},
            "optimal_players": [],
            "deficit_players": [],
            "fatigue_alerts": [],
            "all_players": []
        }

    # Desduplicar sesiones por (date, microcycle_day) para evitar duplicación de cargas si un CSV se importó 2 veces
    sessions_by_day = {}
    for s in sessions:
        key = (s.date, s.microcycle_day)
        if key not in sessions_by_day or s.id > sessions_by_day[key].id:
            sessions_by_day[key] = s
    unique_sessions = sorted(sessions_by_day.values(), key=lambda x: x.date)

    # 1. ACWR al corte del microciclo (usando end_date)
    df_acwr = get_latest_player_acwr(db, target_date=end_date, club_id=club_id)
    acwr_by_player = {}
    if not df_acwr.empty:
        for _, r in df_acwr.iterrows():
            acwr_by_player[r["player_id"]] = {
                "acwr": r["acwr"],
                "status": r["acwr_status"],
                "color": r["acwr_color"],
                "acute": r.get("acute_load", 0.0),
                "chronic": r.get("chronic_load", 0.0)
            }

    # 2. Desglose de cada sesión del microciclo y cálculo de KPIs de equipo
    sessions_breakdown = []
    tot_team_td_m = 0.0
    tot_team_hsr_m = 0.0
    tot_team_eff = 0
    tot_team_duration = 0

    p_stats = defaultdict(lambda: {
        "td_m": 0.0, "hsr_m": 0.0, "sprint_m": 0.0,
        "acc": 0, "dec": 0, "eff": 0, "mins": 0.0,
        "sessions_count": 0, "played_match": False, "match_mins": 0.0
    })

    for s in unique_sessions:
        mets = db.query(PlayerMetric).filter(PlayerMetric.session_id == s.id).all()
        is_match = (s.session_type == "Partido" or s.microcycle_day == "MD")
        n_p = len(mets)
        mean_td = (sum((m.total_distance or 0.0) for m in mets) / n_p) if n_p > 0 else 0.0
        mean_hsr = (sum((m.hsr_distance or 0.0) for m in mets) / n_p) if n_p > 0 else 0.0
        mean_eff = (sum(((m.accelerations_eff or 0) + (m.decelerations_eff or 0)) for m in mets) / n_p) if n_p > 0 else 0.0
        dur = s.duration_minutes or (90 if is_match else 75)

        tot_team_td_m += mean_td
        tot_team_hsr_m += mean_hsr
        tot_team_eff += int(mean_eff)
        tot_team_duration += dur

        day_str = s.microcycle_day.upper().strip() if s.microcycle_day else ""
        if day_str == "MD-4":
            stimulus = "⚡ Tensión Neuromuscular y Espacios Reducidos (AC.E y aceleraciones cortas)"
            planned_foco = "Carga neuromuscular alta / Volumen controlado"
        elif day_str == "MD-3":
            stimulus = "🏃 Resistencia y Volumen Competitivo (Distancia Total y capacidad aeróbica)"
            planned_foco = "Pico de volumen semanal (DT) en espacios amplios"
        elif day_str == "MD-2":
            stimulus = "🚀 Velocidad y Reactividad Neuromuscular (HSR >21 km/h y Sprint)"
            planned_foco = "Estimulación de alta velocidad y activación táctica"
        elif day_str == "MD-1":
            stimulus = "🎯 Activación Prepartido y Balón Parado (Volumen reducido)"
            planned_foco = "Sesión corta, baja fatiga residual y pelota parada"
        elif day_str in ["MD+1", "MD+2"]:
            stimulus = "🔄 Recuperación activa titulares / Compensatorio no titulares"
            planned_foco = "Regeneración metabólica y compensación para suplentes"
        elif is_match:
            stimulus = "🏟️ Competición Oficial de Liga (100% Exigencia)"
            planned_foco = "Máxima exigencia individual y competitiva"
        else:
            stimulus = "⚽ Entrenamiento General"
            planned_foco = "Trabajo técnico-táctico coordinado"

        sessions_breakdown.append({
            "session_id": s.id,
            "date": s.date,
            "microcycle_day": s.microcycle_day,
            "session_type": s.session_type,
            "name": s.name,
            "duration": dur,
            "players_count": n_p,
            "mean_td_m": round(mean_td, 1),
            "mean_td_km": round(mean_td / 1000.0, 2),
            "mean_hsr_m": round(mean_hsr, 1),
            "mean_eff": round(mean_eff, 1),
            "stimulus": stimulus,
            "planned_foco": planned_foco
        })

        for m in mets:
            pid = m.player_id
            td = float(m.total_distance or 0.0)
            hsr = float(m.hsr_distance or 0.0)
            raw_sp = float(m.sprint_distance or 0.0)
            sp_m = round(raw_sp * 18.0, 1) if raw_sp <= 35.0 else round(raw_sp, 1)
            acc_c = int(m.accelerations_eff or 0)
            dec_c = int(m.decelerations_eff or 0)
            mins_c = float(m.minutes_played or 0.0)

            p_stats[pid]["td_m"] += td
            p_stats[pid]["hsr_m"] += hsr
            p_stats[pid]["sprint_m"] += sp_m
            p_stats[pid]["acc"] += acc_c
            p_stats[pid]["dec"] += dec_c
            p_stats[pid]["eff"] += (acc_c + dec_c)
            p_stats[pid]["mins"] += mins_c
            p_stats[pid]["sessions_count"] += 1
            if is_match and mins_c > 0:
                p_stats[pid]["played_match"] = True
                p_stats[pid]["match_mins"] = max(p_stats[pid]["match_mins"], mins_c)

    # 3. Categorización de Futbolistas
    players = (
        db.query(Player)
        .filter(Player.club_id == club_id, Player.active == True)
        .order_by(Player.dorsal.asc())
        .all()
    )

    optimal_players = []
    deficit_players = []
    fatigue_alerts = []
    all_players_summary = []

    for p in players:
        pos_norm = p.position.upper().strip() if p.position else ""
        if pos_norm == "PORTERO":
            continue

        st_data = p_stats[p.id]
        acwr_info = acwr_by_player.get(p.id, {"acwr": None, "status": "Sin datos", "color": "#9E9E9E"})
        acwr_val = acwr_info.get("acwr")

        tot_km = round(st_data["td_m"] / 1000.0, 2)
        tot_hsr = round(st_data["hsr_m"], 1)
        tot_sprint = round(st_data["sprint_m"], 1)
        tot_eff = st_data["eff"]
        tot_mins = round(st_data["mins"], 1)
        sess_cnt = st_data["sessions_count"]
        match_played = st_data["played_match"]
        match_mins = round(st_data["match_mins"], 1)

        p_card = {
            "player_id": p.id,
            "dorsal": p.dorsal,
            "name": p.name,
            "position": pos_norm,
            "tot_km": tot_km,
            "tot_hsr": tot_hsr,
            "tot_sprint": tot_sprint,
            "tot_eff": tot_eff,
            "tot_mins": tot_mins,
            "sessions_count": sess_cnt,
            "played_match": match_played,
            "match_mins": match_mins,
            "acwr": round(acwr_val, 2) if acwr_val is not None else None,
            "acwr_status": acwr_info.get("status"),
            "acwr_color": acwr_info.get("color")
        }

        # CLASIFICACIÓN RIGUROSA DE RENDIMIENTO DEPORTIVO:
        # A) ALERTA DE FATIGA Y RIESGO LESIONAL:
        # ACWR > 1.35 o sobrecarga mecánica extrema (AC.E muy elevado)
        if (acwr_val is not None and acwr_val > 1.35) or (tot_eff > 680 and tot_mins > 380):
            reasons = []
            if acwr_val is not None and acwr_val > 1.50:
                reasons.append(f"ACWR Crítico ({acwr_val:.2f} > 1.50 - Riesgo Alto de Sobrecarga)")
            elif acwr_val is not None and acwr_val > 1.35:
                reasons.append(f"ACWR en Precaución ({acwr_val:.2f} > 1.35 - Fatiga Acumulada)")
            if tot_eff > 680:
                reasons.append(f"Pico agudo de carga mecánica ({tot_eff} AC.E totales)")
            if tot_mins > 420:
                reasons.append(f"Alto minutaje competitivo ({tot_mins:.0f}' acumulados)")

            p_card["alert_reasons"] = " • ".join(reasons)
            p_card["recommendation"] = (
                "⚠️ RECOMENDACIÓN TÁCTICA: Ajustar minutaje en el partido (máx. 45-60 min) o programar descanso "
                "activo con descarga neuromuscular. En MD-1 suprimir tareas de finalización con frenada máxima."
            )
            p_card["category"] = "Alerta de Fatiga"
            p_card["badge_color"] = "#EF4444"
            fatigue_alerts.append(p_card)

        # B) DÉFICIT DE ESTÍMULO (Subentrenamiento / Suplentes / No convocados):
        elif tot_mins < 120.0 or sess_cnt <= 2 or (acwr_val is not None and acwr_val < 0.80):
            def_reasons = []
            if not match_played or match_mins < 30:
                def_reasons.append(f"Suplente con {match_mins:.0f}' de competición")
            if tot_mins < 120:
                def_reasons.append(f"Minutaje semanal bajo ({tot_mins:.0f}' acumulados)")
            if acwr_val is not None and acwr_val < 0.80:
                def_reasons.append(f"ACWR bajo ({acwr_val:.2f} < 0.80 - Riesgo de desadaptación)")

            p_card["deficit_reasons"] = " • ".join(def_reasons)
            p_card["compensatory_plan"] = (
                "📋 COMPENSATORIO SUGERIDO: 4 series de 80m fraccionadas a >21 km/h (HSR) + rondo dinámico "
                "de posesión 4v4 en espacio reducido (8-10 min) para completar la carga fisiológica semanal."
            )
            p_card["category"] = "Déficit de Estímulo"
            p_card["badge_color"] = "#3B82F6"
            deficit_players.append(p_card)

        # C) ESTADO ÓPTIMO:
        else:
            p_card["optimal_note"] = "En ventana óptima de rendimiento (Sweet Spot 0.80 - 1.30). Cumplió metas sin sobrecarga. Listo para competir al 100%."
            p_card["category"] = "Estado Óptimo"
            p_card["badge_color"] = "#10B981"
            optimal_players.append(p_card)

        all_players_summary.append(p_card)

    team_kpis = {
        "num_sessions": len(unique_sessions),
        "total_team_duration": tot_team_duration,
        "team_mean_distance_km": round(tot_team_td_m / 1000.0, 2),
        "team_mean_hsr_m": round(tot_team_hsr_m, 1),
        "team_mean_eff": tot_team_eff,
        "players_monitored": len(all_players_summary),
        "optimal_count": len(optimal_players),
        "deficit_count": len(deficit_players),
        "fatigue_count": len(fatigue_alerts)
    }

    return {
        "start_date": start_date,
        "end_date": end_date,
        "sessions_breakdown": sessions_breakdown,
        "team_kpis": team_kpis,
        "optimal_players": optimal_players,
        "deficit_players": deficit_players,
        "fatigue_alerts": fatigue_alerts,
        "all_players": all_players_summary
    }




