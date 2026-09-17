"""
Servicio unificado de sincronización y extracción automática con UBIKO Web.
Permite autenticación desatendida, detección de nuevas sesiones 'Computadas',
descarga y procesamiento de telemetría GPS e inserción directa en la base de datos SQLite.
"""

import os
import sys
import time
from datetime import datetime, date
from pathlib import Path
from typing import Dict, Any, Optional

import pandas as pd

from src.config import DATA_DIR, SAMPLES_DIR
from src.database.connection import get_db, init_db
from src.database.models import Player, TrainingSession, PlayerMetric, TargetLoad
from src.services.importer import UbikoImporter
from src.services.analytics import calculate_session_summary
from src.services.report_generator import generate_tactical_report

# Cargar variables de entorno desde archivo .env si existe
ENV_FILE = Path(__file__).resolve().parent / ".env"


def _load_env_file():
    """Lee el archivo .env de forma nativa sin requerir librerías externas obligatorias."""
    if not ENV_FILE.exists():
        return
    try:
        with open(ENV_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, val = line.split("=", 1)
                os.environ.setdefault(key.strip(), val.strip().strip("'\""))
    except Exception:
        pass


_load_env_file()

# Configuración predeterminada
UBIKO_URL = os.getenv("UBIKO_URL", "https://admin.ubikosports.com/team/sessions")
UBIKO_USER = os.getenv("UBIKO_USER", "alvarocab0510@gmail.com")
UBIKO_PASSWORD = os.getenv("UBIKO_PASSWORD", "ubikopuente26")
SESSION_STORAGE = DATA_DIR / "ubiko_session_auth.json"
REPORTS_DIR = DATA_DIR / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)


class UbikoSyncService:
    """
    Gestor de sincronización de sesiones entre UBIKO Cloud y la base de datos local SQLite.
    """

    def __init__(self, base_url: str = UBIKO_URL, headless: bool = True):
        self.base_url = base_url.rstrip("/")
        self.headless = headless

    def get_latest_db_session(self) -> Optional[Dict[str, Any]]:
        """Devuelve los metadatos de la sesión más reciente registrada en SQLite."""
        with get_db() as db:
            sess = (
                db.query(TrainingSession)
                .order_by(TrainingSession.date.desc(), TrainingSession.id.desc())
                .first()
            )
            if not sess:
                return None
            return {
                "id": sess.id,
                "name": sess.name,
                "date": sess.date,
                "microcycle_day": sess.microcycle_day
            }

    def fetch_and_sync(self, force: bool = False, min_date: Optional[date] = None) -> Dict[str, Any]:
        """
        Flujo de extracción y sincronización directa con Supabase:
        1. Conecta con UBIKO Web mediante Playwright.
        2. Descarga la telemetría CSV de cada sesión pendiente directamente en memoria.
        3. Parsea e inserta los datos directamente en la base de datos PostgreSQL de Supabase en la nube.
        4. Actualiza los techos de Máxima Exigencia en Supabase sin escribir archivos en disco local.
        """
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            return {
                "success": False,
                "status": "missing_playwright",
                "message": "Playwright no está disponible en el entorno para sincronizar con UBIKO Web."
            }

        import subprocess

        # En Linux o contenedores cloud sin pantalla gráfica ($DISPLAY), forzar headless=True
        is_headless = self.headless
        is_cloud_linux = os.name != "nt" and not os.getenv("DISPLAY")
        if is_cloud_linux:
            is_headless = True

        try:
            with sync_playwright() as p:
                browser = None
                launch_errors = []

                # Intento 1: Chromium estándar de Playwright
                try:
                    browser = p.chromium.launch(headless=is_headless, timeout=25000)
                except Exception as e1:
                    launch_errors.append(f"Chromium: {e1}")

                # Intento 2: Microsoft Edge nativo de Windows
                if not browser and os.name == "nt":
                    try:
                        browser = p.chromium.launch(channel="msedge", headless=is_headless, timeout=25000)
                    except Exception as e2:
                        launch_errors.append(f"Edge: {e2}")

                # Intento 3: Google Chrome nativo
                if not browser:
                    try:
                        browser = p.chromium.launch(channel="chrome", headless=is_headless, timeout=25000)
                    except Exception as e3:
                        launch_errors.append(f"Chrome: {e3}")

                # Intento 4: Si era headless y falló, intentar headless=False
                if not browser and is_headless and not is_cloud_linux:
                    try:
                        browser = p.chromium.launch(headless=False, timeout=25000)
                    except Exception as e4:
                        launch_errors.append(f"Visible: {e4}")

                # Intento 5: Auto-instalación de Chromium si faltaba
                if not browser and not is_cloud_linux:
                    try:
                        print("[UBIKO] Descargando e instalando Chromium para Playwright...")
                        subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True, timeout=120)
                        browser = p.chromium.launch(headless=is_headless, timeout=25000)
                    except Exception as e5:
                        launch_errors.append(f"Install: {e5}")

                if not browser:
                    err_msg = launch_errors[0] if launch_errors else "Navegador no disponible"
                    print(f"[UBIKO ERROR] No se pudo iniciar navegador: {' | '.join(launch_errors)}")
                    return {
                        "success": False,
                        "status": "browser_error",
                        "message": f"No se pudo iniciar el navegador de sincronización ({err_msg}). Prueba activando 'Ver navegador en pantalla' o descarga el CSV en UBIKO Web."
                    }

                try:
                    return self._execute_session_fetch(browser, force=force, min_date=min_date)
                finally:
                    try:
                        browser.close()
                    except Exception:
                        pass
        except Exception as e:
            import traceback
            traceback.print_exc()
            return {
                "success": False,
                "status": "error",
                "message": f"Error en la sincronización con UBIKO: {e}"
            }

    def _execute_session_fetch(self, browser, force: bool = False, min_date: Optional[date] = None) -> Dict[str, Any]:
        # Configurar viewport a 1920x1080 para que la tabla y todos los botones de acción sean visibles
        context_kwargs = {"accept_downloads": True, "viewport": {"width": 1920, "height": 1080}}
        if SESSION_STORAGE.exists():
            try:
                context = browser.new_context(storage_state=str(SESSION_STORAGE), **context_kwargs)
            except Exception:
                context = browser.new_context(**context_kwargs)
        else:
            context = browser.new_context(**context_kwargs)

        page = context.new_page()

        try:
            # 1. Navegar a UBIKO
            print(f"[UBIKO] Accediendo a: {self.base_url}")
            page.goto(self.base_url, wait_until="domcontentloaded", timeout=25000)
            time.sleep(2)

            # 2. Login automático si se presentan campos de login
            is_login_page = "login" in page.url.lower() or "signin" in page.url.lower() or bool(page.query_selector('input[type="password"]'))
            if is_login_page:
                print(f"[UBIKO] Formulario de inicio de sesión detectado en: {page.url}")
                if UBIKO_USER and UBIKO_PASSWORD:
                    user_input = page.wait_for_selector('input[type="text"], input[type="email"], input[name*="user"], input[name*="email"]', timeout=8000)
                    pass_input = page.wait_for_selector('input[type="password"]', timeout=8000)
                    if user_input and pass_input:
                        print(f"[UBIKO] Introduciendo credenciales para: {UBIKO_USER}")
                        user_input.fill(UBIKO_USER)
                        pass_input.fill(UBIKO_PASSWORD)
                        submit_btn = page.query_selector('button[type="submit"], input[type="submit"], button:has-text("Entrar"), button:has-text("Iniciar"), button:has-text("Acceder"), #kt_sign_in_submit')
                        if submit_btn:
                            submit_btn.click()
                            print("[UBIKO] Credenciales enviadas, esperando autenticación...")
                            try:
                                page.wait_for_url(lambda u: "login" not in u.lower(), timeout=15000)
                            except Exception:
                                pass
                            time.sleep(2)
                else:
                    return {
                        "success": False,
                        "status": "auth_required",
                        "message": "Se requiere inicio de sesión en UBIKO. Configura credenciales en .env o activa 'Ver navegador en pantalla'."
                    }

            print(f"[UBIKO] Página activa: {page.url} | '{page.title()}'")

            # Guardar sesión autenticada si ya no estamos en login
            if "login" not in page.url.lower():
                try:
                    context.storage_state(path=str(SESSION_STORAGE))
                except Exception:
                    pass

            # 3. Acceder al apartado de Sesiones del equipo (/team/sessions)
            target_sessions_url = "https://admin.ubikosports.com/team/sessions"
            if "team/sessions" not in page.url.lower():
                print(f"[UBIKO] Navegando a la sección de sesiones del equipo: {target_sessions_url}")
                try:
                    page.goto(target_sessions_url, wait_until="domcontentloaded", timeout=20000)
                    time.sleep(2)
                except Exception as e_nav:
                    print(f"[UBIKO] Error navegando directamente ({e_nav}), intentando clic en menú 'Sesiones'...")
                    try:
                        sesiones_nav = page.locator("nav, header, .navbar, .menu, body").get_by_text("Sesiones", exact=False).first
                        sesiones_nav.click()
                        time.sleep(2)
                    except Exception:
                        pass

            # 4. Esperar a que la vista de sesiones y los datos del servidor terminen de cargar
            print(f"[UBIKO] Página activa de sesiones: {page.url}")
            print("[UBIKO] Esperando a que carguen las sesiones realizadas...")
            try:
                page.wait_for_selector("table tbody tr", timeout=25000)
            except Exception:
                try:
                    page.locator("text=Sesiones").first.wait_for(timeout=10000)
                except Exception as e_wait:
                    if "login" in page.url.lower():
                        return {
                            "success": False,
                            "status": "login_needed",
                            "message": "La sesión de UBIKO ha caducado. Activa 'Ver navegador en pantalla' para iniciar sesión."
                        }
                    return {
                        "success": False,
                        "status": "table_timeout",
                        "message": f"Tiempo de espera agotado esperando la tabla de sesiones en UBIKO ({e_wait})."
                    }
        except Exception as e_flow:
            print(f"[UBIKO ERROR EN FLUJO WEB] {e_flow}")
            return {
                "success": False,
                "status": "flow_error",
                "message": f"Error conectando a UBIKO Web: {e_flow}"
            }

        time.sleep(1.5)

        # 5. Inspeccionar filas de sesiones
        import re
        rows = page.locator("table tbody tr").all()
        print(f"[UBIKO] Total de filas encontradas en la tabla: {len(rows)}")

        if not rows:
            debug_shot = DATA_DIR / "debug_ubiko_norows.png"
            page.screenshot(path=str(debug_shot))
            return {"success": False, "status": "no_data", "message": f"No se encontraron filas de sesiones en UBIKO. Captura: {debug_shot.name}"}

        # Filtrar sesiones a procesar (desde min_date o 03/09/2026 en adelante)
        min_sync_date = min_date if min_date is not None else date(2026, 9, 3)
        print(f"[UBIKO] Analizando sesiones disponibles (filtrando desde {min_sync_date.strftime('%d/%m/%Y')} en adelante)...")

        sessions_to_process = []
        for idx, row in enumerate(rows):
            row_text = row.inner_text().strip()
            cells = row.locator("td, mat-cell, div[role='cell']").all()
            if len(cells) >= 4:
                raw_date = cells[0].inner_text().strip()
                session_name = cells[1].inner_text().strip()
                raw_status = cells[3].inner_text().strip()
            else:
                lines = [l.strip() for l in row_text.split("\n") if l.strip()]
                raw_date = lines[0] if len(lines) > 0 else ""
                session_name = lines[1] if len(lines) > 1 else f"Sesión UBIKO {idx+1}"
                raw_status = "Computada" if "computada" in row_text.lower() else "Pendiente"

            # Parsear fecha de forma robusta con Regex (soporta DD/MM/YY y DD/MM/YYYY)
            parsed_date = None
            date_match = re.search(r"\b(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})\b", raw_date or row_text)
            if date_match:
                d, m, y = map(int, date_match.groups())
                if y < 100:
                    y += 2000
                try:
                    parsed_date = date(y, m, d)
                except ValueError:
                    pass

            if not parsed_date:
                continue

            # Filtrar solo sesiones a partir de la fecha objetivo
            if parsed_date < min_sync_date:
                continue

            print(f"[UBIKO] -> Sesión detectada: '{session_name}' ({parsed_date.strftime('%d/%m/%Y')}) | Estado: {raw_status}")
            sessions_to_process.append({
                "row_idx": idx,
                "row_locator": row,
                "date": parsed_date,
                "raw_date": raw_date,
                "name": session_name,
                "status": raw_status
            })

        print(f"[UBIKO] Se han encontrado {len(sessions_to_process)} sesión(es) a partir del {min_sync_date.strftime('%d/%m/%Y')}.")

        if not sessions_to_process:
            return {
                "success": True,
                "status": "up_to_date",
                "message": f"No hay sesiones en UBIKO con fecha igual o posterior al {min_sync_date.strftime('%d/%m/%Y')}."
            }

        synced_sessions = []
        reports = []

        # 6. Procesar cada sesión secuencialmente
        for item in sessions_to_process:
            s_name = item["name"]
            s_date = item["date"]
            s_status = item["status"]
            current_row = item["row_locator"]

            print(f"\n[UBIKO] >>> Procesando sesión: '{s_name}' ({s_date.strftime('%d/%m/%Y')}) | Estado: {s_status}")

            if "computando" in s_status.lower() or "procesando" in s_status.lower():
                print(f"[UBIKO] Saltando '{s_name}' porque todavía se está computando.")
                continue

            # Comprobar si ya existe en la base de datos SQLite
            with get_db() as db:
                existing = db.query(TrainingSession).filter(
                    TrainingSession.name == s_name,
                    TrainingSession.date == s_date
                ).first()

            if existing and not force:
                print(f"[UBIKO] La sesión '{s_name}' ya está en la base de datos. Generando resumen...")
                with get_db() as db:
                    summ = calculate_session_summary(db, existing.id)
                    try:
                        rep = generate_tactical_report(summ)
                    except Exception as e_rep:
                        rep = f"Informe pendiente de computar: {e_rep}"
                    reports.append(rep)
                synced_sessions.append({"id": existing.id, "name": s_name, "date": s_date, "status": "already_synced"})
                continue

            # Descargar CSV de la fila correspondiente
            print(f"[UBIKO] Descargando telemetría CSV para '{s_name}'...")
            download = None

            actions_cell = current_row.locator("td, mat-cell").last
            act_btns = actions_cell.locator("button, a").all()

            # Intento 1: Buscar botón o enlace explícito de CSV
            csv_item = current_row.locator('button:has-text("CSV"), a:has-text("CSV"), [title*="CSV" i], [aria-label*="CSV" i]')
            if csv_item.count() > 0:
                try:
                    with page.expect_download(timeout=15000) as download_info:
                        csv_item.first.click()
                    download = download_info.value
                except Exception as e_c1:
                    try:
                        with page.expect_download(timeout=15000) as download_info:
                            csv_item.first.evaluate("el => el.click()")
                        download = download_info.value
                    except Exception:
                        pass

            # Intento 2: En la tabla de UBIKO, el botón CSV es típicamente el 4º botón verde (índice 3)
            if not download and len(act_btns) >= 4:
                try:
                    with page.expect_download(timeout=15000) as download_info:
                        act_btns[3].click()
                    download = download_info.value
                except Exception:
                    try:
                        with page.expect_download(timeout=15000) as download_info:
                            act_btns[3].evaluate("el => el.click()")
                        download = download_info.value
                    except Exception:
                        pass

            # Intento 3: Probar el 3º botón (índice 2)
            if not download and len(act_btns) >= 3:
                try:
                    with page.expect_download(timeout=10000) as download_info:
                        act_btns[2].click()
                    download = download_info.value
                except Exception:
                    pass

            # Intento 4: Desplegar menú de exportación de la fila si existe
            if not download:
                dropdown_toggle = current_row.locator('[ngbdropdowntoggle], [data-bs-toggle="dropdown"], .dropdown-toggle')
                if dropdown_toggle.count() > 0:
                    try:
                        dropdown_toggle.first.click()
                        time.sleep(1)
                        with page.expect_download(timeout=15000) as download_info:
                            page.locator('button:has-text("CSV"), a:has-text("CSV"), .dropdown-item:has-text("CSV")').first.click(force=True)
                        download = download_info.value
                    except Exception as e_dd:
                        print(f"[UBIKO] Aviso menú dropdown ({e_dd}).")

            if not download:
                print(f"[UBIKO ERROR] No se pudo descargar el CSV para la sesión '{s_name}'.")
                continue

            import tempfile
            with tempfile.TemporaryDirectory() as tmpdir:
                tmp_csv = Path(tmpdir) / download.suggested_filename
                download.save_as(str(tmp_csv))
                print(f"[UBIKO] Parseando telemetría en memoria para '{s_name}'...")
                df_parsed = UbikoImporter.parse_file(tmp_csv, download.suggested_filename)

            if df_parsed.empty:
                print(f"[UBIKO] Archivo sin registros válidos para '{s_name}'.")
                continue

            # Deducir día del microciclo
            name_upper = s_name.upper()
            micro_day = "MD-3"
            sess_type = "Entrenamiento"
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

            # Ingesta en Supabase (PostgreSQL Nube)
            with get_db() as db:
                # Asegurar porteros oficiales (Estepa #1, Luengo #13)
                db.query(Player).filter(Player.dorsal.in_([1, 13])).update({"position": "Portero"}, synchronize_session=False)
                # Pajuelo #25 es Lateral
                db.query(Player).filter(Player.dorsal == 25).update({"position": "Lateral"}, synchronize_session=False)
                db.commit()

                if force:
                    old_sess = db.query(TrainingSession).filter(
                        TrainingSession.name == s_name,
                        TrainingSession.date == s_date
                    ).first()
                    if old_sess:
                        db.query(PlayerMetric).filter(PlayerMetric.session_id == old_sess.id).delete()
                        db.delete(old_sess)
                        db.commit()

                import_res = UbikoImporter.import_session_to_db(
                    db_session=db,
                    df_parsed=df_parsed,
                    session_date=s_date,
                    session_name=s_name,
                    microcycle_day=micro_day,
                    session_type=sess_type,
                    duration_minutes=int(df_parsed.get("minutes_played", pd.Series([75])).max() or 75),
                    notes="Sincronizado directamente a Supabase desde UBIKO Web"
                )

                summ = calculate_session_summary(db, import_res["session_id"])
                try:
                    rep = generate_tactical_report(summ)
                except Exception as e_rep:
                    rep = f"Informe pendiente de computar: {e_rep}"
                reports.append(rep)

            synced_sessions.append({
                "id": import_res["session_id"],
                "name": s_name,
                "date": s_date,
                "players_count": import_res["players_processed"],
                "status": "newly_synced"
            })
            print(f"[UBIKO] ¡Sesión '{s_name}' ingestada correctamente! ({import_res['players_processed']} jugadores)")

        newly_synced = [s for s in synced_sessions if s.get("status") == "newly_synced"]
        already_synced = [s for s in synced_sessions if s.get("status") == "already_synced"]

        if newly_synced:
            msg = f"Se han sincronizado e integrado exitosamente {len(newly_synced)} nuevas sesiones en la base de datos."
            is_ok = True
        elif already_synced:
            msg = f"Todas las sesiones disponibles ({len(already_synced)}) ya se encuentran sincronizadas y al día."
            is_ok = True
        else:
            msg = "No se pudieron descargar nuevas sesiones desde UBIKO Web. Comprueba que estén en estado 'Computada'."
            is_ok = False

        return {
            "success": is_ok,
            "status": "batch_completed" if newly_synced else ("up_to_date" if already_synced else "no_sessions_downloaded"),
            "synced_count": len(newly_synced),
            "total_checked": len(synced_sessions),
            "sessions": synced_sessions,
            "report": reports[-1] if reports else "",
            "message": msg
        }


def sync_latest_session(headless: bool = True, force: bool = False, min_date: Optional[date] = None) -> Dict[str, Any]:
    """
    Función de entrada de alto nivel lista para ser llamada desde Streamlit o scripts externos.
    """
    service = UbikoSyncService(headless=headless)
    return service.fetch_and_sync(force=force, min_date=min_date)


# Punto de entrada para ejecución directa o bucle continuo en terminal
if __name__ == "__main__":
    init_db()

    # Si la base de datos está vacía (por ejemplo tras borrarla), inicializar la plantilla de Salerm Puente Genil
    from src.database.models import Player
    with get_db() as db:
        if db.query(Player).count() == 0:
            print("[SISTEMA] Base de datos vacía detectada. Inicializando plantilla del Salerm Puente Genil...")
            try:
                from seed_data import seed_roster_and_targets
                seed_roster_and_targets()
            except Exception as e_seed:
                print(f"[SISTEMA] Aviso al inicializar datos base: {e_seed}")

    print("=" * 65)
    print("  SINCRONIZADOR UBIKO WEB - SALERM COSMETICS PUENTE GENIL")
    print("=" * 65)

    # Extraer fecha desde argumento --since=DD/MM/YYYY o YYYY-MM-DD si se especifica
    cli_min_date = None
    for arg in sys.argv:
        if arg.startswith("--since="):
            val = arg.split("=")[1].strip()
            for fmt in ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d"):
                try:
                    cli_min_date = datetime.strptime(val, fmt).date()
                    break
                except ValueError:
                    pass

    if "--daemon" in sys.argv:
        poll_interval = 20  # minutos
        for arg in sys.argv:
            if arg.startswith("--interval="):
                try:
                    poll_interval = int(arg.split("=")[1])
                except ValueError:
                    pass

        print(f"Modo demonio activo: comprobando cada {poll_interval} minutos...")
        while True:
            t_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"\n[{t_now}] Comprobando web de UBIKO...")
            res = sync_latest_session(headless=True, min_date=cli_min_date)
            print(f"[{t_now}] Resultado: {res.get('message')}")
            time.sleep(poll_interval * 60)
    else:
        # Ejecución puntual
        headless_mode = "--visible" not in sys.argv
        force_mode = "--force" in sys.argv

        if cli_min_date:
            print(f"Filtrando sesiones desde: {cli_min_date.strftime('%d/%m/%Y')}")

        print(f"Ejecutando comprobación (Headless={headless_mode}, Force={force_mode})...")
        resultado = sync_latest_session(headless=headless_mode, force=force_mode, min_date=cli_min_date)
        print("\nResultado:", resultado.get("message"))
        if resultado.get("success") and resultado.get("report"):
            print("\n" + "=" * 65)
            print(" INFORME TÁCTICO GENERADO:")
            print("=" * 65)
            print(resultado["report"])
