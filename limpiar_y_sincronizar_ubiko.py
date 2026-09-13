"""
Script para limpiar datos simulados de Supabase y sincronizar con UBIKO Web.
Permite purgar sesiones y métricas falsas (incluidas las de porteros que no usan chip)
y mantener intacta la plantilla de 26 jugadores oficiales y objetivos de carga.

Uso:
  python limpiar_y_sincronizar_ubiko.py             # Limpia datos falsos en Supabase
  python limpiar_y_sincronizar_ubiko.py --sync      # Limpia y descarga sesiones reales desde UBIKO
"""

import sys
from datetime import date
from src.database.connection import init_db, get_db
from src.database.models import PlayerMetric, TrainingSession, Player, TargetLoad
from seed_data import seed_roster_and_targets


def limpiar_datos_falsos():
    print("=" * 65)
    print("  LIMPIEZA DE DATOS SIMULADOS EN SUPABASE (POSTGRESQL)")
    print("=" * 65)

    init_db()

    with get_db() as db:
        n_metrics = db.query(PlayerMetric).delete()
        n_sessions = db.query(TrainingSession).delete()
        db.commit()
        print(f"[1/2] Se han eliminado {n_sessions} sesiones y {n_metrics} métricas simuladas.")

    print("[2/2] Verificando plantilla oficial de 26 jugadores y objetivos...")
    seed_roster_and_targets(overwrite=False)

    with get_db() as db:
        num_jugadores = db.query(Player).count()
        num_sesiones = db.query(TrainingSession).count()
        num_metricas = db.query(PlayerMetric).count()
        print(f"      - Jugadores registrados en Supabase: {num_jugadores}")
        print(f"      - Sesiones actuales: {num_sesiones}")
        print(f"      - Métricas actuales: {num_metricas}")

    print("\n[ÉXITO] La base de datos está completamente limpia.")
    print("        Ni Estepa (#1) ni Luengo (#13) tienen ya datos falsos.")


def main():
    limpiar_datos_falsos()

    if "--sync" in sys.argv:
        print("\n" + "=" * 65)
        print("  INICIANDO DESCARGA REAL DESDE UBIKO WEB...")
        print("=" * 65)
        from ubiko_sync import sync_latest_session
        res = sync_latest_session(headless=False, force=True, min_date=date(2026, 9, 3))
        print(f"Resultado: {res.get('message')}")
    else:
        print("\nPara sincronizar las sesiones reales de UBIKO ahora mismo, ejecuta:")
        print("    python ubiko_sync.py --visible --since=03/09/2026")
        print("\nO bien ejecuta la app web y pulsa en 'Sincronizar Sesiones Ahora':")
        print("    streamlit run app.py\n")


if __name__ == "__main__":
    main()
