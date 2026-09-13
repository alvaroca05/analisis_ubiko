"""
Modelos ORM de SQLAlchemy para la plataforma de análisis GPS UBIKO.
Incluye entidades de Jugadores, Sesiones de Entrenamiento/Partido, Métricas GPS y Objetivos Planificados.
"""

from datetime import date
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, Date, Text, ForeignKey, UniqueConstraint
)
from sqlalchemy.orm import relationship

from src.database.connection import Base


class Player(Base):
    """
    Modelo que representa a un futbolista de la plantilla.
    """
    __tablename__ = "players"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, index=True)
    dorsal = Column(Integer, nullable=False, unique=True)
    position = Column(String(50), nullable=False, index=True)  # Central, Lateral, Mediocentro, Extremo, Delantero
    max_speed_kmh = Column(Float, default=32.0)
    vo2max = Column(Float, nullable=True)
    active = Column(Boolean, default=True)

    # Relaciones
    metrics = relationship("PlayerMetric", back_populates="player", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Player(dorsal={self.dorsal}, name='{self.name}', position='{self.position}')>"


class TrainingSession(Base):
    """
    Modelo que representa una sesión de entrenamiento o partido dentro del microciclo.
    """
    __tablename__ = "training_sessions"
    __table_args__ = (
        UniqueConstraint("date", "name", name="uq_session_date_name"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
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
        return f"<TrainingSession(date='{self.date}', name='{self.name}', day='{self.microcycle_day}')>"


class PlayerMetric(Base):
    """
    Métricas de carga externa e interna registradas por el dispositivo GPS UBIKO para un jugador en una sesión.
    """
    __tablename__ = "player_metrics"
    __table_args__ = (
        UniqueConstraint("player_id", "session_id", name="uq_player_session"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False, index=True)
    session_id = Column(Integer, ForeignKey("training_sessions.id"), nullable=False, index=True)

    minutes_played = Column(Float, default=0.0)
    total_distance = Column(Float, default=0.0)      # Metros totales recorridos (DT)
    hsr_distance = Column(Float, default=0.0)        # Distancia en carrera de alta velocidad (>19.8 km/h) (HSR)
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


class TargetLoad(Base):
    """
    Objetivos de carga física previstos por el preparador físico para cada día de microciclo y posición.
    """
    __tablename__ = "target_loads"
    __table_args__ = (
        UniqueConstraint("microcycle_day", "position", name="uq_target_day_position"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    microcycle_day = Column(String(20), nullable=False, index=True)
    position = Column(String(50), nullable=False, index=True)
    target_td = Column(Float, nullable=False)       # Distancia total planificada (m)
    target_hsr = Column(Float, nullable=False)      # High Speed Running planificado (m)
    target_hmld = Column(Float, nullable=False)     # HMLD planificado (m)
    target_acc_eff = Column(Integer, nullable=False) # Aceleraciones eficaces planificadas
    target_dec_eff = Column(Integer, nullable=False) # Desaceleraciones eficaces planificadas

    def __repr__(self):
        return f"<TargetLoad(day='{self.microcycle_day}', position='{self.position}', TD={self.target_td}m)>"
