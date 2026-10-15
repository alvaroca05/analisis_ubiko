"""
Módulo de generación de informes PDF oficiales para el Salerm Cosmetics Puente Genil.
Replica fielmente la plantilla manuscrita/Excel de referencia de partidos del preparador físico.
"""

import io
from typing import List, Dict, Any, Optional
import pandas as pd


def generate_match_reference_pdf(
    match_title: str,
    df_rows: pd.DataFrame,
    season_title: str = "TEMPORADA 26/27 SALERM COSMETIC PUENTE GENIL REFERENCIA DATOS DE PARTIDOS",
    is_full_squad: Optional[bool] = None
) -> bytes:
    """
    Genera un documento PDF en orientación horizontal (Landscape) que reproduce
    exactamente la estética, colores y estructura del Excel oficial del preparador físico:
    - Cabecera general del club.
    - Bloque lateral con nombre del partido (Formato Oficial 6 Roles) o cabecera completa (Convocatoria).
    - Fila 'JUGADOR TOP' destacada en fondo rojo suave (#E06666).
    - Filas posicionales (Central, Lateral, Mediocentro, Extremo con HSR dorado, Delantero).
    - Franja y fila de 'DATOS REFERENCIA GENERALES EQUIPO' en azul cian (#29AAE1).
    """
    try:
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib import colors
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    except ImportError:
        # Fallback si reportlab no está instalado aún en el entorno local
        return _generate_html_pdf_fallback(match_title, df_rows, season_title)

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=20,
        rightMargin=20,
        topMargin=20,
        bottomMargin=20
    )

    styles = getSampleStyleSheet()

    # Separar jugadores y resumen de equipo
    player_rows = []
    team_row_vals = None
    for _, r in df_rows.iterrows():
        pos = str(r.get("POSICIÓN", "")).strip()
        jug = str(r.get("JUGADOR", "")).strip()
        tiempo = str(r.get("TIEMPO", "")).strip()
        dt = str(r.get("DISTANCIA TOTAL (km)", "")).strip()
        vmax = str(r.get("VELOCIDAD MAX (km/h)", "")).strip()
        hsr = str(r.get("HSR (m)", "")).strip()
        sp_m = str(r.get("METROS EN SPRINT", "")).strip()
        sprints = str(r.get("#SPRINTS", "")).strip()
        acc = str(r.get("#ACC EXPL", "")).strip()
        dcc = str(r.get("#DCC EXPL", "")).strip()
        r_type = r.get("_row_type", "")

        if r_type == "team" or "EQUIPO" in pos:
            team_row_vals = (tiempo, dt, vmax, hsr, sp_m, sprints, acc, dcc)
        else:
            player_rows.append((pos, jug, tiempo, dt, vmax, hsr, sp_m, sprints, acc, dcc, r_type))

    if is_full_squad is None:
        is_full_squad = len(player_rows) > 8 or any("(Sin minutos)" in str(p[1]) for p in player_rows)

    short_block_name = match_title.replace("Jornada", "PARTIDO").replace("Partido contra", "").strip()
    if "(" in short_block_name:
        short_block_name = short_block_name.split("(")[0].strip()

    # Tipografía y espaciado adaptativo
    f_size = 7.5 if is_full_squad else 8.5
    f_lead = 9.5 if is_full_squad else 11.0
    pad_v = 2.5 if is_full_squad else 4.0

    title_style = ParagraphStyle(
        "DocTitle",
        fontName="Helvetica-Bold",
        fontSize=11 if is_full_squad else 12,
        leading=14 if is_full_squad else 15,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#0F172A")
    )
    cell_style = ParagraphStyle(
        "CellNormal",
        fontName="Helvetica",
        fontSize=f_size,
        leading=f_lead,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#1E293B")
    )
    cell_bold = ParagraphStyle(
        "CellBold",
        fontName="Helvetica-Bold",
        fontSize=f_size,
        leading=f_lead,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#0F172A")
    )
    cell_white = ParagraphStyle(
        "CellWhite",
        fontName="Helvetica-Bold",
        fontSize=f_size,
        leading=f_lead,
        alignment=TA_CENTER,
        textColor=colors.white
    )

    elements = []

    # 1. Cabecera con título del Club y Temporada
    if is_full_squad:
        header_text = f"<b>{season_title}</b><br/><font size=9 color='#1E3A8A'>{short_block_name} &bull; CONVOCATORIA COMPLETA ({len(player_rows)} Jugadores)</font>"
    else:
        header_text = f"<b>{season_title}</b>"

    title_p = Paragraph(header_text, title_style)
    title_table = Table([[title_p]], colWidths=[800])
    title_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#F1F5F9")),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor("#334155")),
        ('TOPPADDING', (0, 0), (-1, -1), 4 if is_full_squad else 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4 if is_full_squad else 6),
    ]))
    elements.append(title_table)
    elements.append(Spacer(1, 6 if is_full_squad else 10))

    table_styles = [
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#475569")),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#E2E8F0")),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), pad_v),
        ('BOTTOMPADDING', (0, 0), (-1, -1), pad_v),
    ]

    row_idx = 1

    if is_full_squad:
        # En convocatoria completa omitimos la columna 'BLOQUE' lateral para dar espacio suficiente a los nombres
        headers = [
            "POSICIÓN", "JUGADOR", "TIEMPO", "DISTANCIA\nTOTAL (km)",
            "VELOCIDAD\nMAX (km/h)", "HSR (m)", "METROS EN\nSPRINT", "#SPRINTS",
            "#ACC EXPL", "#DCC EXPL"
        ]
        col_widths = [90, 140, 55, 75, 75, 65, 75, 55, 55, 55]
        header_row = [Paragraph(f"<b>{h}</b>", cell_bold) for h in headers]
        table_data = [header_row]

        for p_tuple in player_rows:
            pos, jug, tiempo, dt, vmax, hsr, sp_m, sprints, acc, dcc, r_type = p_tuple
            is_top = (r_type == "top" or "TOP" in pos or "⭐" in pos)
            pos_clean = pos.replace("⭐", "").strip()

            row_content = [
                Paragraph(f"<b>{pos_clean}</b>", cell_white if is_top else cell_bold),
                Paragraph(f"<b>{jug}</b>" if is_top else jug, cell_white if is_top else cell_style),
                Paragraph(tiempo, cell_white if is_top else cell_style),
                Paragraph(dt, cell_white if is_top else cell_style),
                Paragraph(vmax, cell_white if is_top else cell_style),
                Paragraph(hsr, cell_white if is_top else cell_style),
                Paragraph(sp_m, cell_white if is_top else cell_style),
                Paragraph(sprints, cell_white if is_top else cell_style),
                Paragraph(acc, cell_white if is_top else cell_style),
                Paragraph(dcc, cell_white if is_top else cell_style),
            ]
            table_data.append(row_content)

            if is_top:
                table_styles.append(('BACKGROUND', (0, row_idx), (-1, row_idx), colors.HexColor("#D9534F")))
            elif "EXTREMO" in pos_clean or "CELLOU" in jug.upper():
                table_styles.append(('BACKGROUND', (5, row_idx), (5, row_idx), colors.HexColor("#FFF2CC")))

            row_idx += 1

        # Fila de TÍTULO DE EQUIPO
        team_title_p = Paragraph("<b>DATOS REFERENCIA GENERALES EQUIPO</b>", cell_white)
        team_header_row = [team_title_p] + [""] * 9
        table_data.append(team_header_row)
        team_header_idx = row_idx
        table_styles.extend([
            ('SPAN', (0, team_header_idx), (-1, team_header_idx)),
            ('BACKGROUND', (0, team_header_idx), (-1, team_header_idx), colors.HexColor("#29AAE1")),
            ('ALIGN', (0, team_header_idx), (-1, team_header_idx), 'CENTER'),
        ])
        row_idx += 1

        # Fila de VALORES DE EQUIPO
        if team_row_vals:
            t_tiempo, t_dt, t_vmax, t_hsr, t_spm, t_spr, t_acc, t_dcc = team_row_vals
        else:
            t_tiempo, t_dt, t_vmax, t_hsr, t_spm, t_spr, t_acc, t_dcc = ("95' (Media)", "119.36 KM", "31.57 KM/H", "2.347 KM", "-", "-", "-", "-")

        team_data_row = [
            "", "",
            Paragraph(f"<b>{t_tiempo}</b>", cell_bold),
            Paragraph(f"<b>{t_dt}</b>", cell_bold),
            Paragraph(f"<b>{t_vmax}</b>", cell_bold),
            Paragraph(f"<b>{t_hsr}</b>", cell_bold),
            Paragraph(f"<b>{t_spm}</b>", cell_bold),
            Paragraph(f"<b>{t_spr}</b>", cell_bold),
            Paragraph(f"<b>{t_acc}</b>", cell_bold),
            Paragraph(f"<b>{t_dcc}</b>", cell_bold),
        ]
        table_data.append(team_data_row)
        team_data_idx = row_idx
        table_styles.extend([
            ('SPAN', (0, team_data_idx), (1, team_data_idx)),
            ('BACKGROUND', (0, team_data_idx), (-1, team_data_idx), colors.HexColor("#E0F2FE")),
        ])
    else:
        # Formato Oficial P.F. (6 Roles): Idéntico al Excel con columna lateral de bloque
        headers = [
            "BLOQUE", "POSICIÓN", "JUGADOR", "TIEMPO", "DISTANCIA\nTOTAL (km)",
            "VELOCIDAD\nMAX (km/h)", "HSR (m)", "METROS EN\nSPRINT", "#SPRINTS",
            "#ACC EXPL", "#DCC EXPL"
        ]
        col_widths = [80, 75, 95, 75, 75, 75, 60, 80, 55, 55, 55]
        header_row = [Paragraph(f"<b>{h}</b>", cell_bold) for h in headers]
        table_data = [header_row]

        for p_tuple in player_rows:
            pos, jug, tiempo, dt, vmax, hsr, sp_m, sprints, acc, dcc, r_type = p_tuple
            is_top = (r_type == "top" or "TOP" in pos or "⭐" in pos)
            pos_clean = pos.replace("⭐", "").strip()

            row_content = [
                Paragraph(f"<b>{short_block_name}</b>", cell_bold) if row_idx == 1 else "",
                Paragraph(f"<b>{pos_clean}</b>", cell_white if is_top else cell_bold),
                Paragraph(f"<b>{jug}</b>" if is_top else jug, cell_white if is_top else cell_style),
                Paragraph(tiempo, cell_white if is_top else cell_style),
                Paragraph(dt, cell_white if is_top else cell_style),
                Paragraph(vmax, cell_white if is_top else cell_style),
                Paragraph(hsr, cell_white if is_top else cell_style),
                Paragraph(sp_m, cell_white if is_top else cell_style),
                Paragraph(sprints, cell_white if is_top else cell_style),
                Paragraph(acc, cell_white if is_top else cell_style),
                Paragraph(dcc, cell_white if is_top else cell_style),
            ]
            table_data.append(row_content)

            if is_top:
                table_styles.append(('BACKGROUND', (1, row_idx), (-1, row_idx), colors.HexColor("#D9534F")))
            elif "EXTREMO" in pos_clean or "CELLOU" in jug.upper():
                table_styles.append(('BACKGROUND', (6, row_idx), (6, row_idx), colors.HexColor("#FFF2CC")))

            row_idx += 1

        team_title_p = Paragraph("<b>DATOS REFERENCIA GENERALES EQUIPO</b>", cell_white)
        team_header_row = ["", team_title_p, "", "", "", "", "", "", "", "", ""]
        table_data.append(team_header_row)
        team_header_idx = row_idx
        table_styles.extend([
            ('SPAN', (1, team_header_idx), (-1, team_header_idx)),
            ('BACKGROUND', (1, team_header_idx), (-1, team_header_idx), colors.HexColor("#29AAE1")),
            ('ALIGN', (1, team_header_idx), (-1, team_header_idx), 'CENTER'),
        ])
        row_idx += 1

        if team_row_vals:
            t_tiempo, t_dt, t_vmax, t_hsr, t_spm, t_spr, t_acc, t_dcc = team_row_vals
        else:
            t_tiempo, t_dt, t_vmax, t_hsr, t_spm, t_spr, t_acc, t_dcc = ("95' (Media)", "119.36 KM", "31.57 KM/H", "2.347 KM", "-", "-", "-", "-")

        team_data_row = [
            "", "", "",
            Paragraph(f"<b>{t_tiempo}</b>", cell_bold),
            Paragraph(f"<b>{t_dt}</b>", cell_bold),
            Paragraph(f"<b>{t_vmax}</b>", cell_bold),
            Paragraph(f"<b>{t_hsr}</b>", cell_bold),
            Paragraph(f"<b>{t_spm}</b>", cell_bold),
            Paragraph(f"<b>{t_spr}</b>", cell_bold),
            Paragraph(f"<b>{t_acc}</b>", cell_bold),
            Paragraph(f"<b>{t_dcc}</b>", cell_bold),
        ]
        table_data.append(team_data_row)
        team_data_idx = row_idx
        table_styles.extend([
            ('BACKGROUND', (1, team_data_idx), (-1, team_data_idx), colors.HexColor("#E0F2FE")),
            ('SPAN', (0, 1), (0, -1)),
            ('BACKGROUND', (0, 1), (0, -1), colors.HexColor("#9BB4C9")),
            ('TEXTCOLOR', (0, 1), (0, -1), colors.HexColor("#0F172A")),
        ])

    t = Table(table_data, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle(table_styles))
    elements.append(t)

    doc.build(elements)
    buffer.seek(0)
    return buffer.getvalue()


def _generate_html_pdf_fallback(match_title: str, df_rows: pd.DataFrame, season_title: str) -> bytes:
    """Fallback si reportlab no estuviera cargado: genera un HTML imprimible con estilos directos."""
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>{season_title}</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 15px; font-size: 11px; }}
            h2 {{ text-align: center; background: #f1f5f9; padding: 8px; border: 1px solid #334155; margin-bottom: 10px; font-size: 13px; }}
            table {{ width: 100%; border-collapse: collapse; text-align: center; }}
            th, td {{ border: 1px solid #334155; padding: 5px; }}
            th {{ background: #e2e8f0; font-size: 10px; }}
            .match-block {{ background: #9bb4c9; font-weight: bold; width: 85px; }}
            .top-row {{ background: #d9534f; color: white; font-weight: bold; }}
            .team-bar {{ background: #29aae1; color: white; font-weight: bold; }}
            .team-vals {{ background: #e0f2fe; font-weight: bold; }}
            .gold {{ background: #fff2cc; }}
        </style>
    </head>
    <body>
        <h2>{season_title}</h2>
        <table>
            <thead>
                <tr>
                    <th>BLOQUE</th>
                    <th>POSICIÓN</th>
                    <th>JUGADOR</th>
                    <th>TIEMPO</th>
                    <th>DISTANCIA TOTAL</th>
                    <th>VELOCIDAD MAX</th>
                    <th>HSR</th>
                    <th>METROS EN SPRINT</th>
                    <th>#SPRINTS</th>
                    <th>#ACC EXPL</th>
                    <th>#DCC EXPL</th>
                </tr>
            </thead>
            <tbody>
    """
    for _, r in df_rows.iterrows():
        pos = r.get("POSICIÓN", "")
        jug = r.get("JUGADOR", "")
        r_type = r.get("_row_type", "")
        row_class = "top-row" if r_type == "top" or "TOP" in str(pos) else ""
        html += f"""
        <tr class="{row_class}">
            <td>{match_title}</td>
            <td><b>{pos}</b></td>
            <td>{jug}</td>
            <td>{r.get('TIEMPO', '')}</td>
            <td>{r.get('DISTANCIA TOTAL (km)', '')}</td>
            <td>{r.get('VELOCIDAD MAX (km/h)', '')}</td>
            <td>{r.get('HSR (m)', '')}</td>
            <td>{r.get('METROS EN SPRINT', '')}</td>
            <td>{r.get('#SPRINTS', '')}</td>
            <td>{r.get('#ACC EXPL', '')}</td>
            <td>{r.get('#DCC EXPL', '')}</td>
        </tr>
        """
    html += "</tbody></table></body></html>"
    return html.encode("utf-8")



def generate_weekly_microcycle_pdf(summary: Dict[str, Any]) -> bytes:
    """
    Genera un informe semanal en formato PDF vectorial (A4) a partir del resumen del microciclo.
    Devuelve los bytes del archivo PDF listos para descarga mediante Streamlit.
    """
    import io
    from datetime import date
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import (
        SimpleDocTemplate,
        Paragraph,
        Table,
        TableStyle,
        Spacer,
        HRFlowable
    )

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=36,
        rightMargin=36,
        topMargin=36,
        bottomMargin=36
    )

    styles = getSampleStyleSheet()

    # Estilos tipográficos personalizados
    title_style = ParagraphStyle(
        "DocTitle",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=18,
        leading=22,
        textColor=colors.HexColor("#0F172A"),
        spaceAfter=4
    )

    subtitle_style = ParagraphStyle(
        "DocSubtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=10,
        leading=14,
        textColor=colors.HexColor("#475569"),
        spaceAfter=12
    )

    h2_style = ParagraphStyle(
        "SectionHeader",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=16,
        textColor=colors.HexColor("#0284C7"),
        spaceBefore=12,
        spaceAfter=6
    )

    cell_style = ParagraphStyle(
        "TableCell",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor("#1E293B")
    )

    cell_bold = ParagraphStyle(
        "TableCellBold",
        parent=cell_style,
        fontName="Helvetica-Bold"
    )

    cell_header = ParagraphStyle(
        "TableHeader",
        parent=cell_style,
        fontName="Helvetica-Bold",
        textColor=colors.white
    )

    story = []

    start_d = summary.get("start_date")
    end_d = summary.get("end_date")
    start_str = start_d.strftime("%d/%m/%Y") if isinstance(start_d, date) else str(start_d)
    end_str = end_d.strftime("%d/%m/%Y") if isinstance(end_d, date) else str(end_d)
    team_kpis = summary.get("team_kpis", {})
    breakdown = summary.get("sessions_breakdown", [])
    optimal = summary.get("optimal_players", [])
    deficit = summary.get("deficit_players", [])
    fatigue = summary.get("fatigue_alerts", [])
    all_players = summary.get("all_players", [])

    # 1. Cabecera Institucional
    header_data = [
        [
            Paragraph("<b>SALERM COSMETICS PUENTE GENIL F.C.</b><br/><font size=8 color='#64748B'>Departamento de Preparación Física & Telemetría UBIKO</font>", cell_style),
            Paragraph(f"<para align='right'><b>INFORME TÉCNICO SEMANAL</b><br/><font size=8 color='#64748B'>Microciclo: {start_str} al {end_str}</font></para>", cell_style)
        ]
    ]
    header_table = Table(header_data, colWidths=[280, 240])
    header_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(header_table)
    story.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor("#0284C7"), spaceAfter=14))

    # 2. Tarjetas / Tabla Resumen de KPIs de Equipo
    kpi_data = [
        [
            Paragraph("<font size=7 color='#64748B'>DISTANCIA MEDIA</font><br/><b>" + f"{team_kpis.get('team_mean_distance_km', 0.0):.2f} km</b>", cell_style),
            Paragraph("<font size=7 color='#64748B'>HSR MEDIO (>21 km/h)</font><br/><b>" + f"{team_kpis.get('team_mean_hsr_m', 0.0):.0f} m</b>", cell_style),
            Paragraph("<font size=7 color='#64748B'>CARGA NEUROMUSCULAR</font><br/><b>" + f"{team_kpis.get('team_mean_eff', 0)} AC.E</b>", cell_style),
            Paragraph("<font size=7 color='#64748B'>SESIONES / MINUTOS</font><br/><b>" + f"{team_kpis.get('num_sessions', 0)} ({team_kpis.get('total_team_duration', 0)}')</b>", cell_style),
        ]
    ]
    kpi_table = Table(kpi_data, colWidths=[130, 130, 130, 130])
    kpi_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F1F5F9")),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#CBD5E1")),
        ("INNERGRID", (0, 0), (-1, -1), 1, colors.HexColor("#E2E8F0")),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(kpi_table)
    story.append(Spacer(1, 12))

    # 3. Sesiones del Microciclo (Desglose diario)
    if breakdown:
        story.append(Paragraph("1. Desglose Diario del Microciclo", h2_style))
        sess_rows = [
            [
                Paragraph("Fecha", cell_header),
                Paragraph("Día", cell_header),
                Paragraph("Tipo", cell_header),
                Paragraph("Dur.", cell_header),
                Paragraph("DT Med.", cell_header),
                Paragraph("HSR Med.", cell_header),
                Paragraph("AC.E", cell_header),
                Paragraph("Estímulo Principal / Tarea", cell_header)
            ]
        ]
        for s in breakdown:
            f_str = s["date"].strftime("%d/%m") if isinstance(s["date"], date) else str(s["date"])
            sess_rows.append([
                Paragraph(f_str, cell_bold),
                Paragraph(s.get("microcycle_day", ""), cell_style),
                Paragraph(s.get("session_type", ""), cell_style),
                Paragraph(f"{s.get('duration', 0)}'", cell_style),
                Paragraph(f"{s.get('mean_td_km', 0.0):.2f}k", cell_bold),
                Paragraph(f"{s.get('mean_hsr_m', 0.0):.0f}m", cell_style),
                Paragraph(f"{s.get('mean_eff', 0):.0f}", cell_style),
                Paragraph(s.get("stimulus", "")[:36], cell_style)
            ])

        sess_table = Table(sess_rows, colWidths=[42, 45, 60, 35, 48, 50, 40, 200])
        sess_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E293B")),
            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(sess_table)
        story.append(Spacer(1, 14))

    # 4. Tabla de Cumplimiento Jugador por Jugador
    story.append(Paragraph("2. Control de Cumplimiento Individual de la Plantilla", h2_style))
    story.append(Paragraph(
        "Contraste del volumen y la intensidad acumulada de cada futbolista respecto al plan del microciclo (MD-4 a MD+1).",
        subtitle_style
    ))

    p_rows = [
        [
            Paragraph("Dor.", cell_header),
            Paragraph("Futbolista", cell_header),
            Paragraph("Pos.", cell_header),
            Paragraph("Min.", cell_header),
            Paragraph("Dist. (km)", cell_header),
            Paragraph("HSR (m)", cell_header),
            Paragraph("AC.E", cell_header),
            Paragraph("ACWR", cell_header),
            Paragraph("Estado de Cumplimiento", cell_header)
        ]
    ]

    player_dict = {}
    for p in all_players:
        player_dict[p["player_id"]] = dict(p)
    for p in optimal:
        if p["player_id"] not in player_dict:
            player_dict[p["player_id"]] = dict(p)
        player_dict[p["player_id"]]["status_group"] = "OPTIMO"
    for p in deficit:
        if p["player_id"] not in player_dict:
            player_dict[p["player_id"]] = dict(p)
        player_dict[p["player_id"]]["status_group"] = "DEFICIT"
    for p in fatigue:
        if p["player_id"] not in player_dict:
            player_dict[p["player_id"]] = dict(p)
        player_dict[p["player_id"]]["status_group"] = "SOBRECARGA"

    sorted_players = sorted(player_dict.values(), key=lambda x: int(x.get("dorsal", 99)))

    for p in sorted_players:
        dor = str(p.get("dorsal", ""))
        name = p.get("name", "Jugador")
        pos = p.get("position", "")
        mins = f"{p.get('tot_mins', 0):.0f}'"
        km = f"{p.get('tot_km', 0.0):.1f}k"
        hsr = f"{p.get('tot_hsr', 0.0):.0f}m"
        eff = str(p.get("tot_eff", 0))
        acwr_val = p.get("acwr")
        acwr_str = f"{acwr_val:.2f}" if acwr_val is not None else "N/D"

        st_group = p.get("status_group", "")
        if not st_group:
            if acwr_val is not None and acwr_val > 1.35:
                st_group = "SOBRECARGA"
            elif p.get("tot_mins", 0) < 120:
                st_group = "DEFICIT"
            else:
                st_group = "OPTIMO"

        if st_group == "SOBRECARGA":
            status_cell = Paragraph("<font color='#DC2626'><b>🔴 SOBRECARGA</b></font><br/><font size=7 color='#64748B'>Alerta fatiga / dosificar</font>", cell_style)
        elif st_group == "DEFICIT":
            status_cell = Paragraph("<font color='#D97706'><b>🟡 DÉFICIT</b></font><br/><font size=7 color='#64748B'>Compensatorio necesario</font>", cell_style)
        else:
            status_cell = Paragraph("<font color='#16A34A'><b>🟢 EN OBJETIVO</b></font><br/><font size=7 color='#64748B'>Rango óptimo microciclo</font>", cell_style)

        p_rows.append([
            Paragraph(f"#{dor}", cell_bold),
            Paragraph(name, cell_bold),
            Paragraph(pos, cell_style),
            Paragraph(mins, cell_style),
            Paragraph(km, cell_style),
            Paragraph(hsr, cell_style),
            Paragraph(eff, cell_style),
            Paragraph(acwr_str, cell_style),
            status_cell
        ])

    player_table = Table(p_rows, colWidths=[30, 95, 55, 35, 50, 50, 40, 42, 123])
    player_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0284C7")),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(player_table)
    story.append(Spacer(1, 14))

    # 5. Directrices y Prescripciones Técnicas
    if fatigue or deficit:
        story.append(Paragraph("3. Prescripciones Técnicas para el Cuerpo Técnico", h2_style))
        alert_items = []
        if fatigue:
            for p in fatigue[:3]:
                alert_items.append(Paragraph(f"• <b>Alerta #{p['dorsal']} {p['name']}</b>: {p.get('alert_reasons', 'Fatiga acumulada')}. Recomendación: {p.get('recommendation', 'Dosificar minutos.')}", cell_style))
        if deficit:
            for p in deficit[:3]:
                alert_items.append(Paragraph(f"• <b>Compensatorio #{p['dorsal']} {p['name']}</b>: {p.get('deficit_reasons', 'Baja exposición')}. Tarea sugerida: {p.get('compensatory_plan', 'Estimular sprints y HSR.')}", cell_style))

        if alert_items:
            alert_table = Table([[item] for item in alert_items], colWidths=[520])
            alert_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FFFBEB")),
                ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#FCD34D")),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ]))
            story.append(alert_table)
            story.append(Spacer(1, 14))

    # 6. Pie de Página y Firma Técnica
    footer_text = Paragraph(
        f"<para align='center'><font size=7 color='#94A3B8'>Documento generado automáticamente por UBIKO Performance Hub | Salerm Cosmetics Puente Genil F.C.<br/>Universidad de Córdoba - Trabajo de Fin de Grado en Ingeniería Informática</font></para>",
        cell_style
    )
    story.append(Spacer(1, 8))
    story.append(footer_text)

    # Construir documento
    doc.build(story)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes
