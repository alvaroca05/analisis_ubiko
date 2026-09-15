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

        # Determinar 100% del partido y valor prescrito para la métrica clave del día
        if key_metric == "acc_dec_eff":
            peak_100 = float(peak.peak_eff)
            val_real = float(m.acc_dec_eff or 0)
            target_prescribed = peak_100 * (target_pct / 100.0)
            unit = " esfuerzos"
        elif key_metric == "hsr_distance":
            peak_100 = float(peak.peak_hsr)
            val_real = float(m.hsr_distance or 0.0)
            target_prescribed = peak_100 * (target_pct / 100.0)
            unit = " m"
        else:  # total_distance
            peak_100 = float(peak.peak_td)
            val_real = float(m.total_distance or 0.0)
            target_prescribed = peak_100 * (target_pct / 100.0)
            unit = " m"

        # % Cumplimiento respecto a lo prescrito hoy
        compliance_pct = (val_real / target_prescribed * 100.0) if target_prescribed > 0 else 0.0
        # % Respecto al partido 100%
        match_share_pct = (val_real / peak_100 * 100.0) if peak_100 > 0 else 0.0

        status, color_hex, color_label = get_stimulus_compliance_status(compliance_pct)

        rows.append({
            "player_id": m.player_id,
            "dorsal": m.dorsal,
            "player_name": m.player_name,
            "position": m.position,
            "key_metric": key_metric,
            "key_label": key_label,
            "val_real": round(val_real, 1),
            "val_real_formatted": f"{val_real:.0f}{unit}" if unit == " m" else f"{int(val_real)}{unit}",
            "val_target": round(target_prescribed, 1),
            "val_target_formatted": f"{target_prescribed:.0f}{unit}" if unit == " m" else f"{int(target_prescribed)}{unit}",
            "val_match_100": round(peak_100, 1),
            "val_match_100_formatted": f"{peak_100:.0f}{unit}" if unit == " m" else f"{int(peak_100)}{unit}",
            "compliance_pct": round(compliance_pct, 1),
            "match_share_pct": round(match_share_pct, 1),
            "status": status,
            "color_hex": color_hex,
            "color_label": color_label,
            "peak_match_name": peak.peak_session_name or "Oficial",
            "minutes": m.minutes_played,
            "rpe": m.rpe
        })

    return pd.DataFrame(rows)


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

    return {
        "session": sess_info,
        "metrics": df_metrics,
        "team_kpis": team_kpis,
        "compliance_indiv": df_comp_indiv
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

