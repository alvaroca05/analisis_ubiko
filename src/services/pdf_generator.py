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
