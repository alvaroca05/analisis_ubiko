"""
Módulo analítico de ciencias del deporte aplicadas al fútbol.
Implementa:
- ACWR mediante EWMA (Exponentially Weighted Moving Average) según Williams et al. (2017) y Gabbett (2016).
- Z-scores normalizados por demarcación táctica y tipo de microciclo.
- Cálculo de % de cumplimiento objetivo (Planificado vs Real).
- Sistema de semáforos para detección de sobrecarga y riesgo lesional.
"""

from datetime import date
from types import SimpleNamespace
from typing import Dict, List, Optional, Tuple, Any
import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from src.config import (
    EWMA_ACUTE_DAYS,
    EWMA_CHRONIC_DAYS,
    LAMBDA_ACUTE,
    LAMBDA_CHRONIC,
    ACWR_UNDERLOAD,
    ACWR_SWEET_SPOT_MAX,
    ACWR_DANGER_ZONE,
    Z_SCORE_NORMAL,
    Z_SCORE_WARNING,
    COMPLIANCE_LOW_WARNING,
    COMPLIANCE_OPTIMAL_MIN,
    COMPLIANCE_OPTIMAL_MAX,
    COMPLIANCE_HIGH_WARNING,
)
from src.database.models import Player, TrainingSession, PlayerMetric, TargetLoad


def get_acwr_status(acwr: float) -> Tuple[str, str, str]:
    """
    Retorna (estado, color_hex, etiqueta_semaforo) según el valor de ACWR.
    """
    if pd.isna(acwr) or acwr <= 0:
        return "Sin datos", "#9E9E9E", "Gris"
    elif acwr < ACWR_UNDERLOAD:
        return "Subentrenamiento", "#3B82F6", "Azul"
    elif acwr <= ACWR_SWEET_SPOT_MAX:
        return "Óptimo (Sweet Spot)", "#10B981", "Verde"
    elif acwr <= ACWR_DANGER_ZONE:
        return "Precaución / Fatiga", "#F59E0B", "Amarillo"
    else:
        return "Sobrecarga / Peligro", "#EF4444", "Rojo"


def get_compliance_status(pct: float) -> Tuple[str, str, str]:
    """
    Retorna (estado, color_hex, etiqueta) según el porcentaje de cumplimiento.
    """
    if pd.isna(pct):
        return "N/A", "#9E9E9E", "Gris"
    elif pct < COMPLIANCE_LOW_WARNING:
        return "Déficit severo", "#EF4444", "Rojo"
    elif pct < COMPLIANCE_OPTIMAL_MIN:
        return "Déficit moderado", "#F59E0B", "Amarillo"
    elif pct <= COMPLIANCE_OPTIMAL_MAX:
        return "Objetivo Cumplido", "#10B981", "Verde"
    elif pct <= COMPLIANCE_HIGH_WARNING:
        return "Exceso moderado", "#F59E0B", "Amarillo"
    else:
        return "Sobrecarga no planificada", "#EF4444", "Rojo"


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


def calculate_ewma_acwr(
    session: Session,
    player_id: int,
    load_metric: str = "total_distance"
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
        .filter(PlayerMetric.player_id == player_id)
        .order_by(TrainingSession.date.asc())
    )

    df_sessions = pd.read_sql(query.statement, session.bind)
    if df_sessions.empty:
        return pd.DataFrame()

    df_sessions["date"] = pd.to_datetime(df_sessions["date"])

    # En caso de múltiples sesiones en el mismo día (doble turno, partido + compensatorio), consolidar la carga diaria
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

    # Crear rango de fechas diario completo desde la primera sesión hasta la última
    start_date = df_sessions["date"].min()
    end_date = df_sessions["date"].max()
    full_idx = pd.date_range(start_date, end_date, freq="D", name="date")

    # Reindexar para contemplar días de descanso con carga 0
    df_daily = df_daily_agg.reindex(full_idx)
    df_daily["load_value"] = df_daily["load_value"].fillna(0.0)

    # Cálculo iterativo de EWMA
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

    # Evitar divisiones por cero en el ACWR
    df_daily["acwr"] = np.where(
        df_daily["chronic_ewma"] > 1e-3,
        df_daily["acute_ewma"] / df_daily["chronic_ewma"],
        np.nan
    )

    df_result = df_daily.reset_index()
    # Asignar estados de semáforo
    status_info = df_result["acwr"].apply(get_acwr_status)
    df_result["acwr_status"] = [s[0] for s in status_info]
    df_result["acwr_color"] = [s[1] for s in status_info]

    return df_result


def get_latest_player_acwr(session: Session, target_date: Optional[date] = None) -> pd.DataFrame:
    """
    Calcula el ACWR más reciente de todos los jugadores activos a una fecha determinada.
    """
    players = session.query(Player).filter(Player.active == True).all()
    records = []

    for p in players:
        df_acwr = calculate_ewma_acwr(session, p.id, load_metric="total_distance")
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


def calculate_session_summary(session: Session, session_id: int) -> Dict[str, Any]:
    """
    Obtiene el resumen consolidado de una sesión: datos por jugador, comparativa con objetivos y alertas.
    """
    sess_obj = session.query(TrainingSession).filter(TrainingSession.id == session_id).first()
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

    # Cargar métricas de los jugadores
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
        .filter(PlayerMetric.session_id == session_id)
        .order_by(Player.dorsal.asc())
    )
    df_metrics = pd.read_sql(query.statement, session.bind)
    if df_metrics.empty:
        return {"session": sess_info, "metrics": pd.DataFrame(), "team_kpis": {}}

    # Obtener objetivos planificados para este día de microciclo
    targets = (
        session.query(TargetLoad)
        .filter(TargetLoad.microcycle_day == sess_info.microcycle_day)
        .all()
    )
    targets_dict = {
        t.position: {
            "target_td": t.target_td,
            "target_hsr": t.target_hsr,
            "target_hmld": t.target_hmld,
            "target_acc_eff": t.target_acc_eff,
            "target_dec_eff": t.target_dec_eff,
            "target_eff": t.target_acc_eff + t.target_dec_eff
        }
        for t in targets
    }

    # Asignar objetivos y calcular % de cumplimiento
    compliance_td = []
    compliance_hsr = []
    compliance_hmld = []
    compliance_eff = []

    for _, row in df_metrics.iterrows():
        pos_target = targets_dict.get(row["position"], {})
        t_td = pos_target.get("target_td", np.nan)
        t_hsr = pos_target.get("target_hsr", np.nan)
        t_hmld = pos_target.get("target_hmld", np.nan)
        t_eff = pos_target.get("target_eff", np.nan)

        c_td = (row["total_distance"] / t_td * 100.0) if pd.notna(t_td) and t_td > 0 else np.nan
        c_hsr = (row["hsr_distance"] / t_hsr * 100.0) if pd.notna(t_hsr) and t_hsr > 0 else np.nan
        c_hmld = (row["hmld"] / t_hmld * 100.0) if pd.notna(t_hmld) and t_hmld > 0 else np.nan
        c_eff = (row["acc_dec_eff"] / t_eff * 100.0) if pd.notna(t_eff) and t_eff > 0 else np.nan

        compliance_td.append(c_td)
        compliance_hsr.append(c_hsr)
        compliance_hmld.append(c_hmld)
        compliance_eff.append(c_eff)

    df_metrics["compliance_td"] = compliance_td
    df_metrics["compliance_hsr"] = compliance_hsr
    df_metrics["compliance_hmld"] = compliance_hmld
    df_metrics["compliance_eff"] = compliance_eff

    # Cumplimiento general ponderado de la sesión (30% TD + 30% HSR + 20% HMLD + 20% EFF)
    df_metrics["global_compliance"] = (
        0.30 * df_metrics["compliance_td"] +
        0.30 * df_metrics["compliance_hsr"] +
        0.20 * df_metrics["compliance_hmld"] +
        0.20 * df_metrics["compliance_eff"]
    )

    comp_status = df_metrics["global_compliance"].apply(get_compliance_status)
    df_metrics["compliance_status"] = [s[0] for s in comp_status]
    df_metrics["compliance_color"] = [s[1] for s in comp_status]

    # Calcular Z-Scores por demarcación en la sesión
    df_metrics = calculate_position_z_scores(df_metrics)

    # Cruzar con el ACWR del día de la sesión
    df_acwr = get_latest_player_acwr(session, target_date=sess_info.date)
    if not df_acwr.empty:
        df_metrics = df_metrics.merge(
            df_acwr[["player_id", "acute_load", "chronic_load", "acwr", "acwr_status", "acwr_color"]],
            on="player_id",
            how="left"
        )

    # Carga interna (sRPE de Foster = RPE * duración en minutos)
    df_metrics["srpe"] = df_metrics.apply(
        lambda r: (float(r["rpe"]) * (float(r["minutes_played"]) if float(r["minutes_played"]) > 0 else float(sess_info.duration_minutes)))
        if pd.notna(r.get("rpe")) and r.get("rpe") is not None and float(r["rpe"]) > 0
        else np.nan,
        axis=1
    )

    rpe_valid = df_metrics["rpe"].dropna()
    rpe_valid = rpe_valid[rpe_valid > 0]
    srpe_valid = df_metrics["srpe"].dropna()

    # KPIs globales del equipo en la sesión
    team_kpis = {
        "num_players": len(df_metrics),
        "mean_distance": float(df_metrics["total_distance"].mean()),
        "mean_hsr": float(df_metrics["hsr_distance"].mean()),
        "mean_hmld": float(df_metrics["hmld"].mean()),
        "mean_acc_dec": float(df_metrics["acc_dec_eff"].mean()),
        "mean_compliance": float(df_metrics["global_compliance"].dropna().mean()),
        "players_in_danger": int((df_metrics.get("acwr", pd.Series()) > ACWR_DANGER_ZONE).sum()),
        "players_in_caution": int((
            (df_metrics.get("acwr", pd.Series()) > ACWR_SWEET_SPOT_MAX) &
            (df_metrics.get("acwr", pd.Series()) <= ACWR_DANGER_ZONE)
        ).sum()),
        "mean_rpe": float(rpe_valid.mean()) if not rpe_valid.empty else None,
        "count_rpe": int(len(rpe_valid)),
        "mean_srpe": float(srpe_valid.mean()) if not srpe_valid.empty else None
    }

    return {
        "session": sess_info,
        "metrics": df_metrics,
        "targets": targets_dict,
        "team_kpis": team_kpis
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


def calculate_compliance_table(df_metrics: pd.DataFrame, targets_dict: Dict[str, Dict[str, float]]) -> pd.DataFrame:
    """
    Genera un DataFrame resumido de Comparativa Real vs Planificado agrupado por demarcación.
    """
    summary_rows = []
    positions = df_metrics["position"].unique()

    for pos in positions:
        sub = df_metrics[df_metrics["position"] == pos]
        target = targets_dict.get(pos, {})

        real_td = sub["total_distance"].mean()
        real_hsr = sub["hsr_distance"].mean()
        real_hmld = sub["hmld"].mean()
        real_eff = sub["acc_dec_eff"].mean()

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
