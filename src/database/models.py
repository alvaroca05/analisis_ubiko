"""
Modelos ORM de SQLAlchemy para la plataforma de análisis GPS UBIKO.
Incluye entidades de Jugadores, Sesiones de Entrenamiento/Partido, Métricas GPS y Objetivos Planificados.
"""

from datetime import date, datetime
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, Date, DateTime, Text, ForeignKey, UniqueConstraint
)
from sqlalchemy.orm import relationship

from src.database.connection import Base
from src.config import DEFAULT_CLUB_ID


class Player(Base):
    """
    Modelo que representa a un futbolista de la plantilla.
    Soporta multitenant mediante club_id.
    """
    __tablename__ = "players"
    __table_args__ = (
        UniqueConstraint("club_id", "dorsal", name="uq_club_player_dorsal"),
        {"extend_existing": True}
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    club_id = Column(Integer, default=DEFAULT_CLUB_ID, nullable=False, index=True)
    name = Column(String(100), nullable=False, index=True)
    dorsal = Column(Integer, nullable=False)
    position = Column(String(50), nullable=False, index=True)  # Central, Lateral, Mediocentro, Extremo, Delantero, Portero
    max_speed_kmh = Column(Float, default=32.0)
    vo2max = Column(Float, nullable=True)
    active = Column(Boolean, default=True)

    # Relaciones
    metrics = relationship("PlayerMetric", back_populates="player", cascade="all, delete-orphan")
    match_peaks = relationship("PlayerMatchPeak", back_populates="player", uselist=False, cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Player(id={self.id}, dorsal={self.dorsal}, name='{self.name}', position='{self.position}', club_id={self.club_id})>"


class TrainingSession(Base):
    """
    Modelo que representa una sesión de entrenamiento o partido dentro del microciclo.
    Soporta multitenant mediante club_id.
    """
    __tablename__ = "training_sessions"
    __table_args__ = (
        UniqueConstraint("club_id", "date", "name", name="uq_session_club_date_name"),
        {"extend_existing": True}
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    club_id = Column(Integer, default=DEFAULT_CLUB_ID, nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)
    name = Column(String(100), nullable=False)
    microcycle_day = Column(String(20), nullable=False, index=True)  # MD-4, MD-3, MD-2, MD-1, MD
    session_type = Column(String(50), default="Entrenamiento")       # Entrenamiento, Partido
    duration_minutes = Column(Integer, default=75)
    pitch_condition = Column(String(50), default="Óptimo")
    notes = Column(Text, nullable=True)

    # Relaciones
    metrics = relationship("PlayerMetric", back_populates="session", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<TrainingSession(id={self.id}, date='{self.date}', name='{self.name}', day='{self.microcycle_day}', club_id={self.club_id})>"


class PlayerMetric(Base):
    """
    Métricas de carga externa e interna registradas por el dispositivo GPS UBIKO para un jugador en una sesión.
    """
    __tablename__ = "player_metrics"
    __table_args__ = (
        UniqueConstraint("player_id", "session_id", name="uq_player_session"),
        {"extend_existing": True}
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    club_id = Column(Integer, default=DEFAULT_CLUB_ID, nullable=False, index=True)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False, index=True)
    session_id = Column(Integer, ForeignKey("training_sessions.id"), nullable=False, index=True)

    minutes_played = Column(Float, default=0.0)
    total_distance = Column(Float, default=0.0)      # Metros totales recorridos (DT)
    hsr_distance = Column(Float, default=0.0)        # Distancia en carrera de alta velocidad (>19.8 km/h / >21 km/h) (HSR)
    sprint_distance = Column(Float, default=0.0)     # Distancia al sprint (>25.2 km/h)
    hmld = Column(Float, default=0.0)                # High Metabolic Load Distance (HMLD) en metros
    accelerations_eff = Column(Integer, default=0)   # Aceleraciones eficaces (>3.0 m/s²)
    decelerations_eff = Column(Integer, default=0)   # Desaceleraciones eficaces (<-3.0 m/s²)
    max_speed = Column(Float, default=0.0)           # Velocidad punta registrada en la sesión (km/h)
    player_load = Column(Float, default=0.0)         # Carga acelerométrica triaxial (AU)
    rpe = Column(Float, nullable=True)               # Escala de esfuerzo percibido RPE (Borg 0-10)

    # Relaciones
    player = relationship("Player", back_populates="metrics")
    session = relationship("TrainingSession", back_populates="metrics")

    @property
    def total_efforts(self) -> int:
        """Suma de aceleraciones y desaceleraciones de alta intensidad (AC.E)."""
        return (self.accelerations_eff or 0) + (self.decelerations_eff or 0)

    def __repr__(self):
        return f"<PlayerMetric(player_id={self.player_id}, session_id={self.session_id}, DT={self.total_distance:.1f}m)>"


class PlayerMatchPeak(Base):
    """
    Modelo del 'Partido de Máxima Exigencia' (Carga 100% Dinámica Individual).
    Almacena los valores pico registrados en competición oficial (MD / Partido) para cada jugador.
    Si en un nuevo partido se superan estos techos individuales, se actualizan automáticamente.
    """
    __tablename__ = "player_match_peaks"
    __table_args__ = (
        UniqueConstraint("club_id", "player_id", name="uq_club_player_match_peak"),
        {"extend_existing": True}
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    club_id = Column(Integer, default=DEFAULT_CLUB_ID, nullable=False, index=True)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False, unique=True, index=True)

    # Techos dinámicos del 100%
    peak_td = Column(Float, nullable=False, default=10500.0)        # DT 100% (m)
    peak_hsr = Column(Float, nullable=False, default=700.0)         # HSR 100% (m)
    peak_sprint = Column(Float, nullable=False, default=200.0)      # Sprint 100% (m)
    peak_hmld = Column(Float, nullable=False, default=2000.0)       # HMLD 100% (m)
    peak_acc_eff = Column(Integer, nullable=False, default=45)      # Aceleraciones 100%
    peak_dec_eff = Column(Integer, nullable=False, default=45)      # Desaceleraciones 100%
    peak_max_speed = Column(Float, nullable=False, default=32.0)    # Velocidad máxima en partido (km/h)

    # Trazabilidad del partido de máxima exigencia
    peak_session_name = Column(String(150), nullable=True)          # Ej: "vs Recreativo de Huelva"
    peak_session_date = Column(Date, nullable=True)
    last_updated = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relación
    player = relationship("Player", back_populates="match_peaks")

    @property
    def peak_eff(self) -> int:
        """Suma de aceleraciones y desaceleraciones eficaces en partido (AC.E 100%)."""
        return (self.peak_acc_eff or 0) + (self.peak_dec_eff or 0)

    def __repr__(self):
        return (
            f"<PlayerMatchPeak(player_id={self.player_id}, peak_td={self.peak_td:.0f}m, "
            f"peak_hsr={self.peak_hsr:.0f}m, match='{self.peak_session_name}')>"
        )


class TargetLoad(Base):
    """
    Objetivos de carga física previstos por el preparador físico para cada día de microciclo y posición.
    Soporta multitenant mediante club_id.
    """
    __tablename__ = "target_loads"
    __table_args__ = (
        UniqueConstraint("club_id", "microcycle_day", "position", name="uq_target_club_day_position"),
        {"extend_existing": True}
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    club_id = Column(Integer, default=DEFAULT_CLUB_ID, nullable=False, index=True)
    microcycle_day = Column(String(20), nullable=False, index=True)
    position = Column(String(50), nullable=False, index=True)
    target_td = Column(Float, nullable=False)        # Distancia total planificada (m)
    target_hsr = Column(Float, nullable=False)       # High Speed Running planificado (m)
    target_hmld = Column(Float, nullable=False)      # HMLD planificado (m)
    target_acc_eff = Column(Integer, nullable=False)  # Aceleraciones eficaces planificadas
    target_dec_eff = Column(Integer, nullable=False)  # Desaceleraciones eficaces planificadas

    @property
    def target_efforts(self) -> int:
        return (self.target_acc_eff or 0) + (self.target_dec_eff or 0)

    @property
    def target_total_distance(self) -> float:
        return self.target_td

    @property
    def target_hsr_distance(self) -> float:
        return self.target_hsr

    def __repr__(self):
        return f"<TargetLoad(day='{self.microcycle_day}', position='{self.position}', TD={self.target_td}m, club_id={self.club_id})>"

