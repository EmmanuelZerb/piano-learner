from collections.abc import Iterator

from fastapi import Request
from sqlalchemy import Engine, event, inspect, text
from sqlmodel import Session, SQLModel, create_engine

import app.models  # noqa: F401  (enregistre les tables dans SQLModel.metadata)


def add_missing_columns(engine: Engine) -> list[str]:
    """Migration minimale : ajoute (nullable) les colonnes présentes dans les modèles mais
    absentes en base. Suffit tant qu'on ne fait qu'ajouter des champs optionnels ; passer à
    Alembic le jour où il faudra renommer ou transformer des colonnes.
    """
    inspector = inspect(engine)
    added: list[str] = []
    with engine.begin() as conn:
        for table in SQLModel.metadata.sorted_tables:
            if not inspector.has_table(table.name):
                continue
            existing = {c["name"] for c in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in existing:
                    continue
                col_type = column.type.compile(dialect=engine.dialect)
                conn.execute(
                    text(f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {col_type}')
                )
                added.append(f"{table.name}.{column.name}")
    return added


def _enable_wal(dbapi_connection, _record) -> None:  # type: ignore[no-untyped-def]
    dbapi_connection.execute("PRAGMA journal_mode=WAL")


def make_engine(database_url: str) -> Engine:
    # check_same_thread=False : routes sync et worker des tâches tournent dans des threads.
    # WAL + timeout : lectures de l'API pendant que le worker écrit la progression.
    engine = create_engine(database_url, connect_args={"check_same_thread": False, "timeout": 30})
    event.listen(engine, "connect", _enable_wal)
    SQLModel.metadata.create_all(engine)
    add_missing_columns(engine)
    return engine


def get_session(request: Request) -> Iterator[Session]:
    with Session(request.app.state.engine) as session:
        yield session
