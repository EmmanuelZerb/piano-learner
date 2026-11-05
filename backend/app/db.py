from collections.abc import Iterator

from fastapi import Request
from sqlalchemy import Engine
from sqlmodel import Session, SQLModel, create_engine

import app.models  # noqa: F401  (enregistre les tables dans SQLModel.metadata)


def make_engine(database_url: str) -> Engine:
    # check_same_thread=False : FastAPI exécute les routes sync dans un pool de threads.
    engine = create_engine(database_url, connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return engine


def get_session(request: Request) -> Iterator[Session]:
    with Session(request.app.state.engine) as session:
        yield session
