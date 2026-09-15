"""
Módulo analítico de ciencias del deporte aplicadas al fútbol.
Implementa:
- ACWR mediante EWMA (Exponentially Weighted Moving Average) según Williams et al. (2017) y Gabbett (2016).
- Partido de Máxima Exigencia (Carga 100% Dinámica Individual): Actualización automática de techos individuales.
- Prescripción y % de Cumplimiento individual respecto al 100% del partido según el día del microciclo (MD-4 a MD-1).
- Z-scores normalizados por demarcación táctica y tipo de microciclo.
- Sistema de semáforos ejecutivos: Estado de fatiga (ACWR) y Semáforo de Cumplimiento del Día.
"""

from datetime import date, datetime
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
        # Métrica crítica del día de tensión: AC.E (aceleraciones y desaceleraciones > 3 m/s²)
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
            if comp_pct_td < 75.0:
                return (
                    f"🟡 AC.E Óptimo ({comp_pct_eff:.0f}%) | Déficit DT ({comp_pct_td:.0f}%)",
                    "Déficit secundario DT",
                    "#FBBF24",
                    "Amarillo"
                )
            return (
                f"🟢 Estímulo Óptimo Cumplido (AC.E: {comp_pct_eff:.0f}%)",
                "Cumplido",
                "#10B981",
                "Verde"
            )

    elif day == "MD-3":
        # Métrica crítica del día de resistencia: DT (volumen total)
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
            if comp_pct_hsr < 70.0:
                return (
                    f"🟡 Volumen Óptimo ({comp_pct_td:.0f}%) | Déficit HSR ({comp_pct_hsr:.0f}%)",
                    "Déficit secundario HSR",
                    "#FBBF24",
                    "Amarillo"
                )
            return (
                f"🟢 Estímulo Óptimo Cumplido (DT: {comp_pct_td:.0f}%)",
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

    elif day == "MD+1":
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


# ==============================================================================
# 1. GESTIÓN DEL "PARTIDO DE MÁXIMA EXIGENCIA" (CARGA 100% DINÁMICA INDIVIDUAL)
# ==============================================================================

def sync_and_update_player_match_peaks(db: Session, club_id: int = DEFAULT_CLUB_ID) -> Dict[str, Any]:
    """
    Examina todos los partidos oficiales (session_type='Partido' o microcycle_day='MD') registrados en el club.
    Para cada jugador:
    1. Localiza sus valores máximos alcanzados en partido (DT, HSR, Sprint, HMLD, AC.E, Vmax).
    2. Si en semanas posteriores un nuevo partido supera esos máximos, actualiza automáticamente
       ese nuevo techo del 100% en la tabla `player_match_peaks`.
    3. Si el jugador aún no tiene partidos registrados, inicializa techos basados en sus referencias
       posicionales estándar para que el cálculo nunca quede en blanco.
    """
    players = db.query(Player).filter(Player.club_id == club_id, Player.active == True).all()

    # Partidos del club ordenados cronológicamente
    matches = (
        db.query(TrainingSession)
        .filter(
            TrainingSession.club_id == club_id,
            (TrainingSession.session_type == "Partido") | (TrainingSession.microcycle_day == "MD")
        )
        .order_by(TrainingSession.date.asc())
        .all()
    )

    match_ids = [m.id for m in matches]
    match_dict = {m.id: m for m in matches}

    updated_count = 0
    created_count = 0

    for p in players:
        current_peak = (
            db.query(PlayerMatchPeak)
            .filter(PlayerMatchPeak.club_id == club_id, PlayerMatchPeak.player_id == p.id)
            .first()
        )

        # Buscar métricas de partidos para este jugador
        if match_ids:
            p_metrics = (
                db.query(PlayerMetric)
                .filter(
                    PlayerMetric.player_id == p.id,
                    PlayerMetric.session_id.in_(match_ids)
                )
                .all()
            )
        else:
            p_metrics = []

        if p_metrics:
            # Encontrar el partido con mayor distancia total o esfuerzo
            best_td_metric = max(p_metrics, key=lambda m: (m.total_distance or 0.0))
            best_session = match_dict.get(best_td_metric.session_id)

            max_td = max(float(m.total_distance or 0.0) for m in p_metrics)
            max_hsr = max(float(m.hsr_distance or 0.0) for m in p_metrics)
            max_sprint = max(float(m.sprint_distance or 0.0) for m in p_metrics)
            max_hmld = max(float(m.hmld or 0.0) for m in p_metrics)
            max_acc = max(int(m.accelerations_eff or 0) for m in p_metrics)
            max_dec = max(int(m.decelerations_eff or 0) for m in p_metrics)
            max_vmax = max(float(m.max_speed or 0.0) for m in p_metrics)

            # Validar que no sean ceros (ej. si fue suplente sin minutos)
            if max_td < 3000.0:
                max_td = 10500.0
            if max_hsr < 100.0:
                max_hsr = 650.0
            if max_hmld < 500.0:
                max_hmld = 1800.0
            if (max_acc + max_dec) < 20:
                max_acc, max_dec = 40, 40

            sess_name = best_session.name if best_session else "Partido de Competición"
            sess_date = best_session.date if best_session else date.today()

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
                    peak_max_speed=max(max_vmax, p.max_speed_kmh or 32.0),
                    peak_session_name=sess_name,
                    peak_session_date=sess_date,
                    last_updated=datetime.utcnow()
                )
                db.add(new_peak)
                created_count += 1
            else:
                # Actualizar si algún nuevo partido superó techos
                has_increase = False
                if max_td > current_peak.peak_td:
                    current_peak.peak_td = max_td
                    has_increase = True
                if max_hsr > current_peak.peak_hsr:
                    current_peak.peak_hsr = max_hsr
                    has_increase = True
                if max_sprint > current_peak.peak_sprint:
                    current_peak.peak_sprint = max_sprint
                    has_increase = True
                if max_hmld > current_peak.peak_hmld:
                    current_peak.peak_hmld = max_hmld
                    has_increase = True
                if max_acc > current_peak.peak_acc_eff:
                    current_peak.peak_acc_eff = max_acc
                    has_increase = True
                if max_dec > current_peak.peak_dec_eff:
                    current_peak.peak_dec_eff = max_dec
                    has_increase = True
                if max_vmax > current_peak.peak_max_speed:
                    current_peak.peak_max_speed = max_vmax
                    has_increase = True

                if has_increase:
                    current_peak.peak_session_name = sess_name
                    current_peak.peak_session_date = sess_date
                    current_peak.last_updated = datetime.utcnow()
                    updated_count += 1
        else:
            # Jugador sin partidos disputados: asignar estándar posicional de MD
            if not current_peak:
                # Estándar por demarcación
                pos_std = {
                    "Central": (9800.0, 480.0, 150.0, 1600.0, 45, 48),
                    "Lateral": (11200.0, 1050.0, 320.0, 2200.0, 60, 65),
                    "Mediocentro": (12100.0, 750.0, 210.0, 2400.0, 55, 58),
                    "Extremo": (10900.0, 1180.0, 380.0, 2300.0, 65, 70),
                    "Delantero": (10400.0, 880.0, 280.0, 1950.0, 52, 55),
                    "Portero": (5200.0, 80.0, 20.0, 750.0, 30, 30)
                }.get(p.position, (10500.0, 700.0, 200.0, 2000.0, 45, 45))

                new_peak = PlayerMatchPeak(
                    club_id=club_id,
                    player_id=p.id,
                    peak_td=pos_std[0],
                    peak_hsr=pos_std[1],
                    peak_sprint=pos_std[2],
                    peak_hmld=pos_std[3],
                    peak_acc_eff=pos_std[4],
                    peak_dec_eff=pos_std[5],
                    peak_max_speed=p.max_speed_kmh or 32.0,
                    peak_session_name="Referencia Posicional Estándar (MD 100%)",
                    peak_session_date=None,
                    last_updated=datetime.utcnow()
                )
                db.add(new_peak)
                created_count += 1

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

    # Asegurar que los picos del partido estén sincronizados
    sync_and_update_player_match_peaks(db, club_id=club_id)

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
        peak = get_player_match_peak(db, m.player_id, club_id=club_id)
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
    sync_and_update_player_match_peaks(db, club_id=club_id)

    players = (
        db.query(Player)
        .filter(Player.club_id == club_id, Player.active == True)
        .order_by(Player.dorsal.asc())
        .all()
    )

    rows = []
    for p in players:
        peak = get_player_match_peak(db, p.id, club_id=club_id)
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
    """
    players = session.query(Player).filter(Player.club_id == club_id, Player.active == True).all()
    records = []

    for p in players:
        df_acwr = calculate_ewma_acwr(session, p.id, load_metric="total_distance", club_id=club_id)
        if df_acwr.empty:
            continue

        if target_date:
            df_sub = df_acwr[df_acwr["date"].dt.date <= target_date]
            if df_sub.empty:
                continue
            last_row = df_sub.iloc[-1]
        else:
            last_row = df_acwr.iloc[-1]

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
    else:
        df_metrics["compliance_pct"] = 100.0

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

def get_all_reference_matches(db: Session, club_id: int = DEFAULT_CLUB_ID) -> List[Dict[str, Any]]:
    """
    Recupera todos los partidos oficiales registrados en el club (session_type='Partido' o microcycle_day='MD').
    Retorna la lista estructurada para alimentar el selector de bloques de partido:
    'PARTIDO 1 MIJAS COSTA', 'PARTIDO 2 RECREATIVO DE HUELVA', etc.,
    además del bloque virtual 'MÁXIMOS INDIVIDUALES CONSOLIDADOS (100% DINÁMICO)'.
    """
    matches = (
        db.query(TrainingSession)
        .filter(
            TrainingSession.club_id == club_id,
            (TrainingSession.session_type == "Partido") | (TrainingSession.microcycle_day == "MD")
        )
        .order_by(TrainingSession.date.asc())
        .all()
    )

    res: List[Dict[str, Any]] = []

    # Opción 0: Techo individual dinámico consolidado
    res.append({
        "session_id": None,
        "key": "PEAK_CONSOLIDATED",
        "order": 0,
        "name": "Partido Récord Consolidado (100% Techo Individual)",
        "label": "🏆 PARTIDO RÉCORD CONSOLIDADO (100% Individual por Jugador)",
        "date": date.today(),
        "num_players": db.query(Player).filter(Player.club_id == club_id, Player.active == True).count(),
        "total_distance_km": 0.0
    })

    for idx, m in enumerate(matches, 1):
        p_count = db.query(PlayerMetric).filter(PlayerMetric.session_id == m.id).count()
        tot_dist_m = db.query(func.sum(PlayerMetric.total_distance)).filter(PlayerMetric.session_id == m.id).scalar() or 0.0

        clean_name = m.name.upper()
        if "MIJAS" in clean_name:
            label_prefix = f"PARTIDO {idx} - CP MIJAS LAS LAGUNAS"
        elif "RECREATIVO" in clean_name or "HUELVA" in clean_name:
            label_prefix = f"PARTIDO {idx} - RECREATIVO DE HUELVA"
        else:
            label_prefix = f"PARTIDO {idx} - {m.name}"

        res.append({
            "session_id": m.id,
            "key": f"MATCH_{m.id}",
            "order": idx,
            "name": m.name,
            "label": f"🏟️ {label_prefix} ({m.date.strftime('%d/%m/%Y')})",
            "date": m.date,
            "num_players": p_count,
            "total_distance_km": round(tot_dist_m / 1000.0, 2)
        })

    return res


def get_match_reference_table_data(
    db: Session,
    session_id: Optional[int] = None,
    club_id: int = DEFAULT_CLUB_ID
) -> Dict[str, Any]:
    """
    Genera la tabla de referencia de datos de partido idéntica al formato Excel del preparador físico:
    - Columnas exactas:
      [POSICIÓN | JUGADOR | TIEMPO | DISTANCIA TOTAL (km) | VELOCIDAD MAX (km/h) | HSR (m) | METROS EN SPRINT | #SPRINTS | #ACC EXPL | #DCC EXPL]
    - Filas estructuradas por bloque posicional:
      * JUGADOR TOP (Fila destacada con fondo rojo suave: mayor rendimiento global)
      * CENTRAL (ej. Ginés)
      * LATERAL (ej. Rafa / Manu Viana)
      * MEDIOCENTRO (ej. Lalo)
      * EXTREMO (ej. Cellou)
      * DELANTERO (ej. Salva)
    - Fila inferior de resumen (Fondo azul distintivo):
      'DATOS REFERENCIA GENERALES EQUIPO' mostrando tiempo medio, distancia acumulada en KM,
      pico de velocidad máxima, total HSR acumulado y total de sprints.
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
                Player.id.label("player_id"),
                Player.dorsal,
                Player.name.label("player_name"),
                Player.position,
                PlayerMetric.minutes_played,
                PlayerMetric.total_distance,
                PlayerMetric.max_speed,
                PlayerMetric.hsr_distance,
                PlayerMetric.sprint_distance,
                PlayerMetric.accelerations_eff,
                PlayerMetric.decelerations_eff
            )
            .join(PlayerMetric, Player.id == PlayerMetric.player_id)
            .filter(PlayerMetric.session_id == session_id, Player.club_id == club_id)
            .all()
        )

        for m in metrics:
            pos_norm = m.position.upper().strip()
            # Porteros habitualmente no llevan chip GPS en campo
            if pos_norm == "PORTERO":
                continue

            td_m = float(m.total_distance or 0.0)
            hsr_m = float(m.hsr_distance or 0.0)
            vmax = float(m.max_speed or 0.0)
            mins = float(m.minutes_played or 90.0)
            acc = int(m.accelerations_eff or 0)
            dec = int(m.decelerations_eff or 0)

            raw_sp = float(m.sprint_distance or 0.0)
            if raw_sp <= 35.0:
                sprints_cnt = int(raw_sp)
                sprint_m = round(raw_sp * 18.0, 1)
            else:
                sprint_m = round(raw_sp, 1)
                sprints_cnt = max(1, int(round(raw_sp / 18.0))) if raw_sp > 0 else 0

            # Índice de rendimiento físico ponderado (Score de Exigencia Competitiva)
            # Combina volumen (DT), alta velocidad (HSR + Sprint) y carga neuromuscular (ACC + DEC)
            perf_score = (
                (td_m / 10000.0) * 0.25 +
                (hsr_m / 350.0) * 0.25 +
                (sprint_m / 150.0) * 0.20 +
                ((acc + dec) / 150.0) * 0.30
            )

            players_data.append({
                "player_id": m.player_id,
                "dorsal": m.dorsal,
                "player_name": m.player_name,
                "position_raw": m.position,
                "position": pos_norm,
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
                PlayerMatchPeak.peak_max_speed
            )
            .join(PlayerMatchPeak, Player.id == PlayerMatchPeak.player_id)
            .filter(Player.club_id == club_id, Player.active == True)
            .all()
        )

        for p in peaks:
            pos_norm = p.position.upper().strip()
            if pos_norm == "PORTERO":
                continue

            td_m = float(p.peak_td or 10500.0)
            hsr_m = float(p.peak_hsr or 600.0)
            vmax = float(p.peak_max_speed or 32.0)
            acc = int(p.peak_acc_eff or 45)
            dec = int(p.peak_dec_eff or 45)
            raw_sp = float(p.peak_sprint or 150.0)

            if raw_sp <= 35.0:
                sprints_cnt = int(raw_sp)
                sprint_m = round(raw_sp * 18.0, 1)
            else:
                sprint_m = round(raw_sp, 1)
                sprints_cnt = max(1, int(round(raw_sp / 18.0))) if raw_sp > 0 else 0

            perf_score = (
                (td_m / 10000.0) * 0.25 +
                (hsr_m / 350.0) * 0.25 +
                (sprint_m / 150.0) * 0.20 +
                ((acc + dec) / 150.0) * 0.30
            )

            players_data.append({
                "player_id": p.player_id,
                "dorsal": p.dorsal,
                "player_name": p.player_name,
                "position_raw": p.position,
                "position": pos_norm,
                "minutes": 90.0,
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
            "df_raw": pd.DataFrame(),
            "top_player": None,
            "team_summary": {}
        }

    # 1. Localizar al JUGADOR TOP (mayor rendimiento global de la sesión)
    top_player_item = max(players_data, key=lambda x: x["perf_score"])
    top_player_id = top_player_item["player_id"]

    # 2. Ordenar por Bloque Posicional y dorsal
    players_sorted = sorted(
        players_data,
        key=lambda x: (pos_order.get(x["position"], 99), x["dorsal"])
    )

    # 3. Construir la estructura exacta del Excel del club
    table_rows = []

    # Fila destacada superior: JUGADOR TOP
    table_rows.append({
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
        "_player_id": top_player_id
    })

    # Filas por bloque posicional
    for p in players_sorted:
        is_top = p["player_id"] == top_player_id
        table_rows.append({
            "POSICIÓN": p["position"],
            "JUGADOR": f"#{p['dorsal']} {p['player_name'].upper()}",
            "TIEMPO": f"{p['minutes']:.0f}'",
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

    # Cálculos globales del equipo para la fila inferior
    team_mean_time = float(np.mean([p["minutes"] for p in players_data]))
    team_tot_dist_km = float(np.sum([p["distance_km"] for p in players_data]))
    team_peak_speed = float(np.max([p["max_speed"] for p in players_data]))
    team_tot_hsr = float(np.sum([p["hsr_m"] for p in players_data]))
    team_tot_sprint_m = float(np.sum([p["sprint_m"] for p in players_data]))
    team_tot_sprints = int(np.sum([p["sprints_cnt"] for p in players_data]))
    team_tot_acc = int(np.sum([p["acc_expl"] for p in players_data]))
    team_tot_dec = int(np.sum([p["dcc_expl"] for p in players_data]))

    # Fila inferior de resumen con fondo azul distintivo
    table_rows.append({
        "POSICIÓN": "EQUIPO",
        "JUGADOR": "DATOS REFERENCIA GENERALES EQUIPO",
        "TIEMPO": f"{team_mean_time:.0f}' (Media)",
        "DISTANCIA TOTAL (km)": f"{team_tot_dist_km:.2f} KM",
        "VELOCIDAD MAX (km/h)": f"{team_peak_speed:.2f} KM/H",
        "HSR (m)": f"{team_tot_hsr:.0f} m",
        "METROS EN SPRINT": f"{team_tot_sprint_m:.0f} m",
        "#SPRINTS": str(team_tot_sprints),
        "#ACC EXPL": str(team_tot_acc),
        "#DCC EXPL": str(team_tot_dec),
        "_row_type": "team",
        "_player_id": 0
    })

    df_display = pd.DataFrame(table_rows)

    team_summary = {
        "num_players": len(players_data),
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
        "df_raw": pd.DataFrame(players_data),
        "top_player": top_player_item,
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

    for p in players_sorted:
        min_dist_km = round(p["distance_km"] * (pct_td / 100.0), 2)
        min_hsr = round(p["hsr_m"] * (pct_hsr / 100.0), 1)
        min_sprint_m = round(p["sprint_m"] * (pct_sprint / 100.0), 1)
        min_sprints = max(1, int(round(p["sprints_cnt"] * (pct_sprint / 100.0)))) if p["sprints_cnt"] > 0 else 0
        min_acc = max(1, int(round(p["acc_expl"] * (pct_eff / 100.0)))) if p["acc_expl"] > 0 else 0
        min_dec = max(1, int(round(p["dcc_expl"] * (pct_eff / 100.0)))) if p["dcc_expl"] > 0 else 0
        # Velocidad pico objetivo: 85-90% de su velocidad punta en partido
        target_vmax = round(p["max_speed"] * 0.88, 2)

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
    club_id: int = DEFAULT_CLUB_ID
) -> pd.DataFrame:
    """
    Genera la tabla comparativa post-sesión de UBIKO:
    Contrasta Valor Real vs. Mínimo Prescrito para las métricas clave:
    * #ACC EXPL y #DCC EXPL (Crítica en MD-4)
    * Distancia Total (km) (Crítica en MD-3)
    * HSR (m) y Metros en Sprint (Crítica en MD-2)
    Aplica el semáforo multivariable:
    - <80%: 🔴 Déficit [Métrica]
    - 80%-110%: 🟢 Óptimo
    - >115%: 🟠 Sobrecarga / Sobre-estímulo
    """
    sess = db.query(TrainingSession).filter(TrainingSession.id == session_id, TrainingSession.club_id == club_id).first()
    if not sess:
        return pd.DataFrame()

    day = sess.microcycle_day.upper().strip()
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

        # Diagnóstico multivariable
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


