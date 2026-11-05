from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    ERROR = "error"
    CANCELLED = "cancelled"

    @property
    def finished(self) -> bool:
        return self in {JobStatus.DONE, JobStatus.ERROR, JobStatus.CANCELLED}


def _now() -> datetime:
    return datetime.now(UTC)


class Job(SQLModel, table=True):
    """Traitement de fond : import (fichier/YouTube) puis séparation, transcription, niveaux."""

    id: str = Field(default_factory=lambda: uuid4().hex, primary_key=True)
    label: str  # titre affichable (nom de fichier, URL ou titre du morceau)
    source: str  # "upload" | "youtube" | "track"
    track_id: str | None = Field(default=None, index=True)
    status: JobStatus = JobStatus.QUEUED
    step: str = "queued"
    progress: float = 0.0  # 0 à 1, tout le traitement confondu
    error_code: str | None = None
    error_message: str | None = None
    payload: dict = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=_now)
    finished_at: datetime | None = None
