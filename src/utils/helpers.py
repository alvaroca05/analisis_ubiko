"""
Funciones auxiliares para formateo de datos, semáforos visuales y generación de gráficos interactivos con Plotly.
"""

from typing import Optional
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


def render_badge(text: str, color_hex: str) -> str:
    """
    Genera un badge HTML estilizado para usar en tablas o métricas de Streamlit.
    """
    return (
        f'<span style="background-color: {color_hex}22; color: {color_hex}; '
        f'padding: 3px 10px; border-radius: 12px; font-weight: 600; '
        f'border: 1px solid {color_hex}66; font-size: 0.85rem;">'
        f'{text}</span>'
    )


def render_semaforo_legend_html() -> str:
    """
    Retorna el bloque HTML estilizado de la leyenda del semáforo fisiológico (ACWR y riesgo lesional).
    """
    return """
    <div style="background: linear-gradient(135deg, #1E293B 0%, #0F172A 100%); border: 1px solid #334155; border-radius: 10px; padding: 12px 14px; margin: 10px 0 14px 0;">
        <div style="display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; margin-bottom: 8px; border-bottom: 1px solid #334155; padding-bottom: 6px; gap: 4px;">
            <span style="font-weight: 700; color: #F8FAFC; font-size: 0.90rem; display: flex; align-items: center; gap: 6px;">
                🚦 <b>Leyenda del Semáforo Fisiológico</b>
            </span>
            <span style="font-size: 0.72rem; color: #94A3B8;">Modelo ACWR EWMA (Gabbett & Williams)</span>
        </div>
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 8px; font-size: 0.78rem;">
            <div style="background: rgba(59, 130, 246, 0.12); border-left: 3px solid #3B82F6; padding: 6px 10px; border-radius: 6px;">
                <b style="color: #60A5FA; font-size: 0.82rem;">🔵 Subentrenamiento (&lt; 0.80)</b><br>
                <span style="color: #CBD5E1;">Carga insuficiente. Riesgo de desadaptación.</span>
            </div>
            <div style="background: rgba(16, 185, 129, 0.12); border-left: 3px solid #10B981; padding: 6px 10px; border-radius: 6px;">
                <b style="color: #34D399; font-size: 0.82rem;">🟢 Óptimo (0.80 - 1.30)</b><br>
                <span style="color: #CBD5E1;">Zona segura y óptima de rendimiento.</span>
            </div>
            <div style="background: rgba(245, 158, 11, 0.12); border-left: 3px solid #F59E0B; padding: 6px 10px; border-radius: 6px;">
                <b style="color: #FBBF24; font-size: 0.82rem;">🟡 Precaución (1.30 - 1.50)</b><br>
                <span style="color: #CBD5E1;">Fatiga acumulada. Vigilar recuperación.</span>
            </div>
            <div style="background: rgba(239, 68, 68, 0.12); border-left: 3px solid #EF4444; padding: 6px 10px; border-radius: 6px;">
                <b style="color: #F87171; font-size: 0.82rem;">🔴 Peligro / Sobrecarga (&gt; 1.50)</b><br>
                <span style="color: #CBD5E1;">Riesgo alto de lesión. Rotación recomendada.</span>
            </div>
        </div>
    </div>
    """


def create_acwr_longitudinal_chart(df_acwr: pd.DataFrame, player_name: str) -> go.Figure:
    """
    Crea un gráfico interactivo con Plotly de Carga Aguda, Crónica y ratio ACWR con bandas de riesgo.
    """
    if df_acwr.empty:
        fig = go.Figure()
        fig.update_layout(title="Sin datos disponibles para el jugador.")
        return fig

    # Subplots: Superior = Carga Aguda/Crónica y Carga Diaria | Inferior = Ratio ACWR
    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.10,
        subplot_titles=(
            f"Evolución de Cargas de Trabajo (EWMA) - {player_name}",
            "Ratio de Carga Aguda / Crónica (ACWR)"
        ),
        row_heights=[0.6, 0.4]
    )

    # Panel Superior: Barras de Carga Diaria
    fig.add_trace(
        go.Bar(
            x=df_acwr["date"],
            y=df_acwr["load_value"],
            name="Carga Sesión (m)",
            marker_color="rgba(156, 163, 175, 0.4)",
            opacity=0.6
        ),
        row=1, col=1
    )

    # Carga Aguda (EWMA 7d)
    fig.add_trace(
        go.Scatter(
            x=df_acwr["date"],
            y=df_acwr["acute_ewma"],
            name="Carga Aguda (EWMA 7d)",
            mode="lines+markers",
            line=dict(color="#3B82F6", width=2.5),
            marker=dict(size=4)
        ),
        row=1, col=1
    )

    # Carga Crónica (EWMA 28d)
    fig.add_trace(
        go.Scatter(
            x=df_acwr["date"],
            y=df_acwr["chronic_ewma"],
            name="Carga Crónica (EWMA 28d)",
            mode="lines",
            line=dict(color="#10B981", width=2.5, dash="dash")
        ),
        row=1, col=1
    )

    # Panel Inferior: Curva de ACWR
    fig.add_trace(
        go.Scatter(
            x=df_acwr["date"],
            y=df_acwr["acwr"],
            name="ACWR",
            mode="lines+markers",
            line=dict(color="#8B5CF6", width=2.5),
            marker=dict(
                size=6,
                color=[c for c in df_acwr["acwr_color"]]
            )
        ),
        row=2, col=1
    )

    # Bandas de referencia en ACWR
    start_date = df_acwr["date"].min()
    end_date = df_acwr["date"].max()

    # Banda Verde: Sweet Spot (0.80 - 1.30)
    fig.add_hrect(
        y0=0.80, y1=1.30,
        fillcolor="rgba(16, 185, 129, 0.15)",
        line_width=0,
        annotation_text="Sweet Spot (0.8 - 1.3)",
        annotation_position="top left",
        row=2, col=1
    )

    # Banda Amarilla: Precaución (1.30 - 1.50)
    fig.add_hrect(
        y0=1.30, y1=1.50,
        fillcolor="rgba(245, 158, 11, 0.15)",
        line_width=0,
        annotation_text="Precaución (1.3 - 1.5)",
        annotation_position="top left",
        row=2, col=1
    )

    # Banda Roja: Riesgo de sobrecarga (> 1.50)
    fig.add_hrect(
        y0=1.50, y1=2.50,
        fillcolor="rgba(239, 68, 68, 0.15)",
        line_width=0,
        annotation_text="Zona de Peligro (> 1.5)",
        annotation_position="top left",
        row=2, col=1
    )

    fig.update_layout(
        template="plotly_dark",
        autosize=True,
        height=540,
        margin=dict(l=20, r=20, t=50, b=30),
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(size=10))
    )

    fig.update_yaxes(title_text="Distancia (m)", row=1, col=1)
    fig.update_yaxes(title_text="Ratio ACWR", range=[0.3, 2.2], row=2, col=1)
    fig.update_xaxes(title_text="Fecha", row=2, col=1)

    return fig


def create_compliance_chart(df_compliance: pd.DataFrame) -> go.Figure:
    """
    Gráfico de barras agrupadas comparando métricas Reales vs Planificadas por posición.
    """
    if df_compliance.empty:
        return go.Figure()

    fig = go.Figure()

    # Distancia Total
    fig.add_trace(
        go.Bar(
            x=df_compliance["Posición"],
            y=df_compliance["DT Real (m)"],
            name="DT Real (m)",
            marker_color="#3B82F6"
        )
    )
    fig.add_trace(
        go.Bar(
            x=df_compliance["Posición"],
            y=df_compliance["DT Objetivo (m)"],
            name="DT Objetivo (m)",
            marker_color="#94A3B8"
        )
    )

    fig.update_layout(
        title="Distancia Total (DT): Real vs. Planificado por Demarcación",
        template="plotly_dark",
        autosize=True,
        barmode="group",
        height=360,
        margin=dict(l=20, r=20, t=40, b=30),
        yaxis_title="Metros",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(size=10))
    )

    return fig


def create_zscore_chart(df_metrics: pd.DataFrame, metric_col: str = "hsr_distance") -> go.Figure:
    """
    Gráfico de dispersión de Z-scores por posición para identificar outliers.
    """
    z_col = f"z_{metric_col}"
    if z_col not in df_metrics.columns:
        return go.Figure()

    metric_label = "HSR (>19.8 km/h)" if metric_col == "hsr_distance" else "Distancia Total"

    fig = go.Figure()

    for pos in df_metrics["position"].unique():
        sub = df_metrics[df_metrics["position"] == pos]
        fig.add_trace(
            go.Scatter(
                x=sub["player_name"],
                y=sub[z_col],
                mode="markers+text",
                name=pos,
                text=[f"#{d}" for d in sub["dorsal"]],
                textposition="top center",
                marker=dict(size=12, line=dict(width=1, color="white"))
            )
        )

    # Líneas de umbral Z-Score
    fig.add_hline(y=1.5, line_dash="dash", line_color="#EF4444", annotation_text="+1.5σ (Exceso)")
    fig.add_hline(y=-1.5, line_dash="dash", line_color="#EF4444", annotation_text="-1.5σ (Déficit)")
    fig.add_hline(y=0.0, line_dash="dot", line_color="#10B981")

    fig.update_layout(
        title=f"Z-Score Posicional de {metric_label} (Identificación de Desviaciones)",
        template="plotly_dark",
        autosize=True,
        height=380,
        yaxis_title="Z-Score (Desviaciones estándar)",
        xaxis_tickangle=-45,
        margin=dict(l=20, r=20, t=40, b=70),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(size=10))
    )

    return fig


def create_training_vs_match_chart(df_history: pd.DataFrame, peak_match_peak: Any, player_name: str) -> go.Figure:
    """
    Gráfico comparativo directo: Carga de Entrenamiento vs. Partido de Máxima Exigencia (100% individual).
    """
    if df_history.empty:
        return go.Figure()

    fig = go.Figure()

    # Separar entrenamientos y partidos
    df_train = df_history[df_history["session_type"] != "Partido"]
    df_match = df_history[df_history["session_type"] == "Partido"]

    # Barras de entrenamientos
    if not df_train.empty:
        fig.add_trace(
            go.Bar(
                x=pd.to_datetime(df_train["date"]),
                y=df_train["total_distance"],
                name="Entrenamiento (DT)",
                marker_color="#3B82F6",
                opacity=0.85
            )
        )

    # Barras de partidos
    if not df_match.empty:
        fig.add_trace(
            go.Bar(
                x=pd.to_datetime(df_match["date"]),
                y=df_match["total_distance"],
                name="Partido Oficial (DT)",
                marker_color="#10B981",
                opacity=0.95
            )
        )

    # Línea horizontal de Techo 100% del Partido de Máxima Exigencia
    if peak_match_peak and getattr(peak_match_peak, "peak_td", None):
        peak_val = float(peak_match_peak.peak_td)
        match_label = getattr(peak_match_peak, "peak_session_name", "Partido Máx. Exigencia")
        fig.add_hline(
            y=peak_val,
            line_dash="dash",
            line_color="#F59E0B",
            line_width=2.5,
            annotation_text=f"100% Partido Ref.: {peak_val:.0f}m ({match_label})",
            annotation_position="top left",
            annotation_font=dict(color="#FCD34D", size=11)
        )

    fig.update_layout(
        title=f"Comparativa Directa Entrenamiento vs. Partido - {player_name}",
        template="plotly_dark",
        autosize=True,
        barmode="group",
        height=380,
        yaxis_title="Distancia Total (m)",
        xaxis_title="Fecha",
        margin=dict(l=20, r=20, t=50, b=30),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(size=10))
    )

    return fig


def create_weekly_comparison_chart(df_history: pd.DataFrame, player_name: str) -> go.Figure:
    """
    Gráfico de evolución semanal: compara la carga acumulada (DT y HSR) por semana del año
    (Semana actual vs semanas anteriores).
    """
    if df_history.empty:
        return go.Figure()

    df = df_history.copy()
    df["date"] = pd.to_datetime(df["date"])
    df["semana"] = df["date"].dt.isocalendar().week
    df["año"] = df["date"].dt.isocalendar().year
    df["semana_label"] = "Semana " + df["semana"].astype(str)

    weekly = df.groupby(["año", "semana", "semana_label"]).agg({
        "total_distance": "sum",
        "hsr_distance": "sum",
        "acc_dec_eff": "sum"
    }).reset_index()

    fig = go.Figure()

    # Barras de DT semanal
    fig.add_trace(
        go.Bar(
            x=weekly["semana_label"],
            y=weekly["total_distance"],
            name="Distancia Total (m)",
            marker_color="#6366F1",
            yaxis="y1"
        )
    )

    # Línea de HSR semanal
    fig.add_trace(
        go.Scatter(
            x=weekly["semana_label"],
            y=weekly["hsr_distance"],
            name="HSR (>21 km/h) (m)",
            mode="lines+markers",
            line=dict(color="#EC4899", width=3),
            marker=dict(size=8),
            yaxis="y2"
        )
    )

    fig.update_layout(
        title=f"Evolución Entre Semanas (Semana Actual vs Anteriores) - {player_name}",
        template="plotly_dark",
        autosize=True,
        height=380,
        yaxis=dict(title="Distancia Total Semanal (m)"),
        yaxis2=dict(
            title="HSR Semanal (m)",
            overlaying="y",
            side="right",
            showgrid=False
        ),
        margin=dict(l=20, r=40, t=50, b=30),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(size=10))
    )

    return fig

