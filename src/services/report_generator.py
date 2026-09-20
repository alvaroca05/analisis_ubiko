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

    def _get_max_row(df, col):
        if col in df.columns:
            valid = df[col].dropna()
            if not valid.empty:
                return df.loc[valid.idxmax()]
        return df.iloc[0] if not df.empty else None

    max_speed_row = _get_max_row(outfield_df, "max_speed")
    max_dist_row = _get_max_row(outfield_df, "total_distance")
    max_hsr_row = _get_max_row(outfield_df, "hsr_distance")
    max_eff_row = _get_max_row(outfield_df, "acc_dec_eff")

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
        if "global_compliance" in sub_pos.columns:
            mean_comp = float(sub_pos["global_compliance"].dropna().mean() or 100.0)
        elif "compliance_pct" in sub_pos.columns:
            mean_comp = float(sub_pos["compliance_pct"].dropna().mean() or 100.0)
        else:
            mean_comp = 100.0

        pos_hsr = float(sub_pos["hsr_distance"].dropna().mean() or 0.0) if "hsr_distance" in sub_pos.columns else 0.0
        pos_td = float(sub_pos["total_distance"].dropna().mean() or 0.0) if "total_distance" in sub_pos.columns else 0.0

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
    if max_speed_row is not None:
        lines.append(f"• Velocidad Máxima: #{max_speed_row['dorsal']} {max_speed_row['player_name']} ({max_speed_row['position']}) con {max_speed_row['max_speed']:.2f} km/h.")
    if max_dist_row is not None:
        lines.append(f"• Mayor Distancia Total: #{max_dist_row['dorsal']} {max_dist_row['player_name']} ({max_dist_row['position']}) con {max_dist_row['total_distance']:.1f} m.")
    if max_hsr_row is not None:
        lines.append(f"• Mayor Distancia HSR (>19.8 km/h): #{max_hsr_row['dorsal']} {max_hsr_row['player_name']} ({max_hsr_row['position']}) con {max_hsr_row['hsr_distance']:.1f} m.")
    if max_eff_row is not None:
        lines.append(f"• Mayor Carga Mecánica (AC.E): #{max_eff_row['dorsal']} {max_eff_row['player_name']} ({max_eff_row['position']}) con {max_eff_row['acc_dec_eff']} aceleraciones/desaceleraciones.")

    gk_df = df_metrics[df_metrics["position"] == "Portero"]
    if not gk_df.empty:
        lines.append("• Monitorización de Portería:")
        for _, gk_row in gk_df.iterrows():
            lines.append(f"    - #{gk_row['dorsal']} {gk_row['player_name']}: DT {gk_row.get('total_distance', 0.0):.0f}m | V5/HSR {gk_row.get('hsr_distance', 0.0):.1f}m | Carga {gk_row.get('acc_dec_eff', 0)} acc/dec | Vmáx {gk_row.get('max_speed', 0.0):.2f} km/h.")
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


# ==============================================================================
# INFORME SEMANAL PARA EL PRIMER ENTRENADOR Y CUERPO TÉCNICO
# ==============================================================================

def generate_weekly_coach_report(summary: Dict[str, Any]) -> str:
    """
    Genera el informe ejecutivo semanal sintetizado en formato texto para el Primer Entrenador.
    Desglosa:
    1. Resumen del Microciclo (estímulo planificado vs. carga total acumulada).
    2. Futbolistas en Estado Óptimo (ACWR 0.8 - 1.3).
    3. Futbolistas en Déficit de Estímulo (para trabajo compensatorio pre/post partido).
    4. Alertas de Fatiga y Riesgo Lesional (con recomendaciones tácticas/fisiológicas).
    """
    start_d = summary.get("start_date")
    end_d = summary.get("end_date")
    team_kpis = summary.get("team_kpis", {})
    breakdown = summary.get("sessions_breakdown", [])
    optimal = summary.get("optimal_players", [])
    deficit = summary.get("deficit_players", [])
    fatigue = summary.get("fatigue_alerts", [])

    lines = []
    lines.append("════════════════════════════════════════════════════════════════════════════════")
    lines.append("           UBIKO HUB | INFORME SEMANAL PARA EL PRIMER ENTRENADOR                ")
    lines.append(f"           Periodo Evaluado: {start_d} al {end_d}                              ")
    lines.append(f"           Sesiones Integradas: {team_kpis.get('num_sessions', 0)} | Futbolistas: {team_kpis.get('players_monitored', 0)}")
    lines.append("════════════════════════════════════════════════════════════════════════════════\n")

    # 1. Resumen del Microciclo
    lines.append("1. RESUMEN DEL MICROCICLO (ESTÍMULO PLANIFICADO VS. CARGA ACUMULADA)")
    lines.append(f"• Distancia Total Acumulada (Media Plantilla): {team_kpis.get('team_mean_distance_km', 0.0):.2f} km")
    lines.append(f"• Carrera de Alta Velocidad Acumulada (HSR >21 km/h): {team_kpis.get('team_mean_hsr_m', 0.0):.0f} m promedio")
    lines.append(f"• Carga Neuromuscular Mecánica (AC.E Totales): {team_kpis.get('team_mean_eff', 0)} aceleraciones/frenadas promedio")
    lines.append(f"• Tiempo Total de Trabajo de Campo: {team_kpis.get('total_team_duration', 0)} minutos\n")

    lines.append("Desglose cronológico de sesiones:")
    for s in breakdown:
        lines.append(
            f"  [{s['date'].strftime('%d/%m')} | {s['microcycle_day']} ({s['duration']}')]: "
            f"DT: {s['mean_td_km']:.2f} km | HSR: {s['mean_hsr_m']:.0f}m | AC.E: {s['mean_eff']:.0f} | "
            f"Foco: {s['stimulus']}"
        )
    lines.append("")

    # 2. Futbolistas en Estado Óptimo
    lines.append(f"2. FUTBOLISTAS EN ESTADO ÓPTIMO ({len(optimal)} jugadores)")
    lines.append("Jugadores que alcanzaron las metas fisiológicas sin acumular sobrecarga (ACWR en Sweet Spot 0.80 - 1.30):")
    if optimal:
        for p in optimal:
            acwr_str = f"ACWR: {p['acwr']:.2f}" if p['acwr'] is not None else "ACWR: N/D"
            lines.append(
                f"  ✓ #{p['dorsal']} {p['name']} ({p['position']}): "
                f"DT: {p['tot_km']:.1f} km | HSR: {p['tot_hsr']:.0f}m | AC.E: {p['tot_eff']} | {p['tot_mins']:.0f}' jugados | {acwr_str}"
            )
    else:
        lines.append("  (Ningún futbolista encaja exactamente en el rango óptimo)")
    lines.append("")

    # 3. Futbolistas en Déficit de Estímulo
    lines.append(f"3. FUTBOLISTAS EN DÉFICIT DE ESTÍMULO ({len(deficit)} jugadores)")
    lines.append("Jugadores con estímulo semanal insuficiente (suplentes, pocos minutos o ACWR < 0.80). Planificar compensatorio:")
    if deficit:
        for p in deficit:
            acwr_str = f"ACWR: {p['acwr']:.2f}" if p['acwr'] is not None else "ACWR: N/D"
            lines.append(f"  • #{p['dorsal']} {p['name']} ({p['position']}) | {p['tot_mins']:.0f}' jugados | {acwr_str}")
            lines.append(f"    - Motivo: {p.get('deficit_reasons', 'Baja carga')}")
            lines.append(f"    - {p.get('compensatory_plan', 'Programar compensatorio post-partido.')}")
    else:
        lines.append("  ✓ Todos los futbolistas alcanzaron los umbrales mínimos requeridos.")
    lines.append("")

    # 4. Alertas de Fatiga y Riesgo Lesional
    lines.append(f"4. ALERTAS DE FATIGA Y RIESGO LESIONAL ({len(fatigue)} jugadores)")
    lines.append("Jugadores con fatiga acumulada crítica (ACWR > 1.35 o picos agudos). Directrices para el Míster:")
    if fatigue:
        for p in fatigue:
            acwr_str = f"ACWR: {p['acwr']:.2f}" if p['acwr'] is not None else "ACWR: N/D"
            lines.append(f"  ⚠️ #{p['dorsal']} {p['name']} ({p['position']}) | AC.E: {p['tot_eff']} | {acwr_str}")
            lines.append(f"    - Causa: {p.get('alert_reasons', 'Sobrecarga aguda')}")
            lines.append(f"    - {p.get('recommendation', 'Dosificar minutos o descanso activo.')}")
    else:
        lines.append("  ✓ Ningún jugador en zona de fatiga crítica o riesgo lesional agudo.")
    lines.append("")

    lines.append("════════════════════════════════════════════════════════════════════════════════")
    lines.append("Informe generado automáticamente por UBIKO Hub | Preparación Física & Rendimiento")
    lines.append("════════════════════════════════════════════════════════════════════════════════")

    return "\n".join(lines)


def generate_weekly_coach_html_report(summary: Dict[str, Any]) -> str:
    """
    Genera un informe HTML imprimible de alta fidelidad estética (preparado para impresión A4 o guardado en PDF).
    """
    start_d = summary.get("start_date")
    end_d = summary.get("end_date")
    team_kpis = summary.get("team_kpis", {})
    breakdown = summary.get("sessions_breakdown", [])
    optimal = summary.get("optimal_players", [])
    deficit = summary.get("deficit_players", [])
    fatigue = summary.get("fatigue_alerts", [])

    # Construir filas de sesiones
    session_rows = ""
    for s in breakdown:
        session_rows += f"""
        <tr>
            <td style="font-weight: bold; color: #1E293B;">{s['date'].strftime('%d/%m/%Y')}</td>
            <td><span class="badge badge-gray">{s['microcycle_day']}</span></td>
            <td>{s['session_type']}</td>
            <td>{s['duration']}'</td>
            <td><strong>{s['mean_td_km']:.2f} km</strong></td>
            <td>{s['mean_hsr_m']:.0f} m</td>
            <td>{s['mean_eff']:.0f}</td>
            <td style="font-size: 0.85rem; color: #475569;">{s['stimulus']}</td>
        </tr>
        """

    # Construir tarjetas de óptimos
    optimal_cards = ""
    for p in optimal:
        acwr_badge = f"{p['acwr']:.2f}" if p['acwr'] is not None else "N/D"
        optimal_cards += f"""
        <div class="player-card optimal-border">
            <div class="player-header">
                <strong>#{p['dorsal']} {p['name']}</strong>
                <span class="badge badge-green">ACWR: {acwr_badge}</span>
            </div>
            <div class="player-metrics">
                <span>Pos: {p['position']}</span> |
                <span>DT: {p['tot_km']:.1f} km</span> |
                <span>HSR: {p['tot_hsr']:.0f} m</span> |
                <span>AC.E: {p['tot_eff']}</span> |
                <span>Min: {p['tot_mins']:.0f}' ({p['sessions_count']} ses.)</span>
            </div>
            <div class="player-note" style="color: #065F46;">
                ✓ {p.get('optimal_note', 'Apto al 100%')}
            </div>
        </div>
        """

    # Construir tarjetas de déficit
    deficit_cards = ""
    for p in deficit:
        acwr_badge = f"{p['acwr']:.2f}" if p['acwr'] is not None else "N/D"
        deficit_cards += f"""
        <div class="player-card deficit-border">
            <div class="player-header">
                <strong>#{p['dorsal']} {p['name']}</strong>
                <span class="badge badge-blue">ACWR: {acwr_badge}</span>
            </div>
            <div class="player-metrics">
                <span>Pos: {p['position']}</span> |
                <span>DT: {p['tot_km']:.1f} km</span> |
                <span>HSR: {p['tot_hsr']:.0f} m</span> |
                <span>AC.E: {p['tot_eff']}</span> |
                <span>Min: {p['tot_mins']:.0f}'</span>
            </div>
            <div class="player-reason"><strong>Déficit:</strong> {p.get('deficit_reasons', 'Bajo minutaje')}</div>
            <div class="player-rec" style="color: #1E40AF;"><strong>Propuesta:</strong> {p.get('compensatory_plan', 'Planificar compensatorio')}</div>
        </div>
        """

    # Construir tarjetas de fatiga
    fatigue_cards = ""
    for p in fatigue:
        acwr_badge = f"{p['acwr']:.2f}" if p['acwr'] is not None else "N/D"
        fatigue_cards += f"""
        <div class="player-card fatigue-border">
            <div class="player-header">
                <strong style="color: #991B1B;">⚠️ #{p['dorsal']} {p['name']}</strong>
                <span class="badge badge-red">ACWR: {acwr_badge}</span>
            </div>
            <div class="player-metrics">
                <span>Pos: {p['position']}</span> |
                <span>DT: {p['tot_km']:.1f} km</span> |
                <span>HSR: {p['tot_hsr']:.0f} m</span> |
                <span>AC.E: {p['tot_eff']}</span> |
                <span>Min: {p['tot_mins']:.0f}'</span>
            </div>
            <div class="player-reason" style="color: #B91C1C;"><strong>Alerta:</strong> {p.get('alert_reasons', 'Fatiga crítica')}</div>
            <div class="player-rec" style="color: #9A3412;"><strong>Recomendación al Míster:</strong> {p.get('recommendation', 'Dosificar minutaje')}</div>
        </div>
        """

    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <title>UBIKO Hub | Informe Semanal para el Primer Entrenador</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            margin: 0;
            padding: 24px;
            background-color: #F8FAFC;
            color: #1E293B;
            line-height: 1.5;
        }}
        .container {{
            max-width: 1050px;
            margin: 0 auto;
            background: #FFFFFF;
            padding: 32px 40px;
            border-radius: 12px;
            box-shadow: 0 4px 16px rgba(0, 0, 0, 0.06);
        }}
        .header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 3px solid #0284C7;
            padding-bottom: 16px;
            margin-bottom: 24px;
        }}
        .header h1 {{
            margin: 0;
            font-size: 1.6rem;
            color: #0F172A;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}
        .header p {{
            margin: 4px 0 0 0;
            color: #64748B;
            font-size: 0.95rem;
        }}
        .btn-print {{
            background-color: #0284C7;
            color: white;
            border: none;
            padding: 10px 18px;
            border-radius: 6px;
            font-weight: 600;
            cursor: pointer;
            font-size: 0.9rem;
        }}
        .kpi-grid {{
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 16px;
            margin-bottom: 28px;
        }}
        .kpi-card {{
            background: #F1F5F9;
            padding: 14px 18px;
            border-radius: 8px;
            border-left: 4px solid #0284C7;
        }}
        .kpi-title {{
            font-size: 0.8rem;
            text-transform: uppercase;
            color: #64748B;
            font-weight: 600;
        }}
        .kpi-value {{
            font-size: 1.5rem;
            font-weight: 700;
            color: #0F172A;
            margin-top: 4px;
        }}
        .section-title {{
            font-size: 1.2rem;
            font-weight: 700;
            color: #0F172A;
            border-bottom: 2px solid #E2E8F0;
            padding-bottom: 8px;
            margin: 28px 0 16px 0;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 0.9rem;
            margin-bottom: 20px;
        }}
        th, td {{
            padding: 10px 12px;
            text-align: left;
            border-bottom: 1px solid #E2E8F0;
        }}
        th {{
            background-color: #F8FAFC;
            color: #475569;
            font-weight: 600;
        }}
        .badge {{
            display: inline-block;
            padding: 3px 8px;
            border-radius: 12px;
            font-size: 0.78rem;
            font-weight: 600;
        }}
        .badge-green {{ background-color: #DCFCE7; color: #166534; }}
        .badge-blue {{ background-color: #DBEAFE; color: #1E40AF; }}
        .badge-red {{ background-color: #FEE2E2; color: #991B1B; }}
        .badge-gray {{ background-color: #E2E8F0; color: #334155; }}
        .player-grid {{
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 12px;
        }}
        .player-card {{
            background: #FFFFFF;
            border: 1px solid #E2E8F0;
            border-radius: 8px;
            padding: 12px 16px;
        }}
        .optimal-border {{ border-left: 4px solid #10B981; background: #F0FDF4; }}
        .deficit-border {{ border-left: 4px solid #3B82F6; background: #EFF6FF; }}
        .fatigue-border {{ border-left: 4px solid #EF4444; background: #FEF2F2; }}
        .player-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 6px;
        }}
        .player-metrics {{
            font-size: 0.85rem;
            color: #475569;
            margin-bottom: 6px;
        }}
        .player-reason, .player-rec, .player-note {{
            font-size: 0.83rem;
            margin-top: 4px;
            line-height: 1.4;
        }}
        .footer {{
            margin-top: 36px;
            padding-top: 16px;
            border-top: 1px solid #E2E8F0;
            text-align: center;
            font-size: 0.82rem;
            color: #94A3B8;
        }}
        @media print {{
            body {{ background: #FFF; padding: 0; }}
            .container {{ box-shadow: none; padding: 0; max-width: 100%; }}
            .btn-print {{ display: none !important; }}
            .player-card {{ break-inside: avoid; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div>
                <h1>Informe Semanal del Cuerpo Técnico</h1>
                <p>Periodo competitivo: <strong>{start_d} al {end_d}</strong> | Preparación Física & Rendimiento</p>
            </div>
            <button class="btn-print" onclick="window.print()">🖨️ Imprimir / Guardar PDF</button>
        </div>

        <!-- Tarjetas KPI Globales -->
        <div class="kpi-grid">
            <div class="kpi-card">
                <div class="kpi-title">Distancia Media Acumulada</div>
                <div class="kpi-value">{team_kpis.get('team_mean_distance_km', 0.0):.2f} km</div>
            </div>
            <div class="kpi-card" style="border-left-color: #10B981;">
                <div class="kpi-title">HSR Medio (>21 km/h)</div>
                <div class="kpi-value">{team_kpis.get('team_mean_hsr_m', 0.0):.0f} m</div>
            </div>
            <div class="kpi-card" style="border-left-color: #F59E0B;">
                <div class="kpi-title">Carga Neuromuscular (AC.E)</div>
                <div class="kpi-value">{team_kpis.get('team_mean_eff', 0)} esfuerzos</div>
            </div>
            <div class="kpi-card" style="border-left-color: #8B5CF6;">
                <div class="kpi-title">Sesiones Monitorizadas</div>
                <div class="kpi-value">{team_kpis.get('num_sessions', 0)} ({team_kpis.get('total_team_duration', 0)}')</div>
            </div>
        </div>

        <!-- 1. Desglose del Microciclo -->
        <div class="section-title">
            <span>1. Resumen y Desglose Diario del Microciclo</span>
            <span style="font-size: 0.85rem; color: #64748B; font-weight: normal;">Estímulo planificado vs. carga real</span>
        </div>
        <table>
            <thead>
                <tr>
                    <th>Fecha</th>
                    <th>Día</th>
                    <th>Tipo</th>
                    <th>Duración</th>
                    <th>DT Media</th>
                    <th>HSR Medio</th>
                    <th>AC.E Medio</th>
                    <th>Estímulo Principal</th>
                </tr>
            </thead>
            <tbody>
                {session_rows}
            </tbody>
        </table>

        <!-- 2. Futbolistas en Estado Óptimo -->
        <div class="section-title">
            <span style="color: #15803D;">2. Futbolistas en Estado Óptimo ({len(optimal)})</span>
            <span class="badge badge-green">Sweet Spot 0.80 - 1.30</span>
        </div>
        <div class="player-grid">
            {optimal_cards if optimal else '<p style="color: #64748B;">Sin futbolistas en este rango.</p>'}
        </div>

        <!-- 3. Futbolistas en Déficit de Estímulo -->
        <div class="section-title">
            <span style="color: #1E40AF;">3. Futbolistas en Déficit de Estímulo ({len(deficit)})</span>
            <span class="badge badge-blue">Plan de Trabajo Compensatorio</span>
        </div>
        <div class="player-grid">
            {deficit_cards if deficit else '<p style="color: #64748B;">Ningún jugador en déficit.</p>'}
        </div>

        <!-- 4. Alertas de Fatiga y Riesgo Lesional -->
        <div class="section-title">
            <span style="color: #B91C1C;">4. Alertas de Fatiga y Riesgo Lesional ({len(fatigue)})</span>
            <span class="badge badge-red">Directrices para el Primer Entrenador</span>
        </div>
        <div class="player-grid">
            {fatigue_cards if fatigue else '<p style="color: #64748B;">Plantilla sin alertas críticas de sobrecarga.</p>'}
        </div>

        <div class="footer">
            Generado automáticamente por UBIKO Hub | Plataforma de Rendimiento Táctico & GPS | Universidad de Córdoba
        </div>
    </div>
</body>
</html>"""

    return html

