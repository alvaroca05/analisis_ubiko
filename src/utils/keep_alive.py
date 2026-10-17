"""
Script de mantenimiento y Keep-Alive para Streamlit Community Cloud.
Mantiene la web de UBIKO activa las 24 horas del día para evitar que entre en modo suspensión ('Zzzz').
Si detecta que la aplicación se ha dormido, pulsa automáticamente el botón 'Yes, get this app back up!'.
"""

import os
import sys
import time
import requests

TARGET_URL = os.environ.get("STREAMLIT_APP_URL", "https://rendimiento-ubiko.streamlit.app")


def ping_http(url: str) -> bool:
    """Envía una petición HTTP con cabeceras de navegador para simular tráfico activo."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
    }
    try:
        res = requests.get(url, headers=headers, timeout=20)
        print(f"[Keep-Alive] HTTP Ping a {url} -> Código {res.status_code} ({len(res.content)} bytes)")
        return res.status_code == 200
    except Exception as e:
        print(f"[Keep-Alive] Aviso HTTP ping: {e}")
        return False


def wake_with_playwright(url: str):
    """Abre la web en un navegador headless para activar WebSockets y pulsar el botón si está dormida."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[Keep-Alive] Playwright no está instalado. Continuando solo con HTTP ping.")
        return

    print(f"[Keep-Alive] Iniciando navegador headless para inspeccionar {url}...")
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]
        )
        page = browser.new_page(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        try:
            page.goto(url, timeout=45000, wait_until="domcontentloaded")
            page.wait_for_timeout(6000)
            print(f"[Keep-Alive] Título de la página: '{page.title()}'")

            # Buscar botón de reactivación si Streamlit la puso en suspensión ('Zzzz')
            wake_btn = page.locator('button:has-text("Yes, get this app back up!"), button:has-text("wake")')
            if wake_btn.count() > 0 and wake_btn.first.is_visible():
                print("[Keep-Alive] [!] Aplicacion en modo 'Zzzz' detectada. Pulsando 'Yes, get this app back up!'...")
                wake_btn.first.click()
                page.wait_for_timeout(12000)
                print("[Keep-Alive] [OK] Senal de reactivacion enviada. La aplicacion se esta levantando.")
            else:
                print("[Keep-Alive] [OK] La aplicacion ya esta despierta y operativa.")

            page.wait_for_timeout(4000)
        except Exception as e:
            print(f"[Keep-Alive] Aviso durante la navegación: {e}")
        finally:
            browser.close()


def main():
    print(f"=== [UBIKO KEEP-ALIVE] Comprobando estado de {TARGET_URL} ===")
    ping_http(TARGET_URL)
    wake_with_playwright(TARGET_URL)
    print("=== [UBIKO KEEP-ALIVE] Proceso completado exitosamente ===")


if __name__ == "__main__":
    main()
