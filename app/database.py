from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


settings = get_settings()
connect_args = {}
if settings.database_url.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(settings.database_url, pool_pre_ping=True, connect_args=connect_args)

if engine.dialect.name == "postgresql":
    # search_path on the alt server is "scerp, core": without an explicit schema SQLAlchemy treats a
    # same-named table in core as already existing and never creates ours. Pin app objects to the
    # first schema of search_path.
    app_schema = settings.db_schema.strip()
    if not app_schema:
        with engine.connect() as _conn:
            app_schema = _conn.execute(text("SELECT current_schema()")).scalar() or ""
    if app_schema:
        engine = engine.execution_options(schema_translate_map={None: app_schema})

if settings.database_url.startswith("sqlite"):

    @event.listens_for(engine, "connect")
    def _sqlite_fk(dbapi_connection, connection_record):  # type: ignore[no-untyped-def]
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
