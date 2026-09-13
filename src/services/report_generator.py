"""
Generador de informes técnicos y tácticos en lenguaje natural para el cuerpo técnico.
Interpreta automáticamente las métricas de carga externa de la sesión, los ratios ACWR y el grado de cumplimiento táctico.
"""

from typing import Any, Dict
import pandas as pd

from src.config import MICROCYCLE_DESCRIPTIONS, ACWR_DANGER_ZONE, ACWR_SWEET_SPOT_MAX, ACWR_UNDERLOAD


def generate_tactical_report(session_summary: Dict[str, Any]) -> str:
    """
    Genera un informe ejecutivo redactado en lenguaje natural dirigido al Entrenador y Preparador Físico.
    """
    sess = session_summary.get("session")
    df_metrics = session_summary.get("metrics")
    team_kpis = session_summary.get("team_kpis", {})
    targets = session_summary.get("targets", {})

    if sess is None or df_metrics is None or df_metrics.empty:
        return "No hay suficientes datos registrados en la sesión para generar el informe técnico."

    day_desc = MICROCYCLE_DESCRIPTIONS.get(sess.microcycle_day, "Sesión de trabajo general")
    avg_compliance = team_kpis.get("mean_compliance", 0.0)

    # Identificar jugadores por semáforo ACWR
    danger_players = []
    caution_players = []
    underload_players = []

    if "acwr" in df_metrics.columns:
        for _, row in df_metrics.iterrows():
            acwr_val = row.get("acwr")
            name = row.get("player_name", "Jugador")
            pos = row.get("position", "")
            dorsal = row.get("dorsal", "")

            if pd.notna(acwr_val):
                if acwr_val > ACWR_DANGER_ZONE:
                    danger_players.append((f"#{dorsal} {name} ({pos})", acwr_val))
                elif acwr_val > ACWR_SWEET_SPOT_MAX:
                    caution_players.append((f"#{dorsal} {name} ({pos})", acwr_val))
                elif acwr_val < ACWR_UNDERLOAD:
                    underload_players.append((f"#{dorsal} {name} ({pos})", acwr_val))

    # Identificar picos y jugadores destacados (filtrando jugadores de campo para métricas atléticas)
    outfield_df = df_metrics[df_metrics["position"] != "Portero"]
    if outfield_df.empty:
        outfield_df = df_metrics

    max_speed_row = outfield_df.loc[outfield_df["max_speed"].idxmax()]
    max_dist_row = outfield_df.loc[outfield_df["total_distance"].idxmax()]
    max_hsr_row = outfield_df.loc[outfield_df["hsr_distance"].idxmax()]
    max_eff_row = outfield_df.loc[outfield_df["acc_dec_eff"].idxmax()]

    # Construcción del informe
    lines = []
    lines.append(f"══════════════════════════════════════════════════════════════════")
    lines.append(f" INFORME EJECUTIVO DEL CUERPO TÉCNICO | SESIÓN {sess.name.upper()}")
    lines.append(f" Fecha: {sess.date} | Día Microciclo: {sess.microcycle_day} ({sess.session_type})")
    lines.append(f" Enfoque del día: {day_desc}")
    lines.append(f"══════════════════════════════════════════════════════════════════\n")

    # 1. Resumen Global de Carga
    lines.append("1. RESUMEN GLOBAL DE LA SESIÓN")
    lines.append(f"• Jugadores monitorizados: {team_kpis.get('num_players', len(df_metrics))}")
    lines.append(f"• Distancia Total Media: {team_kpis.get('mean_distance', 0.0):.1f} metros por jugador.")
    lines.append(f"• Carrera de Alta Velocidad (HSR >19.8 km/h): {team_kpis.get('mean_hsr', 0.0):.1f} m promedio.")
    lines.append(f"• High Metabolic Load Distance (HMLD): {team_kpis.get('mean_hmld', 0.0):.1f} m promedio.")
    lines.append(f"• Aceleraciones + Desaceleraciones Eficaces: {team_kpis.get('mean_acc_dec', 0.0):.1f} esfuerzos/jugador.")
    lines.append(f"• Cumplimiento del plan táctico: {avg_compliance:.1f}% respecto a la carga prescrita.\n")

    # 2. Semáforo de Riesgo y Fatiga (ACWR)
    lines.append("2. EVALUACIÓN DE FATIGA Y RIESGO LESIONAL (ACWR - EWMA)")
    if danger_players:
        lines.append("  ⚠️ ALERTA ROJA (Riesgo Alto de Sobrecarga - ACWR > 1.50):")
        for p, val in danger_players:
            lines.append(f"    - {p}: ACWR = {val:.2f}. Se sugiere descargar en la próxima sesión o dosificar minutos.")
    else:
        lines.append("  ✓ Ningún jugador en zona de riesgo crítico (ACWR > 1.50).")

    if caution_players:
        lines.append("  ⚡ ZONA DE PRECAUCIÓN (Fatiga Acumulada - ACWR 1.30 - 1.50):")
        for p, val in caution_players:
            lines.append(f"    - {p}: ACWR = {val:.2f}. Monitorear recuperación neuromuscular (CMJ / RPE).")

    if underload_players:
        lines.append("  📉 SUBENTRENAMIENTO (ACWR < 0.80 - Posible desadaptación física):")
        for p, val in underload_players[:4]:
            lines.append(f"    - {p}: ACWR = {val:.2f}. Requiere trabajo compensatorio de carrera o rondos de alta intensidad.")
    lines.append("")

    # 3. Cumplimiento Táctico por Demarcaciones
    lines.append("3. ANÁLISIS DE CUMPLIMIENTO TÁCTICO POR LÍNEA")
    for pos in df_metrics["position"].unique():
        sub_pos = df_metrics[df_metrics["position"] == pos]
        mean_comp = sub_pos["global_compliance"].mean()
        pos_hsr = sub_pos["hsr_distance"].mean()
        pos_td = sub_pos["total_distance"].mean()

        target = targets.get(pos, {})
        tgt_hsr = target.get("target_hsr", 0.0)

        diff_text = "alineado con el plan"
        if mean_comp > 115:
            diff_text = "por encima de la carga prescrita (exceso de estímulo)"
        elif mean_comp < 85:
            diff_text = "por debajo del objetivo táctico (déficit de estímulo)"

        lines.append(
            f"• {pos.upper()}S ({len(sub_pos)} jug.): Cumplimiento {mean_comp:.1f}% ({diff_text}). "
            f"DT: {pos_td:.0f}m | HSR: {pos_hsr:.0f}m (Objetivo: {tgt_hsr:.0f}m)."
        )
    lines.append("")

    # 4. Jugadores con Máximo Rendimiento
    lines.append("4. PICOS DE RENDIMIENTO Y VELOCIDAD PUNTA")
    lines.append(f"• Velocidad Máxima: #{max_speed_row['dorsal']} {max_speed_row['player_name']} ({max_speed_row['position']}) con {max_speed_row['max_speed']:.2f} km/h.")
    lines.append(f"• Mayor Distancia Total: #{max_dist_row['dorsal']} {max_dist_row['player_name']} ({max_dist_row['position']}) con {max_dist_row['total_distance']:.1f} m.")
    lines.append(f"• Mayor Distancia HSR (>19.8 km/h): #{max_hsr_row['dorsal']} {max_hsr_row['player_name']} ({max_hsr_row['position']}) con {max_hsr_row['hsr_distance']:.1f} m.")
    lines.append(f"• Mayor Carga Mecánica (AC.E): #{max_eff_row['dorsal']} {max_eff_row['player_name']} ({max_eff_row['position']}) con {max_eff_row['acc_dec_eff']} aceleraciones/desaceleraciones.")

    gk_df = df_metrics[df_metrics["position"] == "Portero"]
    if not gk_df.empty:
        lines.append("• Monitorización de Portería:")
        for _, gk_row in gk_df.iterrows():
            lines.append(f"    - #{gk_row['dorsal']} {gk_row['player_name']}: DT {gk_row['total_distance']:.0f}m | V5/HSR {gk_row['hsr_distance']:.1f}m | Carga {gk_row['acc_dec_eff']} acc/dec | Vmáx {gk_row['max_speed']:.2f} km/h.")
    lines.append("")

    # 5. Recomendaciones para la Próxima Sesión
    next_day_rec = _get_next_day_recommendations(sess.microcycle_day, danger_players, underload_players)
    lines.append("5. DIRECTRICES PARA LA SIGUIENTE SESIÓN")
    lines.append(next_day_rec)

    return "\n".join(lines)


def _get_next_day_recommendations(current_day: str, danger_players: list, underload_players: list) -> str:
    """Genera recomendaciones pedagógicas según el orden del microciclo."""
    recs = []

    if current_day == "MD-4":
        recs.append("• Mañana corresponde MD-3 (Duración/Resistencia): Planificar tareas en espacios amplios (fútbol 10v10 o 11v11) para estimular HSR y sprint.")
    elif current_day == "MD-3":
        recs.append("• Mañana corresponde MD-2 (Velocidad/Táctica): Reducir volumen total de metros y centrarse en aceleraciones cortas y tareas de finalización explosivas.")
    elif current_day == "MD-2":
        recs.append("• Mañana corresponde MD-1 (Activación/Prepartido): Sesión corta (45-50 min), baja carga metabólica, rondos de reacción y balón parado ofensivo/defensivo.")
    elif current_day == "MD-1":
        recs.append("• Mañana es DÍA DE PARTIDO (MD): Los jugadores titulares están listos. Mantener hidratación y control de descanso.")
    elif current_day == "MD":
        recs.append("• Pospartido: Aplicar protocolos de recuperación (baños de contraste, nutrición rápida) y programar sesión compensatoria para los no convocados o suplentes.")

    if danger_players:
        names = ", ".join([p[0].split()[1] for p in danger_players[:2]])
        recs.append(f"• Atención individual: Reducir carga activa en tareas de oposición a {names}.")
    if underload_players:
        names = ", ".join([p[0].split()[1] for p in underload_players[:2]])
        recs.append(f"• Suplentes/No habituales: Programar serie compensatoria de carrera continua fraccionada a {names}.")

    return "\n".join(recs)
