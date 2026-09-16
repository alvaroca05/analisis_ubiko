"""
Módulo de automatización web con Playwright para la plataforma UBIKO del Salerm Cosmetics Puente Genil.
Detecta automáticamente nuevas sesiones computadas, hace clic en el botón 'CSV' de la fila,
descarga el archivo consolidado, lo almacena en SQLite y genera el informe táctico completo.
"""

import os
import json
import time
from datetime import datetime, date
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
import pandas as pd

from src.config import DATA_DIR, SAMPLES_DIR
from src.database.connection import get_db, init_db
from src.database.models import TrainingSession
from src.services.importer import UbikoImporter
from src.services.analytics import calculate_session_summary
from src.services.report_generator import generate_tactical_report

# Archivo de sesión para guardar cookies y no tener que meter contraseñas cada vez
SESSION_STORAGE_PATH = DATA_DIR / "ubiko_session_auth.json"
DEFAULT_UBIKO_URL = "https://app.ubikosports.com"


class UbikoWebAutomator:
    """
    Automatización completa de UBIKO Web mediante Playwright.
    """

    def __init__(self, base_url: str = DEFAULT_UBIKO_URL, headless: bool = False):
        self.base_url = base_url.rstrip("/")
        self.headless = headless

    def sync_latest_session(
        self,
        target_url: Optional[str] = None,
        force_download: bool = False
    ) -> Dict[str, Any]:
        """
        Abre el navegador, accede a la lista de 'Sesiones realizadas',
        detecta si la última sesión es nueva, pulsa el botón 'CSV', descarga y genera el informe.
        """
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            return {
                "success": False,
                "error": "Playwright no está instalado. Ejecuta: pip install playwright && playwright install chromium"
            }

        url_to_open = target_url or f"{self.base_url}"

        with sync_playwright() as p:
            # Lanzamos navegador Chromium
            browser = p.chromium.launch(
                headless=self.headless,
                args=["--start-maximized", "--disable-blink-features=AutomationControlled"]
            )

            # Usar cookies guardadas si existen
            if SESSION_STORAGE_PATH.exists():
                try:
                    context = browser.new_context(
                        storage_state=str(SESSION_STORAGE_PATH),
                        accept_downloads=True,
                        viewport=None
                    )
                except Exception:
                    context = browser.new_context(accept_downloads=True, viewport=None)
            else:
                context = browser.new_context(accept_downloads=True, viewport=None)

            page = context.new_page()

            print(f"[UBIKO BOT] Navegando a UBIKO: {url_to_open}...")
            page.goto(url_to_open, wait_until="domcontentloaded", timeout=60000)

            # Verificar si estamos en la pantalla de login
            if "login" in page.url.lower() or page.query_selector('input[type="password"]'):
                print("\n" + "=" * 60)
                print(" [UBIKO BOT] INICIO DE SESIÓN REQUERIDO")
                print(" Por favor, introduce tu usuario y contraseña en la ventana del navegador.")
                print(" La sesión se guardará automáticamente para que no vuelva a pedirla.")
                print("=" * 60)

                # Esperar hasta que el usuario inicie sesión y aparezca el menú de Sesiones
                page.wait_for_selector('text=Sesiones, a[href*="sesiones"], a[href*="sessions"]', timeout=180000)
                # Guardar cookies para futuras ejecuciones 100% desatendidas
                context.storage_state(path=str(SESSION_STORAGE_PATH))
                print("[UBIKO BOT] Sesión guardada con éxito en ubiko_session_auth.json.")

            # Asegurarnos de estar en la pestaña de Sesiones
            if not page.query_selector("text=Sesiones realizadas"):
                sesiones_btn = page.query_selector('text="Sesiones", a[href*="sesion"], a[href*="session"]')
                if sesiones_btn:
                    sesiones_btn.click()
                    page.wait_for_load_state("networkidle")

            # Esperar a que cargue la tabla de 'Sesiones realizadas'
            page.wait_for_selector("table, .table, text=Sesiones realizadas", timeout=30000)
            time.sleep(2)  # Pequeña pausa para renderizado dinámico de Vue/React

            # Localizar la primera fila (la sesión más reciente)
            # Selector de filas de la tabla
            rows = page.query_selector_all("table tbody tr, .session-row")
            if not rows:
                browser.close()
                return {"success": False, "error": "No se encontraron filas en la tabla de sesiones."}

            first_row = rows[0]

            # Extraer texto de la primera fila
            row_text = first_row.inner_text()
            cells = first_row.query_selector_all("td")

            raw_date = cells[0].inner_text().strip() if len(cells) > 0 else ""
            session_name = cells[1].inner_text().strip() if len(cells) > 1 else "Sesión UBIKO"

            print(f"\n[UBIKO BOT] Última sesión encontrada en la web:")
            print(f"  - Fecha: {raw_date}")
            print(f"  - Nombre: {session_name}")

            # Parsear fecha de la sesión (ej. '07/09/26 20:23 - 21:39')
            clean_date_str = raw_date.split()[0] if raw_date else datetime.now().strftime("%d/%m/%y")
            parsed_date = date.today()
            for fmt in ("%d/%m/%y", "%d/%m/%Y", "%Y-%m-%d"):
                try:
                    parsed_date = datetime.strptime(clean_date_str, fmt).date()
                    break
                except ValueError:
                    pass

            # Comprobar si ya la tenemos en la base de datos
            with get_db() as db:
                existing = (
                    db.query(TrainingSession)
                    .filter(TrainingSession.name == session_name, TrainingSession.date == parsed_date)
                    .first()
                )

            if existing and not force_download:
                print(f"[UBIKO BOT] La sesión '{session_name}' ({parsed_date}) ya está registrada en el sistema.")
                # Generar informe de la sesión existente
                with get_db() as db:
                    summary = calculate_session_summary(db, existing.id)
                    try:
                        report = generate_tactical_report(summary)
                    except Exception as e_rep:
                        report = f"Informe pendiente de computar: {e_rep}"

                browser.close()
                return {
                    "success": True,
                    "already_existed": True,
                    "session_id": existing.id,
                    "session_name": session_name,
                    "session_date": parsed_date,
                    "report": report
                }

            # Si es nueva (o forzada), localizamos el botón 'CSV' en esa fila
            print("[UBIKO BOT] Nueva sesión detectada. Buscando botón 'CSV'...")

            # El botón CSV es el 4º icono de la columna Acciones o contiene texto CSV
            csv_btn = first_row.query_selector(
                'button:has-text("CSV"), a:has-text("CSV"), [title*="CSV"], .btn-csv, button:nth-child(4)'
            )

            if not csv_btn:
                # Búsqueda en todos los botones de la fila
                buttons = first_row.query_selector_all("button, a")
                for btn in buttons:
                    txt = (btn.inner_text() or btn.get_attribute("title") or "").upper()
                    if "CSV" in txt:
                        csv_btn = btn
                        break

            if not csv_btn:
                browser.close()
                return {"success": False, "error": "No se localizó el botón CSV en la fila de la sesión."}

            print("[UBIKO BOT] Pulsando botón 'CSV' y esperando descarga...")
            with page.expect_download(timeout=30000) as download_info:
                csv_btn.click()

            download = download_info.value
            download_dest = SAMPLES_DIR / f"ubiko_auto_{parsed_date.strftime('%Y%m%d')}_{download.suggested_filename}"
            download.save_as(str(download_dest))
            print(f"[UBIKO BOT] Archivo descargado en: {download_dest.name}")

            # Cerrar navegador
            browser.close()

            # Procesar archivo descargado
            df_parsed = UbikoImporter.parse_file(download_dest, download_dest.name)

            # Deducción de microciclo por el nombre de la sesión
            micro_day = "MD-3"
            sess_type = "Entrenamiento"
            name_upper = session_name.upper()

            if "MD-4" in name_upper:
                micro_day = "MD-4"
            elif "MD-3" in name_upper:
                micro_day = "MD-3"
            elif "MD-2" in name_upper:
                micro_day = "MD-2"
            elif "MD+1" in name_upper:
                micro_day = "MD+1"
            elif "MD-1" in name_upper:
                micro_day = "MD-1"
            elif "PARTIDO" in name_upper or "MD" in name_upper:
                micro_day = "MD"
                sess_type = "Partido"

            # Inserción en SQLite
            with get_db() as db:
                import_res = UbikoImporter.import_session_to_db(
                    db_session=db,
                    df_parsed=df_parsed,
                    session_date=parsed_date,
                    session_name=session_name,
                    microcycle_day=micro_day,
                    session_type=sess_type,
                    duration_minutes=int(df_parsed.get("minutes_played", pd.Series([75])).max() or 75),
                    notes="Descargado automáticamente desde UBIKO Web"
                )

                summary = calculate_session_summary(db, import_res["session_id"])
                try:
                    report = generate_tactical_report(summary)
                except Exception as e_rep:
                    report = f"Informe pendiente de computar: {e_rep}"

            print("\n" + "=" * 65)
            print(" ¡SESIÓN IMPORTADA Y GENERADO INFORME COMPLETO CON ÉXITO!")
            print("=" * 65)
            print(report)

            return {
                "success": True,
                "already_existed": False,
                "session_id": import_res["session_id"],
                "session_name": session_name,
                "session_date": parsed_date,
                "players_processed": import_res["players_processed"],
                "report": report
            }

        except Exception as e:
            return {"success": False, "error": str(e)}
