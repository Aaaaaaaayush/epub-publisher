from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, scoped_session
from app.config.settings import settings
from app.database.base import Base

# Setup database engine
# SQLite-specific arguments: allow multithreaded access
engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}
)

# Enable foreign keys for SQLite databases
@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    if settings.DATABASE_URL.startswith("sqlite"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON;")
        cursor.close()

# Session factories
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
db_session = scoped_session(SessionLocal)

def init_db():
    """Initializes the database schema and creates all tables."""
    # Import models here to register them with the metadata
    from app.models.document import Document, Section
    Base.metadata.create_all(bind=engine)
