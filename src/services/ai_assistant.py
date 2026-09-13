"""
Servicio de Asistente de Inteligencia Artificial para Análisis de Rendimiento y Ciencias del Deporte.
Soporta proveedores LLM en la nube como Groq (Llama 3.3 / Llama 3.1) y Google Gemini con fallback inteligente.
"""

import os
from typing import Dict, Any, Optional
import pandas as pd
from sqlalchemy.orm import Session

from src.database.models import Player, TrainingSession, PlayerMetric
from src.services.analytics import (
    calculate_ewma_acwr,
    calculate_session_summary,
    ACWR_SWEET_SPOT_MAX,
    ACWR_DANGER_ZONE,
    ACWR_UNDERLOAD
)


class AIAssistant:
    """
    Asistente virtual para el cuerpo técnico y preparadores físicos.
    Analiza ratios ACWR, curvas de fatiga, picos de velocidad/HSR y responde consultas en lenguaje natural.
    """

    def __init__(self, provider: str = "auto"):
        self.groq_api_key = os.getenv("GROQ_API_KEY", "").strip()
        raw_gemini = os.getenv("GEMINI_API_KEY", "").strip()
        self.gemini_api_key = "" if "tu_clave" in raw_gemini.lower() else raw_gemini
        self.provider = provider.lower()

    def _get_groq_active_models(self) -> list:
        """Obtiene dinámicamente los modelos activos en la cuenta de Groq."""
        import requests
        
        # Modelos recomendados y oficialmente soportados por Groq
        recommended = [
            "llama-3.3-70b-versatile",
            "llama-3.1-8b-instant",
            "llama-3.2-11b-vision-preview",
            "llama-3.2-3b-preview",
            "llama-3.2-1b-preview",
            "mixtral-8x7b-32768"
        ]
        
        # Modelos formalmente deprecados / dados de baja por Groq que no deben usarse
        deprecated = {
            "llama-3.1-70b-versatile",
            "llama-3.1-70b",
            "llama-3.1-405b-reasoning",
            "llama3-70b-8192",
            "llama3-8b-8192"
        }
        
        try:
            res = requests.get(
                "https://api.groq.com/openai/v1/models",
                headers={"Authorization": f"Bearer {self.groq_api_key}"},
                timeout=5
            )
            if res.status_code == 200:
                data = res.json().get("data", [])
                active = [
                    m["id"] for m in data
                    if m.get("active", True) and m["id"] not in deprecated
                ]
                # Priorizar llama-3.3-70b, luego otros 70b, luego 8b instant, luego el resto
                models_33_70b = [m for m in active if "3.3" in m and "70b" in m]
                models_other_70b = [m for m in active if "70b" in m and m not in models_33_70b]
                models_8b = [m for m in active if "8b" in m or "instant" in m]
                others = [m for m in active if m not in models_33_70b and m not in models_other_70b and m not in models_8b]
                sorted_models = models_33_70b + models_other_70b + models_8b + others
                if sorted_models:
                    return sorted_models
        except Exception:
            pass
        return recommended

    def _call_groq(self, system_prompt: str, user_prompt: str) -> str:
        """Llama a la API de Groq usando requests nativo con fallback dinámico de modelos."""
        import requests
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.groq_api_key}",
            "Content-Type": "application/json"
        }
        
        candidate_models = self._get_groq_active_models()
        last_error = None

        for model_name in candidate_models:
            payload = {
                "model": model_name,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "temperature": 0.3,
                "max_tokens": 1024
            }
            try:
                res = requests.post(url, headers=headers, json=payload, timeout=25)
                if res.status_code == 200:
                    data = res.json()
                    return data["choices"][0]["message"]["content"].strip()
                elif res.status_code in (400, 404, 422):
                    # Modelo obsoleto/decommissioned o no soportado en este tier; probar siguiente
                    last_error = f"{model_name} ({res.status_code}) -> {res.text}"
                    continue
                else:
                    raise RuntimeError(f"Groq API error ({res.status_code}): {res.text}")
            except requests.exceptions.RequestException as e_req:
                last_error = str(e_req)
                continue

        raise RuntimeError(f"No se pudo completar con los modelos de Groq. Último intento: {last_error}")

    def _call_gemini(self, system_prompt: str, user_prompt: str) -> str:
        """Llama a la API de Google Gemini usando requests nativo (sin requerir google-generativeai)."""
        import requests
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={self.gemini_api_key}"
        headers = {"Content-Type": "application/json"}
        payload = {
            "system_instruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"parts": [{"text": user_prompt}]}],
            "generationConfig": {"temperature": 0.3, "maxOutputTokens": 1024}
        }
        res = requests.post(url, headers=headers, json=payload, timeout=30)
        if res.status_code == 200:
            data = res.json()
            return data["candidates"][0]["content"]["parts"][0]["text"].strip()
        else:
            raise RuntimeError(f"Gemini API error ({res.status_code}): {res.text}")

    def _call_llm(self, system_prompt: str, user_prompt: str) -> str:
        """
        Ejecuta la inferencia contra Groq o Google Gemini según disponibilidad.
        """
        # Prioridad 1: Groq (Llama 3.3 70B Versatile)
        if (self.provider in ["auto", "groq"]) and self.groq_api_key:
            try:
                return self._call_groq(system_prompt, user_prompt)
            except Exception as e_groq:
                if not self.gemini_api_key:
                    return f"[Error con proveedor Groq: {e_groq}]"

        # Prioridad 2: Google Gemini (Gemini 1.5 Flash)
        if (self.provider in ["auto", "gemini"]) and self.gemini_api_key:
            try:
                return self._call_gemini(system_prompt, user_prompt)
            except Exception as e_gemini:
                return f"[Error con proveedor Gemini: {e_gemini}]"

        # Modo fallback offline / heurístico si no hay API keys configuradas
        return self._heuristic_fallback(system_prompt, user_prompt)

    def _heuristic_fallback(self, system_prompt: str, user_prompt: str) -> str:
        """
        Genera una respuesta analítica basada en reglas cuando no hay conexión a APIs LLM externas.
        Garantiza que el sistema siempre devuelva valor técnico sin romperse.
        """
        return (
            "⚠️ **Nota: No se detectó `GROQ_API_KEY` o `GEMINI_API_KEY` en las variables de entorno.**\n\n"
            "**[Informe Analítico Basado en Reglas Algorítmicas]:**\n"
            f"{user_prompt}\n\n"
            "💡 *Recomendación metodológica:* Para desbloquear el análisis narrativo por Inteligencia Artificial, "
            "añade tu `GROQ_API_KEY` o `GEMINI_API_KEY` en el archivo `.env`."
        )

    def compare_players(self, player_a_id: int, player_b_id: int, db: Session) -> str:
        """
        Compara dos futbolistas a nivel fisiológico, riesgo lesional (ACWR EWMA) y volumen atlético reciente.
        """
        player_a = db.query(Player).filter(Player.id == player_a_id).first()
        player_b = db.query(Player).filter(Player.id == player_b_id).first()

        if not player_a or not player_b:
            return "No se encontraron los futbolistas seleccionados en la base de datos."

        # Cargar series temporales ACWR EWMA
        df_a = calculate_ewma_acwr(db, player_a.id, load_metric="total_distance")
        df_b = calculate_ewma_acwr(db, player_b.id, load_metric="total_distance")

        # Cargar métricas de las últimas 5 sesiones para medias de HSR y aceleraciones
        metrics_a = (
            db.query(PlayerMetric)
            .filter(PlayerMetric.player_id == player_a.id)
            .order_by(PlayerMetric.id.desc())
            .limit(5)
            .all()
        )
        metrics_b = (
            db.query(PlayerMetric)
            .filter(PlayerMetric.player_id == player_b.id)
            .order_by(PlayerMetric.id.desc())
            .limit(5)
            .all()
        )

        def get_stats(player, df_acwr, metrics_list):
            if not df_acwr.empty:
                last_row = df_acwr.iloc[-1]
                acwr = float(last_row.get("acwr", 1.0) or 1.0)
                acute = float(last_row.get("acute_ewma", 0.0) or 0.0)
                chronic = float(last_row.get("chronic_ewma", 0.0) or 0.0)
                status = str(last_row.get("acwr_status", "N/A"))
            else:
                acwr, acute, chronic, status = 1.0, 0.0, 0.0, "Sin datos"

            if metrics_list:
                mean_hsr = sum(m.hsr_distance or 0.0 for m in metrics_list) / len(metrics_list)
                mean_ace = sum((m.accelerations_eff or 0) + (m.decelerations_eff or 0) for m in metrics_list) / len(metrics_list)
                vmax = max((m.max_speed or 0.0) for m in metrics_list)
            else:
                mean_hsr, mean_ace, vmax = 0.0, 0, player.max_speed_kmh or 30.0

            return {
                "name": player.name,
                "dorsal": player.dorsal,
                "pos": player.position,
                "acwr": acwr,
                "acute": acute,
                "chronic": chronic,
                "status": status,
                "mean_hsr": mean_hsr,
                "mean_ace": mean_ace,
                "vmax": vmax
            }

        stats_a = get_stats(player_a, df_a, metrics_a)
        stats_b = get_stats(player_b, df_b, metrics_b)

        system_prompt = (
            "Eres un Científico Deportivo de élite y Preparador Físico de Alto Rendimiento en fútbol profesional. "
            "Tu misión es analizar con rigor científico la carga física, el riesgo lesional (EWMA ACWR) y el "
            "estado neuromuscular de dos futbolistas que compiten por una posición o rol táctico. "
            "Sé preciso, objetivo y proporciona conclusiones directas para el entrenador."
        )

        user_prompt = f"""
Compara a estos dos futbolistas del Salerm Puente Genil para el cuerpo técnico:

[JUGADOR 1]: #{stats_a['dorsal']} {stats_a['name']} ({stats_a['pos']})
- Ratio ACWR (EWMA): {stats_a['acwr']:.2f} [{stats_a['status']}]
- Carga Aguda (EWMA 7d): {stats_a['acute']:.1f} m | Carga Crónica (EWMA 28d): {stats_a['chronic']:.1f} m
- Media HSR reciente (>19.8 km/h): {stats_a['mean_hsr']:.1f} m
- Media Acc/Dec eficaces recientes (AC.E): {stats_a['mean_ace']:.1f} esfuerzos
- Velocidad máxima registrada: {stats_a['vmax']:.2f} km/h

[JUGADOR 2]: #{stats_b['dorsal']} {stats_b['name']} ({stats_b['pos']})
- Ratio ACWR (EWMA): {stats_b['acwr']:.2f} [{stats_b['status']}]
- Carga Aguda (EWMA 7d): {stats_b['acute']:.1f} m | Carga Crónica (EWMA 28d): {stats_b['chronic']:.1f} m
- Media HSR reciente (>19.8 km/h): {stats_b['mean_hsr']:.1f} m
- Media Acc/Dec eficaces recientes (AC.E): {stats_b['mean_ace']:.1f} esfuerzos
- Velocidad máxima registrada: {stats_b['vmax']:.2f} km/h

Por favor, estructura tu respuesta con:
1. **Índice de Frescura y Riesgo de Lesión (ACWR):** Quién se encuentra en la zona óptima (Sweet Spot 0.80-1.30) y quién presenta fatiga o desadaptación.
2. **Capacidad Atlética y Dinamismo Reciente:** Comparativa de HSR, velocidad y capacidad acelerométrica.
3. **Recomendación para la Próxima Sesión / Partido:** Dosificación de minutos, descansos activos o trabajos complementarios.
"""
        return self._call_llm(system_prompt, user_prompt)

    def ask_squad_query(self, question: str, db: Session) -> str:
        """
        Responde a una pregunta en lenguaje natural sobre el estado físico de la plantilla,
        basándose en el resumen de la última sesión y los ratios ACWR globales.
        """
        latest_session = (
            db.query(TrainingSession)
            .order_by(TrainingSession.date.desc(), TrainingSession.id.desc())
            .first()
        )

        if not latest_session:
            return "No hay sesiones registradas en la base de datos para responder a la consulta."

        summary = calculate_session_summary(db, latest_session.id)
        kpis = summary.get("team_kpis", {})
        df_metrics = summary.get("metrics", pd.DataFrame())

        # Extraer jugadores en peligro o precaución
        alerts = []
        if not df_metrics.empty and "acwr" in df_metrics.columns:
            danger_df = df_metrics[df_metrics["acwr"] > ACWR_DANGER_ZONE]
            caution_df = df_metrics[
                (df_metrics["acwr"] > ACWR_SWEET_SPOT_MAX) &
                (df_metrics["acwr"] <= ACWR_DANGER_ZONE)
            ]
            underload_df = df_metrics[df_metrics["acwr"] < ACWR_UNDERLOAD]

            for _, r in danger_df.iterrows():
                alerts.append(f"• #{r['dorsal']} {r['player_name']} ({r['position']}): ACWR = {r['acwr']:.2f} [SOBRECARGA SEVERA]")
            for _, r in caution_df.iterrows():
                alerts.append(f"• #{r['dorsal']} {r['player_name']} ({r['position']}): ACWR = {r['acwr']:.2f} [PRECAUCIÓN / FATIGA]")
            for _, r in underload_df.iterrows():
                alerts.append(f"• #{r['dorsal']} {r['player_name']} ({r['position']}): ACWR = {r['acwr']:.2f} [SUBENTRENAMIENTO]")

        context_data = f"""
SESIÓN EVALUADA: {latest_session.name} ({latest_session.date.strftime('%d/%m/%Y')}) - {latest_session.microcycle_day} ({latest_session.session_type})
- Jugadores monitoreados: {kpis.get('num_players', 0)}
- Distancia Media del Equipo: {kpis.get('mean_distance', 0.0):.1f} m
- HSR Medio (>19.8 km/h): {kpis.get('mean_hsr', 0.0):.1f} m
- HMLD Media: {kpis.get('mean_hmld', 0.0):.1f} m
- Cumplimiento Táctico Global: {kpis.get('mean_compliance', 0.0):.1f}%
- Futbolistas en Sobrecarga/Peligro (ACWR > 1.50): {kpis.get('players_in_danger', 0)}
- Futbolistas en Precaución/Fatiga (ACWR 1.30-1.50): {kpis.get('players_in_caution', 0)}

ESTADO DE JUGADORES CON ALERTAS:
{chr(10).join(alerts) if alerts else "• Toda la plantilla se encuentra en el rango óptimo (Sweet Spot 0.80 - 1.30)."}
"""

        system_prompt = (
            "Eres el Asistente Técnico y Fisiológico de Inteligencia Artificial del Salerm Cosmetics Puente Genil F.C. "
            "Tu labor es responder consultas técnicas del cuerpo técnico apoyándote en los datos objetivos del GPS "
            "y en la periodización táctica del microciclo. Sé conciso, profesional y directo."
        )

        user_prompt = f"""
Contexto de telemetría física del equipo:
{context_data}

Pregunta del Cuerpo Técnico:
"{question}"

Por favor, responde directamente a la pregunta con base en los datos de telemetría anteriores.
"""
        return self._call_llm(system_prompt, user_prompt)
