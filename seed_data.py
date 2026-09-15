"""
Script de generación de datos sintéticos realistas para el TFG.
Crea la base de datos SQLite con:
1. Plantilla completa de 24 jugadores de fútbol profesional.
2. Objetivos de carga física por demarcación y día de microciclo (MD-4 a MD).
3. 6 semanas completas de microciclos competitivos (más de 30 sesiones y 700+ registros GPS individuales).
4. Casos reales de fatiga (jugadores en sobrecarga, jugadores en fase de retorno y jugadores en zona óptima).
"""

import random
from datetime import date, timedelta
import numpy as np

from src.config import POSITIONS, MICROCYCLE_DAYS, DEFAULT_CLUB_ID
from src.database.connection import init_db, get_db
from src.database.models import Player, TrainingSession, PlayerMetric, TargetLoad, PlayerMatchPeak

# Fijar semilla para reproducibilidad científica
random.seed(42)
np.random.seed(42)

PLAYERS_DATA = [
    # 1 Estepa (Portero)
    {"name": "Estepa", "dorsal": 1, "position": "Portero", "max_speed": 24.5, "vo2max": 50.0},
    # 3 Connor (Lateral Izquierdo)
    {"name": "Connor", "dorsal": 3, "position": "Lateral", "max_speed": 32.5, "vo2max": 59.5},
    # 4 Gines (Central)
    {"name": "Gines", "dorsal": 4, "position": "Central", "max_speed": 30.5, "vo2max": 55.0},
    # 5 Salvi (Central)
    {"name": "Salvi", "dorsal": 5, "position": "Central", "max_speed": 31.2, "vo2max": 56.5},
    # 6 Virtudes (Mediocentro)
    {"name": "Virtudes", "dorsal": 6, "position": "Mediocentro", "max_speed": 31.4, "vo2max": 63.0},
    # 7 Bugui (Extremo - Sin minutos disputados esta temporada)
    {"name": "Bugui", "dorsal": 7, "position": "Extremo", "max_speed": 34.2, "vo2max": 61.5, "active": False},
    # 8 Juan Maria (Mediocentro)
    {"name": "Juan Maria", "dorsal": 8, "position": "Mediocentro", "max_speed": 31.0, "vo2max": 62.0},
    # 9 Bianco (Delantero)
    {"name": "Bianco", "dorsal": 9, "position": "Delantero", "max_speed": 32.8, "vo2max": 58.5},
    # 10 Salva Vegas (Mediocentro / Mediapunta)
    {"name": "Salva Vegas", "dorsal": 10, "position": "Mediocentro", "max_speed": 32.0, "vo2max": 62.0},
    # 11 Alan (Extremo)
    {"name": "Alan", "dorsal": 11, "position": "Extremo", "max_speed": 34.0, "vo2max": 62.0},
    # 12 Talarn (Lateral / Central)
    {"name": "Talarn", "dorsal": 12, "position": "Lateral", "max_speed": 32.0, "vo2max": 58.5},
    # 13 Luengo (Portero)
    {"name": "Luengo", "dorsal": 13, "position": "Portero", "max_speed": 24.0, "vo2max": 49.5},
    # 14 Polaco (Mediocentro)
    {"name": "Polaco", "dorsal": 14, "position": "Mediocentro", "max_speed": 31.5, "vo2max": 61.5},
    # 15 Viana (Extremo)
    {"name": "Viana", "dorsal": 15, "position": "Extremo", "max_speed": 33.6, "vo2max": 60.5},
    # 16 Rafita (Extremo)
    {"name": "Rafita", "dorsal": 16, "position": "Extremo", "max_speed": 33.5, "vo2max": 60.0},
    # 17 Marcos Perez (Central)
    {"name": "Marcos Perez", "dorsal": 17, "position": "Central", "max_speed": 30.8, "vo2max": 56.0},
    # 18 Victor Julia (Mediocentro)
    {"name": "Victor Julia", "dorsal": 18, "position": "Mediocentro", "max_speed": 31.2, "vo2max": 61.0},
    # 19 Topo (Mediocentro / Mediapunta)
    {"name": "Topo", "dorsal": 19, "position": "Mediocentro", "max_speed": 32.0, "vo2max": 63.5},
    # 20 Lalo (Mediocentro)
    {"name": "Lalo", "dorsal": 20, "position": "Mediocentro", "max_speed": 31.5, "vo2max": 61.5},
    # 21 Seth Vega (Delantero / Extremo)
    {"name": "Seth Vega", "dorsal": 21, "position": "Delantero", "max_speed": 33.5, "vo2max": 59.5},
    # 22 Pepelu (Mediocentro)
    {"name": "Pepelu", "dorsal": 22, "position": "Mediocentro", "max_speed": 31.0, "vo2max": 61.0},
    # 23 Josemi (Delantero)
    {"name": "Josemi", "dorsal": 23, "position": "Delantero", "max_speed": 33.2, "vo2max": 59.5},
    # 24 Cellou (Extremo / Delantero)
    {"name": "Cellou", "dorsal": 24, "position": "Extremo", "max_speed": 33.8, "vo2max": 61.0},
    # 25 Pajuelo (Lateral Derecho)
    {"name": "Pajuelo", "dorsal": 25, "position": "Lateral", "max_speed": 32.8, "vo2max": 60.5},
    # 26 Moro (Delantero)
    {"name": "Moro", "dorsal": 26, "position": "Delantero", "max_speed": 32.6, "vo2max": 58.0},
    # 27 Fernando Romero (Mediocentro)
    {"name": "Fernando Romero", "dorsal": 27, "position": "Mediocentro", "max_speed": 32.5, "vo2max": 64.0}
]

# Objetivos fisiológicos planificados de carga por día de microciclo y posición
TARGETS_CONFIG = {
    "MD-4": {
        "Portero": {"td": 4000, "hsr": 30, "hmld": 550, "acc": 20, "dec": 20},
        "Central": {"td": 5500, "hsr": 160, "hmld": 850, "acc": 26, "dec": 28},
        "Lateral": {"td": 6200, "hsr": 350, "hmld": 1100, "acc": 33, "dec": 36},
        "Mediocentro": {"td": 6800, "hsr": 250, "hmld": 1200, "acc": 30, "dec": 32},
        "Extremo": {"td": 6400, "hsr": 420, "hmld": 1250, "acc": 35, "dec": 38},
        "Delantero": {"td": 6000, "hsr": 320, "hmld": 1050, "acc": 28, "dec": 30},
    },
    "MD-3": {
        "Portero": {"td": 4800, "hsr": 50, "hmld": 650, "acc": 25, "dec": 25},
        "Central": {"td": 6500, "hsr": 300, "hmld": 1050, "acc": 30, "dec": 32},
        "Lateral": {"td": 7600, "hsr": 700, "hmld": 1450, "acc": 40, "dec": 42},
        "Mediocentro": {"td": 8400, "hsr": 500, "hmld": 1550, "acc": 36, "dec": 38},
        "Extremo": {"td": 7700, "hsr": 800, "hmld": 1600, "acc": 45, "dec": 48},
        "Delantero": {"td": 7200, "hsr": 580, "hmld": 1350, "acc": 36, "dec": 38},
    },
    "MD-2": {
        "Portero": {"td": 3600, "hsr": 40, "hmld": 500, "acc": 18, "dec": 18},
        "Central": {"td": 4800, "hsr": 200, "hmld": 750, "acc": 22, "dec": 22},
        "Lateral": {"td": 5400, "hsr": 450, "hmld": 980, "acc": 28, "dec": 28},
        "Mediocentro": {"td": 5800, "hsr": 320, "hmld": 1020, "acc": 25, "dec": 26},
        "Extremo": {"td": 5500, "hsr": 520, "hmld": 1080, "acc": 30, "dec": 30},
        "Delantero": {"td": 5200, "hsr": 400, "hmld": 920, "acc": 26, "dec": 26},
    },
    "MD-1": {
        "Portero": {"td": 2600, "hsr": 20, "hmld": 350, "acc": 12, "dec": 12},
        "Central": {"td": 3500, "hsr": 80, "hmld": 500, "acc": 14, "dec": 15},
        "Lateral": {"td": 3800, "hsr": 150, "hmld": 620, "acc": 18, "dec": 18},
        "Mediocentro": {"td": 4000, "hsr": 120, "hmld": 650, "acc": 16, "dec": 17},
        "Extremo": {"td": 3900, "hsr": 180, "hmld": 660, "acc": 19, "dec": 19},
        "Delantero": {"td": 3700, "hsr": 140, "hmld": 590, "acc": 16, "dec": 17},
    },
    "MD": {
        "Portero": {"td": 5200, "hsr": 80, "hmld": 750, "acc": 30, "dec": 30},
        "Central": {"td": 9800, "hsr": 480, "hmld": 1600, "acc": 45, "dec": 48},
        "Lateral": {"td": 11200, "hsr": 1050, "hmld": 2200, "acc": 60, "dec": 65},
        "Mediocentro": {"td": 12100, "hsr": 750, "hmld": 2400, "acc": 55, "dec": 58},
        "Extremo": {"td": 10900, "hsr": 1180, "hmld": 2300, "acc": 65, "dec": 70},
        "Delantero": {"td": 10400, "hsr": 880, "hmld": 1950, "acc": 52, "dec": 55},
    }
}


def seed_roster_and_targets(overwrite: bool = False, club_id: int = DEFAULT_CLUB_ID):
    """
    Inicializa los objetivos de carga física y la plantilla oficial de 26 jugadores
    SIN generar sesiones ni métricas falsas. Soporta multitenant mediante club_id.
    """
    init_db()
    with get_db() as db:
        # 1. Objetivos
        if overwrite or db.query(TargetLoad).filter(TargetLoad.club_id == club_id).count() == 0:
            if overwrite:
                db.query(TargetLoad).filter(TargetLoad.club_id == club_id).delete()
            for day, pos_dict in TARGETS_CONFIG.items():
                for pos, vals in pos_dict.items():
                    t = TargetLoad(
                        club_id=club_id,
                        microcycle_day=day,
                        position=pos,
                        target_td=float(vals["td"]),
                        target_hsr=float(vals["hsr"]),
                        target_hmld=float(vals["hmld"]),
                        target_acc_eff=int(vals["acc"]),
                        target_dec_eff=int(vals["dec"])
                    )
                    db.add(t)
            print("[PLANTILLA] Objetivos de carga configurados.")

        # 2. Jugadores oficiales
        if overwrite or db.query(Player).filter(Player.club_id == club_id).count() == 0:
            if overwrite:
                db.query(Player).filter(Player.club_id == club_id).delete()
            for pdata in PLAYERS_DATA:
                p = Player(
                    club_id=club_id,
                    name=pdata["name"],
                    dorsal=pdata["dorsal"],
                    position=pdata["position"],
                    max_speed_kmh=pdata["max_speed"],
                    vo2max=pdata["vo2max"],
                    active=pdata.get("active", True)
                )
                db.add(p)
            print(f"[PLANTILLA] {len(PLAYERS_DATA)} jugadores oficiales registrados.")
        else:
            existing_dorsals = {p.dorsal for p in db.query(Player.dorsal).filter(Player.club_id == club_id).all()}
            for pdata in PLAYERS_DATA:
                if pdata["dorsal"] not in existing_dorsals:
                    p = Player(
                        club_id=club_id,
                        name=pdata["name"],
                        dorsal=pdata["dorsal"],
                        position=pdata["position"],
                        max_speed_kmh=pdata["max_speed"],
                        vo2max=pdata["vo2max"],
                        active=pdata.get("active", True)
                    )
                    db.add(p)

    # 3. Inicializar techos dinámicos del 100% de partido
    with get_db() as db:
        from src.services.analytics import sync_and_update_player_match_peaks
        sync_and_update_player_match_peaks(db, club_id=club_id)


def purge_simulated_sessions_and_metrics(club_id: int = DEFAULT_CLUB_ID) -> tuple:
    """
    Elimina todas las sesiones y métricas de la base de datos activa (Supabase o SQLite),
    garantizando que la plantilla oficial de 26 jugadores y los objetivos permanezcan intactos.
    Sincroniza automáticamente los archivos CSV reales de Ubiko y recalcula techos.
    Retorna (num_sesiones_borradas, num_metricas_borradas).
    """
    init_db()
    with get_db() as db:
        n_metrics = db.query(PlayerMetric).filter(PlayerMetric.club_id == club_id).delete()
        n_sessions = db.query(TrainingSession).filter(TrainingSession.club_id == club_id).delete()
    
    seed_roster_and_targets(overwrite=False, club_id=club_id)

    # Sincronizar sesiones reales desde CSVs de Ubiko y actualizar techos
    with get_db() as db:
        from src.services.importer import UbikoImporter
        from src.services.analytics import sync_and_update_player_match_peaks
        UbikoImporter.sync_local_csv_samples(db)
        sync_and_update_player_match_peaks(db, club_id=club_id)

    print(f"[LIMPIEZA] Eliminadas {n_sessions} sesiones y {n_metrics} métricas. Sincronizadas sesiones reales.")
    return n_sessions, n_metrics


def seed_database(include_sessions: bool = True):
    """
    Función principal de inicialización y poblado de la base de datos.
    Si include_sessions=True, genera también las 6 semanas de sesiones sintéticas de prueba.
    """
    print("Iniciando creación de esquemas y plantilla base...")
    init_db()
    seed_roster_and_targets(overwrite=True)

    if not include_sessions:
        print("Poblado base completado sin sesiones sintéticas.")
        return

    with get_db() as db:
        # Recuperar mapa de jugadores
        players_map = {p.id: p for p in db.query(Player).all()}

        # 3. Generar Microciclos Históricos (6 semanas hacia atrás hasta hoy)
        print("Generando 6 semanas de microciclos y métricas GPS UBIKO...")
        db.query(PlayerMetric).delete()
        db.query(TrainingSession).delete()

        end_date = date.today()
        # 6 semanas = 42 días
        start_date = end_date - timedelta(days=41)

        current_date = start_date
        session_count = 0

        # Patrón semanal: Miércoles (MD-4), Jueves (MD-3), Viernes (MD-2), Sábado (MD-1), Lunes (Descanso), Martes (Descanso/Gimnasio)
        # Nota: Los Domingos (MD / Partidos) se importan exclusivamente de los CSV reales de Ubiko para evitar duplicados.
        while current_date <= end_date:
            weekday = current_date.weekday()  # 0=Lunes, 1=Martes, 2=Miércoles, 3=Jueves, 4=Viernes, 5=Sábado, 6=Domingo

            day_tag = None
            sess_type = "Entrenamiento"
            duration = 75

            if weekday == 2:
                day_tag = "MD-4"
                duration = 70
            elif weekday == 3:
                day_tag = "MD-3"
                duration = 85
            elif weekday == 4:
                day_tag = "MD-2"
                duration = 60
            elif weekday == 5:
                day_tag = "MD-1"
                duration = 45
            elif weekday == 6:
                # Domingo: reservado para partidos reales oficiales de Ubiko
                day_tag = None

            if day_tag:
                session_count += 1
                sess_name = f"{sess_type} - {day_tag} ({current_date.strftime('%d/%m')})"
                sess_obj = TrainingSession(
                    date=current_date,
                    name=sess_name,
                    microcycle_day=day_tag,
                    session_type=sess_type,
                    duration_minutes=duration,
                    pitch_condition="Excelente"
                )
                db.add(sess_obj)
                db.flush()

                # Generar métricas para cada jugador de campo activo (Bugui #7 no ha disputado minutos y los porteros no portan chip GPS)
                for p_id, player in players_map.items():
                    if player.position == "Portero" or player.dorsal == 7 or not getattr(player, "active", True):
                        continue

                    targets = TARGETS_CONFIG[day_tag][player.position]

                    # Moduladores específicos para recrear casos de uso reales
                    factor_individual = 1.0
                    
                    # Caso 1: Pajuelo (#25 Lateral) y Manu Viana (#15 Extremo) - Fatiga acumulada reciente -> PRECAUCIÓN (ACWR ~ 1.35 - 1.45)
                    if player.dorsal in [25, 15] and current_date >= (end_date - timedelta(days=5)):
                        factor_individual = 1.40  # Fatiga moderada

                    # Caso 3: Loren (#9 Delantero) y Salva Vegas (#10) - Vuelta de lesión en última semana -> SUBENTRENAMIENTO (ACWR < 0.75)
                    elif player.dorsal in [9, 10] and current_date >= (end_date - timedelta(days=7)):
                        factor_individual = 0.35  # Trabajo muy reducido

                    # Caso 4: Jugadores con pocos minutos / suplentes habituales (ej. Fernando #27)
                    elif player.dorsal == 27:
                        factor_individual = 0.40  # Carga reducida acorde a su rol actual

                    # Caso 4: Desviaciones tácticas en la sesión de hoy (Cumplimiento Real vs Plan)
                    if current_date == end_date:
                        if player.dorsal in [19, 23]:  # Topo y Josemi sobreestimulados en la sesión de hoy
                            factor_individual *= 1.28
                        elif player.dorsal in [4, 5]:   # Edu Chía y Salvi Vera con menor volumen del prescrito
                            factor_individual *= 0.76

                    # Variabilidad biológica normal (~5% de desviación estándar)
                    noise = np.random.normal(1.0, 0.05)
                    final_factor = factor_individual * noise

                    real_td = max(1000.0, targets["td"] * final_factor)
                    real_hsr = max(20.0, targets["hsr"] * final_factor)
                    real_sprint = max(0.0, real_hsr * np.random.uniform(0.18, 0.28))
                    real_hmld = max(200.0, targets["hmld"] * final_factor)
                    real_acc = max(5, int(targets["acc"] * final_factor))
                    real_dec = max(5, int(targets["dec"] * final_factor))
                    
                    # Velocidad máxima alcanzada
                    if day_tag in ["MD", "MD-2"]:
                        vmax = min(player.max_speed_kmh, player.max_speed_kmh * np.random.uniform(0.92, 1.0))
                    else:
                        vmax = player.max_speed_kmh * np.random.uniform(0.80, 0.90)

                    # PlayerLoad proporcional a distancia y aceleraciones
                    pload = (real_td * 0.08) + ((real_acc + real_dec) * 1.5)
                    rpe = min(10.0, max(3.0, (final_factor * (7.0 if day_tag == 'MD' else 6.0)) + np.random.normal(0, 0.5)))

                    metric = PlayerMetric(
                        player_id=p_id,
                        session_id=sess_obj.id,
                        minutes_played=float(duration),
                        total_distance=round(real_td, 1),
                        hsr_distance=round(real_hsr, 1),
                        sprint_distance=round(real_sprint, 1),
                        hmld=round(real_hmld, 1),
                        accelerations_eff=real_acc,
                        decelerations_eff=real_dec,
                        max_speed=round(vmax, 2),
                        player_load=round(pload, 1),
                        rpe=round(rpe, 1)
                    )
                    db.add(metric)

            current_date += timedelta(days=1)

        print(f"Poblado finalizado con éxito:")
        print(f"  - 24 jugadores registrados.")
        print(f"  - 25 objetivos de carga posicional configurados.")
        print(f"  - {session_count} sesiones simuladas a lo largo de 6 semanas.")
        print(f"  - {session_count * 24} registros GPS de métricas calculados.")

    # 4. Sincronizar automáticamente los partidos y entrenamientos oficiales reales de Ubiko
    with get_db() as db:
        from src.services.importer import UbikoImporter
        from src.services.analytics import sync_and_update_player_match_peaks
        sync_res = UbikoImporter.sync_local_csv_samples(db)
        sync_and_update_player_match_peaks(db)
        print(f"  - {sync_res.get('synced_count', 0)} sesiones oficiales Ubiko importadas desde data/samples.")


if __name__ == "__main__":
    seed_database()
