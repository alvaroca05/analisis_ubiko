"""
Gestión de la conexión y sesiones de SQLAlchemy para SQLite.
"""

from contextlib import contextmanager
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from src.config import DATABASE_URL

# Configuración dinámica del motor según motor de base de datos (SQLite local o PostgreSQL en la nube)
if "sqlite" in DATABASE_URL.lower():
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},
        echo=False
    )
else:
    # PostgreSQL / Supabase Transaction Pooler (puerto 6543) o Session Pooler (puerto 5432)
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        pool_recycle=300,
        pool_size=5,
        max_overflow=10,
        echo=False
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, expire_on_commit=False, bind=engine)
Base = declarative_base()


@contextmanager
def get_db():
    """
    Context manager para manejo seguro de sesiones de base de datos.
    Asegura commit al finalizar y rollback en caso de error.
    """
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db():
    """
    Crea todas las tablas definidas en los modelos.
    Incluye comprobación defensiva de conectividad para diagnosticar problemas de red o credenciales.
    """
    from sqlalchemy import text
    from src.database.models import Base  # Import local para registrar modelos

    is_sqlite = "sqlite" in DATABASE_URL.lower()
    backend_name = "SQLite local" if is_sqlite else "PostgreSQL / Supabase"

    try:
        # 1. Comprobación defensiva de conectividad
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        
        # 2. Creación de tablas
        Base.metadata.create_all(bind=engine)

        # 3. Migración defensiva de columnas (club_id) en caso de bases de datos existentes
        with engine.connect() as conn:
            for table_name in ["players", "training_sessions", "player_metrics", "target_loads"]:
                try:
                    conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN club_id INTEGER DEFAULT 1 NOT NULL"))
                    conn.commit()
                except Exception:
                    pass

        print(f"[BASE DE DATOS] Conectado y sincronizado con éxito ({backend_name}).")
    except Exception as e:
        print(f"[BASE DE DATOS ERROR] No se pudo conectar a {backend_name}: {e}")
        raise

